from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from app.security import decode_token
from app.db import connection

bearer = HTTPBearer(auto_error=False)

def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    if not credentials:
        raise HTTPException(status_code=401, detail="Autenticação necessária", headers={"WWW-Authenticate": "Bearer"})
    try:
        claims = decode_token(credentials.credentials, "access")
        user_id, workspace_id = int(claims["sub"]), int(claims["workspace_id"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")
    with connection() as conn:
        user = conn.execute("SELECT id, workspace_id, full_name, email, role FROM users WHERE id=%s AND workspace_id=%s AND is_active", (user_id, workspace_id)).fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="Usuário inativo ou inexistente")
    return user

def manager_only(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "manager":
        raise HTTPException(status_code=403, detail="Ação permitida somente ao gestor")
    return user

def opportunity_scope(user: dict) -> tuple[str, tuple]:
    if user["role"] == "manager":
        return "workspace_id=%s", (user["workspace_id"],)
    return "workspace_id=%s AND owner_user_id=%s", (user["workspace_id"], user["id"])
