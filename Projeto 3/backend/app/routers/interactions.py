import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import audit
from app.database import get_db
from app.deps import get_current_user, get_owned_or_404, is_manager, scope_owned
from app.errors import BadRequest, Forbidden, NotFound
from app.models import Contact, Deal, Interaction, InteractionType, User
from app.pagination import paginate
from app.schemas import InteractionCreate, InteractionOut, InteractionUpdate, Page

router = APIRouter(tags=["Histórico de interações"])


def _check_contact(db: Session, contact_id: Optional[uuid.UUID], deal: Deal) -> None:
    if contact_id is None:
        return
    contact = db.scalars(select(Contact).where(Contact.id == contact_id, Contact.deleted_at.is_(None))).first()
    if contact is None or contact.company_id != deal.company_id:
        raise BadRequest("O contato informado não pertence à empresa deste negócio.", code="contact_company_mismatch")


def _get_interaction(db: Session, interaction_id: uuid.UUID, user: User) -> Interaction:
    """Vendedor só acessa interações de negócios da própria carteira (senão 404)."""
    stmt = (
        select(Interaction)
        .join(Deal, Deal.id == Interaction.deal_id)
        .where(Interaction.id == interaction_id, Deal.deleted_at.is_(None))
    )
    interaction = db.scalars(scope_owned(stmt, Deal, user)).unique().first()
    if interaction is None:
        raise NotFound()
    return interaction


def _ensure_can_change(interaction: Interaction, user: User) -> None:
    if not is_manager(user) and interaction.user_id != user.id:
        raise Forbidden("Apenas o autor do registro ou um gestor pode alterá-lo.")


@router.get("/deals/{deal_id}/interactions", response_model=Page[InteractionOut])
def list_interactions(
    deal_id: uuid.UUID,
    type: Optional[InteractionType] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    deal = get_owned_or_404(db, Deal, deal_id, user)
    stmt = select(Interaction).where(Interaction.deal_id == deal.id)
    if type:
        stmt = stmt.where(Interaction.type == type)
    return paginate(db, stmt.order_by(Interaction.occurred_at.desc()), page, page_size)


@router.post("/deals/{deal_id}/interactions", response_model=InteractionOut, status_code=201)
def create_interaction(
    deal_id: uuid.UUID, body: InteractionCreate, request: Request,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    deal = get_owned_or_404(db, Deal, deal_id, user)
    _check_contact(db, body.contact_id, deal)
    interaction = Interaction(deal_id=deal.id, user_id=user.id, **body.model_dump())
    db.add(interaction)
    db.flush()
    audit(db, user, "create", "interaction", interaction.id, {"deal_id": str(deal.id)}, request)
    db.commit()
    db.refresh(interaction)
    return interaction


@router.patch("/interactions/{interaction_id}", response_model=InteractionOut)
def update_interaction(
    interaction_id: uuid.UUID, body: InteractionUpdate, request: Request,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    interaction = _get_interaction(db, interaction_id, user)
    _ensure_can_change(interaction, user)
    data = body.model_dump(exclude_unset=True)
    if data.get("contact_id"):
        _check_contact(db, data["contact_id"], db.get(Deal, interaction.deal_id))
    for field, value in data.items():
        setattr(interaction, field, value)
    audit(db, user, "update", "interaction", interaction.id, {"fields": sorted(data)}, request)
    db.commit()
    db.refresh(interaction)
    return interaction


@router.delete("/interactions/{interaction_id}", status_code=204)
def delete_interaction(interaction_id: uuid.UUID, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    interaction = _get_interaction(db, interaction_id, user)
    _ensure_can_change(interaction, user)
    db.delete(interaction)
    audit(db, user, "delete", "interaction", interaction_id, request=request)
    db.commit()
    return Response(status_code=204)
