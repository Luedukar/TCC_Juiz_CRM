"""Mapeamento ORM das tabelas definidas em db/schema.sql.

O DDL é gerenciado pelo schema.sql (não usamos create_all). Os enums nativos do
PostgreSQL são referenciados com create_type=False.
"""
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    BigInteger, Boolean, CHAR, Date, DateTime, FetchedValue, ForeignKey,
    ForeignKeyConstraint, Integer, Numeric, SmallInteger, String, Text, func,
)
from sqlalchemy.dialects.postgresql import CITEXT, ENUM as PGEnum, INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserRole(str, enum.Enum):
    sales_manager = "sales_manager"
    sales_rep = "sales_rep"


class LeadTemperature(str, enum.Enum):
    cold = "cold"
    warm = "warm"
    hot = "hot"


class DealStatus(str, enum.Enum):
    open = "open"
    won = "won"
    lost = "lost"


class InteractionType(str, enum.Enum):
    meeting = "meeting"
    email = "email"
    call = "call"


class NextActionType(str, enum.Enum):
    meeting = "meeting"
    email = "email"
    call = "call"
    proposal = "proposal"
    follow_up = "follow_up"
    other = "other"


class ConsentPurpose(str, enum.Enum):
    commercial_contact = "commercial_contact"
    marketing = "marketing"
    data_sharing = "data_sharing"


class ConsentBasis(str, enum.Enum):
    consent = "consent"
    legitimate_interest = "legitimate_interest"
    contract = "contract"


def pg_enum(py_enum: type[enum.Enum], name: str) -> PGEnum:
    return PGEnum(py_enum, name=name, create_type=False)


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _ts() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def _updated_ts() -> Mapped[datetime]:
    # Mantido por trigger no banco (set_updated_at).
    return mapped_column(DateTime(timezone=True), server_default=func.now(), server_onupdate=FetchedValue())


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[UserRole] = mapped_column(pg_enum(UserRole, "user_role"), default=UserRole.sales_rep)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(SmallInteger, default=0)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    terms_accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    token_hash: Mapped[str] = mapped_column(CHAR(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    replaced_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("refresh_tokens.id"))
    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    ip_address: Mapped[Optional[str]] = mapped_column(INET)
    created_at: Mapped[datetime] = _ts()

    user: Mapped[User] = relationship()


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = _uuid_pk()
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    legal_name: Mapped[str] = mapped_column(String(200))
    trade_name: Mapped[Optional[str]] = mapped_column(String(200))
    cnpj: Mapped[Optional[str]] = mapped_column(CHAR(14), unique=True)
    industry: Mapped[Optional[str]] = mapped_column(String(100))
    size: Mapped[Optional[str]] = mapped_column(String(30))
    website: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(30))
    address_line: Mapped[Optional[str]] = mapped_column(String(255))
    city: Mapped[Optional[str]] = mapped_column(String(100))
    state: Mapped[Optional[str]] = mapped_column(CHAR(2))
    zip_code: Mapped[Optional[str]] = mapped_column(String(10))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = _uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    full_name: Mapped[str] = mapped_column(String(150))
    email: Mapped[Optional[str]] = mapped_column(CITEXT)
    phone: Mapped[Optional[str]] = mapped_column(String(30))
    job_title: Mapped[Optional[str]] = mapped_column(String(100))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    anonymized_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class ContactConsent(Base):
    __tablename__ = "contact_consents"

    id: Mapped[uuid.UUID] = _uuid_pk()
    contact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"))
    purpose: Mapped[ConsentPurpose] = mapped_column(pg_enum(ConsentPurpose, "consent_purpose"))
    basis: Mapped[ConsentBasis] = mapped_column(pg_enum(ConsentBasis, "consent_basis"), default=ConsentBasis.consent)
    granted: Mapped[bool] = mapped_column(Boolean)
    source: Mapped[Optional[str]] = mapped_column(String(100))
    evidence: Mapped[Optional[str]] = mapped_column(Text)
    recorded_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"))
    granted_at: Mapped[datetime] = _ts()
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class Pipeline(Base):
    __tablename__ = "pipelines"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(100), unique=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _ts()

    stages: Mapped[list["PipelineStage"]] = relationship(
        back_populates="pipeline", order_by="PipelineStage.position", lazy="selectin"
    )


class PipelineStage(Base):
    __tablename__ = "pipeline_stages"

    id: Mapped[uuid.UUID] = _uuid_pk()
    pipeline_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipelines.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(80))
    position: Mapped[int] = mapped_column(Integer)
    probability: Mapped[int] = mapped_column(SmallInteger, default=0)
    color: Mapped[str] = mapped_column(CHAR(7), default="#94A3B8")
    is_won: Mapped[bool] = mapped_column(Boolean, default=False)
    is_lost: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _ts()

    pipeline: Mapped[Pipeline] = relationship(back_populates="stages")


class Deal(Base):
    __tablename__ = "deals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["stage_id", "pipeline_id"],
            ["pipeline_stages.id", "pipeline_stages.pipeline_id"],
            name="fk_deal_stage_pipeline",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    pipeline_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    stage_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"))
    primary_contact_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(200))
    value: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    currency: Mapped[str] = mapped_column(CHAR(3), default="BRL")
    temperature: Mapped[LeadTemperature] = mapped_column(
        pg_enum(LeadTemperature, "lead_temperature"), default=LeadTemperature.cold
    )
    status: Mapped[DealStatus] = mapped_column(pg_enum(DealStatus, "deal_status"), default=DealStatus.open)
    position: Mapped[Decimal] = mapped_column(Numeric(20, 10), default=Decimal("0"))
    expected_close_date: Mapped[Optional[date]] = mapped_column(Date)
    next_action_type: Mapped[Optional[NextActionType]] = mapped_column(pg_enum(NextActionType, "next_action_type"))
    next_action_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    next_action_note: Mapped[Optional[str]] = mapped_column(String(255))
    stage_entered_at: Mapped[datetime] = _ts()
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    lost_reason: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    company: Mapped[Company] = relationship(lazy="joined", foreign_keys=[company_id])
    owner: Mapped[User] = relationship(lazy="joined", foreign_keys=[owner_id])
    primary_contact: Mapped[Optional[Contact]] = relationship(lazy="joined", foreign_keys=[primary_contact_id])


class DealStageHistory(Base):
    __tablename__ = "deal_stage_history"

    id: Mapped[uuid.UUID] = _uuid_pk()
    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"))
    from_stage_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("pipeline_stages.id"))
    to_stage_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_stages.id"))
    moved_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"))
    moved_at: Mapped[datetime] = _ts()


class Interaction(Base):
    __tablename__ = "interactions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"))
    contact_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    type: Mapped[InteractionType] = mapped_column(pg_enum(InteractionType, "interaction_type"))
    subject: Mapped[str] = mapped_column(String(200))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()

    user: Mapped[User] = relationship(lazy="joined")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(50))
    entity: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    details: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    ip_address: Mapped[Optional[str]] = mapped_column(INET)
    created_at: Mapped[datetime] = _ts()
