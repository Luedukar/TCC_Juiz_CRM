from datetime import datetime, timedelta, timezone
import hashlib, secrets
import jwt
from pwdlib import PasswordHash
from app.config import settings

password_hash = PasswordHash.recommended()
ALGORITHM = "HS256"

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return password_hash.verify(plain, hashed)
    except Exception:
        return False

def hash_password(plain: str) -> str:
    return password_hash.hash(plain)

def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def issue_access(user: dict) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user["id"]), "workspace_id": user["workspace_id"], "role": user["role"], "iat": now, "exp": now + timedelta(minutes=settings.access_token_minutes), "type": "access"}
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)

def issue_refresh(user: dict) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=settings.refresh_token_days)
    token = jwt.encode({"sub": str(user["id"]), "workspace_id": user["workspace_id"], "iat": now, "exp": expires, "jti": secrets.token_urlsafe(16), "type": "refresh"}, settings.jwt_secret, algorithm=ALGORITHM)
    return token, expires

def decode_token(token: str, expected_type: str) -> dict:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("tipo de token inválido")
    return payload
