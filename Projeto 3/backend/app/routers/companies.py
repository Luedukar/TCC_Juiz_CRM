import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.audit import audit
from app.database import get_db
from app.deps import get_current_user, get_owned_or_404, is_manager, resolve_owner_id, scope_owned
from app.errors import Forbidden
from app.models import Company, User
from app.pagination import paginate
from app.schemas import CompanyCreate, CompanyOut, CompanyUpdate, Page
from app.security import utcnow

router = APIRouter(prefix="/companies", tags=["Empresas"])


@router.get("", response_model=Page[CompanyOut])
def list_companies(
    q: Optional[str] = Query(None, max_length=100, description="Busca por razão social, nome fantasia ou CNPJ"),
    owner_id: Optional[uuid.UUID] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = scope_owned(select(Company).where(Company.deleted_at.is_(None)), Company, user)
    if owner_id:
        stmt = stmt.where(Company.owner_id == owner_id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Company.legal_name.ilike(like), Company.trade_name.ilike(like), Company.cnpj.ilike(like)))
    return paginate(db, stmt.order_by(Company.legal_name), page, page_size)


@router.post("", response_model=CompanyOut, status_code=201)
def create_company(body: CompanyCreate, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data = body.model_dump(exclude={"owner_id"})
    company = Company(**data, owner_id=resolve_owner_id(db, body.owner_id, user))
    db.add(company)
    db.flush()
    audit(db, user, "create", "company", company.id, request=request)
    db.commit()
    db.refresh(company)
    return company


@router.get("/{company_id}", response_model=CompanyOut)
def get_company(company_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_owned_or_404(db, Company, company_id, user)


@router.patch("/{company_id}", response_model=CompanyOut)
def update_company(
    company_id: uuid.UUID, body: CompanyUpdate, request: Request,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    company = get_owned_or_404(db, Company, company_id, user)
    data = body.model_dump(exclude_unset=True)
    if "owner_id" in data:
        data["owner_id"] = resolve_owner_id(db, data["owner_id"], user)
    for field, value in data.items():
        setattr(company, field, value)
    audit(db, user, "update", "company", company.id, {"fields": sorted(data)}, request)
    db.commit()
    db.refresh(company)
    return company


@router.delete("/{company_id}", status_code=204)
def delete_company(company_id: uuid.UUID, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company = get_owned_or_404(db, Company, company_id, user)
    company.deleted_at = utcnow()
    audit(db, user, "delete", "company", company.id, request=request)
    db.commit()
    return Response(status_code=204)
