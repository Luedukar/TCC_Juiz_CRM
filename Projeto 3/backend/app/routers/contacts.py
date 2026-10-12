import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.audit import audit
from app.database import get_db
from app.deps import get_current_user, get_owned_or_404, resolve_owner_id, require_manager, scope_owned
from app.errors import BadRequest
from app.models import Company, Contact, ContactConsent, User
from app.pagination import paginate
from app.schemas import ConsentIn, ConsentOut, ContactCreate, ContactOut, ContactUpdate, Page
from app.security import utcnow

router = APIRouter(prefix="/contacts", tags=["Contatos"])


def _clear_other_primary(db: Session, company_id: uuid.UUID, keep_id: Optional[uuid.UUID]) -> None:
    """Garante um único contato principal por empresa (evita violar o índice único parcial)."""
    stmt = update(Contact).where(
        Contact.company_id == company_id, Contact.is_primary.is_(True), Contact.deleted_at.is_(None)
    )
    if keep_id:
        stmt = stmt.where(Contact.id != keep_id)
    db.execute(stmt.values(is_primary=False))


@router.get("", response_model=Page[ContactOut])
def list_contacts(
    company_id: Optional[uuid.UUID] = None,
    q: Optional[str] = Query(None, max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = scope_owned(select(Contact).where(Contact.deleted_at.is_(None)), Contact, user)
    if company_id:
        stmt = stmt.where(Contact.company_id == company_id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Contact.full_name.ilike(like), Contact.email.ilike(like)))
    return paginate(db, stmt.order_by(Contact.full_name), page, page_size)


@router.post("", response_model=ContactOut, status_code=201)
def create_contact(body: ContactCreate, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company = get_owned_or_404(db, Company, body.company_id, user)  # 404 se a empresa não for da carteira
    owner_id = resolve_owner_id(db, body.owner_id, user, default=company.owner_id)
    if body.is_primary:
        _clear_other_primary(db, company.id, None)
    contact = Contact(**body.model_dump(exclude={"owner_id"}), owner_id=owner_id)
    db.add(contact)
    db.flush()
    audit(db, user, "create", "contact", contact.id, request=request)
    db.commit()
    db.refresh(contact)
    return contact


@router.get("/{contact_id}", response_model=ContactOut)
def get_contact(contact_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_owned_or_404(db, Contact, contact_id, user)


@router.patch("/{contact_id}", response_model=ContactOut)
def update_contact(
    contact_id: uuid.UUID, body: ContactUpdate, request: Request,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    contact = get_owned_or_404(db, Contact, contact_id, user)
    if contact.anonymized_at:
        raise BadRequest("Contato anonimizado não pode ser editado.", code="contact_anonymized")
    data = body.model_dump(exclude_unset=True)
    if "owner_id" in data:
        data["owner_id"] = resolve_owner_id(db, data["owner_id"], user)
    if data.get("is_primary"):
        _clear_other_primary(db, contact.company_id, contact.id)
    for field, value in data.items():
        setattr(contact, field, value)
    audit(db, user, "update", "contact", contact.id, {"fields": sorted(data)}, request)
    db.commit()
    db.refresh(contact)
    return contact


@router.delete("/{contact_id}", status_code=204)
def delete_contact(contact_id: uuid.UUID, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    contact = get_owned_or_404(db, Contact, contact_id, user)
    contact.deleted_at = utcnow()
    contact.is_primary = False
    audit(db, user, "delete", "contact", contact.id, request=request)
    db.commit()
    return Response(status_code=204)


# ------------------------------------------------------------------ LGPD
@router.get("/{contact_id}/consents", response_model=list[ConsentOut])
def list_consents(contact_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    contact = get_owned_or_404(db, Contact, contact_id, user)
    return db.scalars(
        select(ContactConsent).where(ContactConsent.contact_id == contact.id).order_by(ContactConsent.granted_at.desc())
    ).all()


@router.post("/{contact_id}/consents", response_model=ConsentOut, status_code=201)
def record_consent(
    contact_id: uuid.UUID, body: ConsentIn, request: Request,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Registra uma decisão de consentimento. A decisão anterior da mesma finalidade é encerrada (revoked_at)."""
    contact = get_owned_or_404(db, Contact, contact_id, user)
    now = utcnow()
    db.execute(
        update(ContactConsent)
        .where(
            ContactConsent.contact_id == contact.id,
            ContactConsent.purpose == body.purpose,
            ContactConsent.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    consent = ContactConsent(
        contact_id=contact.id, purpose=body.purpose, basis=body.basis, granted=body.granted,
        source=body.source, evidence=body.evidence, recorded_by=user.id,
        revoked_at=None if body.granted else now,
    )
    db.add(consent)
    db.flush()
    audit(db, user, "consent_granted" if body.granted else "consent_revoked", "contact", contact.id,
          {"purpose": body.purpose.value}, request)
    db.commit()
    db.refresh(consent)
    return consent


@router.post("/{contact_id}/anonymize", response_model=ContactOut)
def anonymize_contact(
    contact_id: uuid.UUID, request: Request,
    manager: User = Depends(require_manager), db: Session = Depends(get_db),
):
    """LGPD (direito do titular): remove dados pessoais mantendo o vínculo com negócios e o histórico de consentimentos."""
    contact = get_owned_or_404(db, Contact, contact_id, manager)
    contact.full_name = "Contato anonimizado"
    contact.email = None
    contact.phone = None
    contact.job_title = None
    contact.notes = None
    contact.is_primary = False
    contact.anonymized_at = utcnow()
    audit(db, manager, "anonymize", "contact", contact.id, request=request)
    db.commit()
    db.refresh(contact)
    return contact
