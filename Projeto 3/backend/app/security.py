"""Hash de senha (argon2id), JWT de acesso e refresh tokens opacos."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.config import get_settings
from app.models import User

_ph = PasswordHasher()
# Hash descartável usado para igualar o tempo de resposta quando o e-mail não existe.
DUMMY_HASH = _ph.hash("senha-descartavel-para-timing")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _ph.check_needs_rehash(password_hash)


def create_access_token(user: User) -> tuple[str, int]:
    s = get_settings()
    now = utcnow()
    expires = now + timedelta(minutes=s.access_token_minutes)
    payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "type": "access",
        "iat": now,
        "exp": expires,
    }
    token = jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)
    return token, s.access_token_minutes * 60


def decode_access_token(token: str) -> dict[str, Any]:
    """Levanta jwt.PyJWTError (incluindo ExpiredSignatureError) se o token for inválido."""
    s = get_settings()
    payload = jwt.decode(
        token,
        s.jwt_secret,
        algorithms=[s.jwt_algorithm],
        options={"require": ["exp", "iat", "sub"]},
    )
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("tipo de token inválido")
    return payload


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def new_refresh_token() -> tuple[str, str]:
    """Retorna (token_em_claro, hash). Só o hash é persistido."""
    raw = secrets.token_urlsafe(48)
    return raw, hash_token(raw)
