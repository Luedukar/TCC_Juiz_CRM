import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.audit import audit
from app.database import get_db
from app.deps import require_manager
from app.errors import BadRequest, NotFound
from app.models import RefreshToken, User, UserRole
from app.pagination import paginate
from app.schemas import Page, UserCreate, UserOut, UserUpdate
from app.security import hash_password, utcnow

router = APIRouter(prefix="/users", tags=["Usuários (gestor)"])


@router.get("", response_model=Page[UserOut])
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
):
    return paginate(db, select(User).order_by(User.name), page, page_size)


@router.post("", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, request: Request, manager: User = Depends(require_manager), db: Session = Depends(get_db)):
    user = User(name=body.name, email=body.email, password_hash=hash_password(body.password), role=body.role)
    db.add(user)
    db.flush()
    audit(db, manager, "create", "user", user.id, {"role": body.role.value}, request)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: uuid.UUID, body: UserUpdate, request: Request,
    manager: User = Depends(require_manager), db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("Usuário não encontrado.")
    data = body.model_dump(exclude_unset=True)

    if user.id == manager.id and (data.get("is_active") is False or data.get("role") == UserRole.sales_rep):
        raise BadRequest("Você não pode desativar ou rebaixar a própria conta.")

    password_changed = "password" in data
    if password_changed:
        user.password_hash = hash_password(data.pop("password"))
    for field, value in data.items():
        setattr(user, field, value)

    # Desativar o usuário ou trocar a senha encerra todas as sessões existentes.
    if data.get("is_active") is False or password_changed:
        db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )
    audit(db, manager, "update", "user", user.id, {"fields": sorted(body.model_fields_set)}, request)
    db.commit()
    db.refresh(user)
    return user
