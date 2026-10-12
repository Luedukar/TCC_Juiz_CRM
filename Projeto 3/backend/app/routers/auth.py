import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.audit import audit
from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user
from app.errors import AccountLocked, Unauthorized
from app.models import RefreshToken, User
from app.ratelimit import inet_or_none, login_rate_limit, record_login_failure, refresh_rate_limit
from app.schemas import LoginIn, LoginOut, RefreshIn, TokenPair, UserOut
from app.security import (
    DUMMY_HASH, create_access_token, hash_password, hash_token, new_refresh_token,
    password_needs_rehash, utcnow, verify_password,
)

router = APIRouter(prefix="/auth", tags=["Autenticação"])


def _issue_tokens(db: Session, user: User, request: Request, family_id: uuid.UUID | None = None) -> tuple[TokenPair, RefreshToken]:
    s = get_settings()
    access, expires_in = create_access_token(user)
    raw, token_hash = new_refresh_token()
    record = RefreshToken(
        user_id=user.id,
        family_id=family_id or uuid.uuid4(),
        token_hash=token_hash,
        expires_at=utcnow() + timedelta(days=s.refresh_token_days),
        user_agent=(request.headers.get("user-agent") or "")[:300] or None,
        ip_address=inet_or_none(request),
    )
    db.add(record)
    db.flush()
    return TokenPair(access_token=access, refresh_token=raw, expires_in=expires_in), record


def _revoke_family(db: Session, family_id: uuid.UUID) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )


@router.post("/login", response_model=LoginOut, dependencies=[Depends(login_rate_limit)])
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    s = get_settings()
    now = utcnow()
    user = db.scalar(select(User).where(User.email == body.email))

    if user and user.locked_until and user.locked_until > now:
        raise AccountLocked()

    # Sempre verifica um hash (real ou descartável) para não vazar, pelo tempo, se o e-mail existe.
    valid = verify_password(user.password_hash if user else DUMMY_HASH, body.password)

    if not user or not valid or not user.is_active:
        record_login_failure(request)
        if user:
            user.failed_logins += 1
            if user.failed_logins >= s.max_failed_logins:
                user.locked_until = now + timedelta(minutes=s.lockout_minutes)
                user.failed_logins = 0
                audit(db, user, "account_locked", "user", user.id, request=request)
            db.commit()
        raise Unauthorized("E-mail ou senha incorretos.", code="invalid_credentials")

    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    tokens, _ = _issue_tokens(db, user, request)
    audit(db, user, "login", "user", user.id, request=request)
    db.commit()
    db.refresh(user)
    return LoginOut(**tokens.model_dump(), user=UserOut.model_validate(user))


@router.post("/refresh", response_model=TokenPair, dependencies=[Depends(refresh_rate_limit)])
def refresh(body: RefreshIn, request: Request, db: Session = Depends(get_db)):
    """Rotaciona o refresh token. Reuso de um token já rotacionado revoga toda a sessão."""
    record = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(body.refresh_token)).with_for_update()
    )
    if record is None:
        raise Unauthorized(code="invalid_refresh_token")

    if record.revoked_at is not None:
        # Duas renovações quase simultâneas (ex.: duas abas) não indicam roubo: recusa sem derrubar a sessão.
        grace = timedelta(seconds=get_settings().refresh_reuse_grace_seconds)
        if record.replaced_by is not None and utcnow() - record.revoked_at <= grace:
            raise Unauthorized(
                "Sua sessão foi renovada em outra janela. Tente novamente.", code="refresh_conflict"
            )
        _revoke_family(db, record.family_id)
        audit(db, record.user, "refresh_reuse_detected", "user", record.user_id, request=request)
        db.commit()
        raise Unauthorized("Sua sessão foi encerrada por segurança. Faça login novamente.", code="refresh_reuse_detected")

    user = record.user
    if record.expires_at <= utcnow() or not user.is_active:
        raise Unauthorized(code="refresh_token_expired")

    tokens, new_record = _issue_tokens(db, user, request, family_id=record.family_id)
    record.revoked_at = utcnow()
    record.replaced_by = new_record.id
    db.commit()
    return tokens


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(body: RefreshIn, db: Session = Depends(get_db)):
    """Idempotente: encerra a sessão associada ao refresh token informado."""
    record = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(body.refresh_token)))
    if record:
        _revoke_family(db, record.family_id)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/accept-terms", response_model=UserOut)
def accept_terms(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """LGPD: registra o aceite dos termos de uso e da política de privacidade."""
    user.terms_accepted_at = utcnow()
    audit(db, user, "accept_terms", "user", user.id, request=request)
    db.commit()
    db.refresh(user)
    return user
