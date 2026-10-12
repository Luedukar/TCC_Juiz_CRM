import uuid
from datetime import UTC, datetime

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user, require_manager
from app.limits import limiter
from app.models import RefreshToken, User
from app.schemas import LoginInput, RefreshInput, TokenPair, UserCreate, UserOut
from app.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


def _issue_tokens(db: Session, user: User) -> TokenPair:
    access_token, expires_in = create_access_token(user.id, user.role)
    refresh_token, jti, expires_at = create_refresh_token(user.id)
    db.add(RefreshToken(user_id=user.id, jti=jti, expires_at=expires_at))
    db.commit()
    return TokenPair(access_token=access_token, refresh_token=refresh_token, expires_in=expires_in)


@router.post("/login", response_model=TokenPair)
@limiter.limit(settings.login_rate_limit)
def login(payload: LoginInput, request: Request, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email.lower().strip()))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="E-mail ou senha inválidos.")
    return _issue_tokens(db, user)


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshInput, db: Session = Depends(get_db)):
    unauthorized = HTTPException(status_code=401, detail="Refresh token inválido ou revogado.")
    try:
        claims = decode_token(payload.refresh_token)
        if claims.get("type") != "refresh":
            raise unauthorized
        jti = uuid.UUID(claims["jti"])
        user_id = uuid.UUID(claims["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise unauthorized from None

    token_record = db.scalar(
        select(RefreshToken).where(RefreshToken.jti == jti).with_for_update()
    )
    if (
        token_record is None
        or token_record.user_id != user_id
        or token_record.revoked_at is not None
        or (
            token_record.expires_at.replace(tzinfo=UTC)
            if token_record.expires_at.tzinfo is None
            else token_record.expires_at
        )
        <= datetime.now(UTC)
    ):
        raise unauthorized

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized
    token_record.revoked_at = datetime.now(UTC)
    access_token, expires_in = create_access_token(user.id, user.role)
    new_refresh, new_jti, expires_at = create_refresh_token(user.id)
    db.add(RefreshToken(user_id=user.id, jti=new_jti, expires_at=expires_at))
    db.commit()
    return TokenPair(access_token=access_token, refresh_token=new_refresh, expires_in=expires_in)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: RefreshInput, db: Session = Depends(get_db)):
    unauthorized = HTTPException(status_code=401, detail="Refresh token inválido.")
    try:
        claims = decode_token(payload.refresh_token)
        if claims.get("type") != "refresh":
            raise unauthorized
        jti = uuid.UUID(claims["jti"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise unauthorized from None
    token_record = db.scalar(select(RefreshToken).where(RefreshToken.jti == jti))
    if token_record is None:
        raise unauthorized
    if token_record.revoked_at is None:
        token_record.revoked_at = datetime.now(UTC)
        db.commit()
    return None


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_manager),
):
    normalized_email = payload.email.lower().strip()
    if db.scalar(select(User).where(User.email == normalized_email)):
        raise HTTPException(status_code=409, detail="Já existe um usuário com esse e-mail.")
    user = User(
        full_name=payload.full_name.strip(),
        email=normalized_email,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
