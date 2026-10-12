"""Dependências de autenticação e RBAC.

Regras:
- sales_manager: enxerga e altera tudo.
- sales_rep: só enxerga/altera registros em que owner_id == seu id. Registros de
  outros vendedores respondem 404 (não vazamos a existência).
"""
import uuid
from typing import Any, Optional, TypeVar

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import Forbidden, NotFound, Unauthorized
from app.models import User, UserRole
from app.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)
T = TypeVar("T")


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise Unauthorized(code="not_authenticated")
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = uuid.UUID(payload["sub"])
    except jwt.ExpiredSignatureError:
        raise Unauthorized("Sua sessão expirou. Faça login novamente.", code="token_expired")
    except (jwt.PyJWTError, ValueError, KeyError):
        raise Unauthorized(code="invalid_token")

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise Unauthorized(code="invalid_token")
    return user


def is_manager(user: User) -> bool:
    return user.role == UserRole.sales_manager


def require_manager(user: User = Depends(get_current_user)) -> User:
    if not is_manager(user):
        raise Forbidden("Apenas gestores de vendas podem realizar esta ação.")
    return user


def scope_owned(stmt: Select, model: Any, user: User) -> Select:
    """Restringe a consulta à carteira do vendedor; gestor vê tudo."""
    return stmt if is_manager(user) else stmt.where(model.owner_id == user.id)


def get_owned_or_404(db: Session, model: type[T], obj_id: uuid.UUID, user: User) -> T:
    stmt = select(model).where(model.id == obj_id)  # type: ignore[attr-defined]
    if hasattr(model, "deleted_at"):
        stmt = stmt.where(model.deleted_at.is_(None))  # type: ignore[attr-defined]
    stmt = scope_owned(stmt, model, user)
    obj = db.scalars(stmt).unique().first()
    if obj is None:
        raise NotFound()
    return obj


def resolve_owner_id(db: Session, requested: Optional[uuid.UUID], user: User, default: Optional[uuid.UUID] = None) -> uuid.UUID:
    """Define o responsável por um registro novo ou reatribuído.

    Vendedor só pode atribuir a si mesmo. Gestor pode atribuir a qualquer usuário ativo.
    """
    if requested is None:
        return default or user.id
    if requested != user.id and not is_manager(user):
        raise Forbidden("Você só pode atribuir registros à sua própria carteira.")
    owner = db.get(User, requested)
    if owner is None or not owner.is_active:
        raise NotFound("Usuário responsável não encontrado.")
    return requested
