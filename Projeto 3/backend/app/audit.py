from typing import Any, Optional
import uuid

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditLog, User
from app.ratelimit import inet_or_none


def audit(
    db: Session,
    user: Optional[User],
    action: str,
    entity: str,
    entity_id: Optional[uuid.UUID] = None,
    details: Optional[dict[str, Any]] = None,
    request: Optional[Request] = None,
) -> None:
    """Registra a ação na sessão atual; é confirmada junto com o commit da operação."""
    db.add(
        AuditLog(
            user_id=user.id if user else None,
            action=action,
            entity=entity,
            entity_id=entity_id,
            details=details,
            ip_address=inet_or_none(request) if request else None,
        )
    )
