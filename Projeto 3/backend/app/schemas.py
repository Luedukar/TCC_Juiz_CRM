import re
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import ClassVar, Generic, Optional, TypeVar

from pydantic import (
    BaseModel, ConfigDict, EmailStr, Field, computed_field, field_validator, model_validator,
)

from app.models import (
    ConsentBasis, ConsentPurpose, DealStatus, InteractionType, LeadTemperature,
    NextActionType, UserRole,
)

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class PartialUpdate(BaseModel):
    """Base de PATCH: campos obrigatórios no banco não aceitam null explícito."""

    NON_NULLABLE: ClassVar[set[str]] = set()

    @model_validator(mode="after")
    def reject_explicit_nulls(self):
        for name in self.model_fields_set & self.NON_NULLABLE:
            if getattr(self, name) is None:
                raise ValueError(f"O campo '{name}' não pode ser nulo.")
        return self


# ---------------------------------------------------------------- Auth / usuários
class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=200)


class UserOut(ORMModel):
    id: uuid.UUID
    name: str
    email: str
    role: UserRole
    is_active: bool
    last_login_at: Optional[datetime]
    terms_accepted_at: Optional[datetime]


class UserRef(ORMModel):
    id: uuid.UUID
    name: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class LoginOut(TokenPair):
    user: UserOut


def _check_password_strength(value: str) -> str:
    if len(value) < 10:
        raise ValueError("A senha deve ter pelo menos 10 caracteres.")
    if not (re.search(r"[A-Za-z]", value) and re.search(r"\d", value)):
        raise ValueError("A senha deve conter letras e números.")
    return value


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    password: str = Field(max_length=128)
    role: UserRole = UserRole.sales_rep

    check_pw = field_validator("password")(_check_password_strength)


class UserUpdate(PartialUpdate):
    NON_NULLABLE: ClassVar[set[str]] = {"name", "role", "is_active", "password"}

    name: Optional[str] = Field(default=None, min_length=2, max_length=150)
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, max_length=128)

    @field_validator("password")
    @classmethod
    def check_pw(cls, v):
        return v if v is None else _check_password_strength(v)


# ---------------------------------------------------------------- Empresas
def validate_cnpj(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    digits = re.sub(r"\D", "", value)
    if len(digits) != 14 or len(set(digits)) == 1:
        raise ValueError("CNPJ inválido.")

    def check_digit(base: str, weights: list[int]) -> str:
        total = sum(int(d) * w for d, w in zip(base, weights))
        rest = total % 11
        return "0" if rest < 2 else str(11 - rest)

    d1 = check_digit(digits[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    d2 = check_digit(digits[:12] + d1, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    if digits[12:] != d1 + d2:
        raise ValueError("CNPJ inválido.")
    return digits


class CompanyFields(BaseModel):
    legal_name: str = Field(min_length=2, max_length=200)
    trade_name: Optional[str] = Field(default=None, max_length=200)
    cnpj: Optional[str] = None
    industry: Optional[str] = Field(default=None, max_length=100)
    size: Optional[str] = Field(default=None, max_length=30)
    website: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=30)
    address_line: Optional[str] = Field(default=None, max_length=255)
    city: Optional[str] = Field(default=None, max_length=100)
    state: Optional[str] = Field(default=None, min_length=2, max_length=2)
    zip_code: Optional[str] = Field(default=None, max_length=10)
    notes: Optional[str] = None

    check_cnpj = field_validator("cnpj")(validate_cnpj)

    @field_validator("state")
    @classmethod
    def upper_state(cls, v):
        return v.upper() if v else v


class CompanyCreate(CompanyFields):
    owner_id: Optional[uuid.UUID] = None


class CompanyUpdate(PartialUpdate):
    NON_NULLABLE: ClassVar[set[str]] = {"legal_name", "owner_id"}

    legal_name: Optional[str] = Field(default=None, min_length=2, max_length=200)
    trade_name: Optional[str] = Field(default=None, max_length=200)
    cnpj: Optional[str] = None
    industry: Optional[str] = Field(default=None, max_length=100)
    size: Optional[str] = Field(default=None, max_length=30)
    website: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=30)
    address_line: Optional[str] = Field(default=None, max_length=255)
    city: Optional[str] = Field(default=None, max_length=100)
    state: Optional[str] = Field(default=None, min_length=2, max_length=2)
    zip_code: Optional[str] = Field(default=None, max_length=10)
    notes: Optional[str] = None
    owner_id: Optional[uuid.UUID] = None

    check_cnpj = field_validator("cnpj")(validate_cnpj)


class CompanyOut(ORMModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    legal_name: str
    trade_name: Optional[str]
    cnpj: Optional[str]
    industry: Optional[str]
    size: Optional[str]
    website: Optional[str]
    phone: Optional[str]
    address_line: Optional[str]
    city: Optional[str]
    state: Optional[str]
    zip_code: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime


class CompanyRef(ORMModel):
    id: uuid.UUID
    legal_name: str
    trade_name: Optional[str]


# ---------------------------------------------------------------- Contatos
class ContactCreate(BaseModel):
    company_id: uuid.UUID
    full_name: str = Field(min_length=2, max_length=150)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=30)
    job_title: Optional[str] = Field(default=None, max_length=100)
    is_primary: bool = False
    notes: Optional[str] = None
    owner_id: Optional[uuid.UUID] = None


class ContactUpdate(PartialUpdate):
    NON_NULLABLE: ClassVar[set[str]] = {"full_name", "is_primary", "owner_id"}

    full_name: Optional[str] = Field(default=None, min_length=2, max_length=150)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=30)
    job_title: Optional[str] = Field(default=None, max_length=100)
    is_primary: Optional[bool] = None
    notes: Optional[str] = None
    owner_id: Optional[uuid.UUID] = None


class ContactOut(ORMModel):
    id: uuid.UUID
    company_id: uuid.UUID
    owner_id: uuid.UUID
    full_name: str
    email: Optional[str]
    phone: Optional[str]
    job_title: Optional[str]
    is_primary: bool
    notes: Optional[str]
    anonymized_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class ContactRef(ORMModel):
    id: uuid.UUID
    full_name: str
    email: Optional[str]
    phone: Optional[str]


class ConsentIn(BaseModel):
    purpose: ConsentPurpose
    basis: ConsentBasis = ConsentBasis.consent
    granted: bool
    source: Optional[str] = Field(default=None, max_length=100)
    evidence: Optional[str] = None


class ConsentOut(ORMModel):
    id: uuid.UUID
    contact_id: uuid.UUID
    purpose: ConsentPurpose
    basis: ConsentBasis
    granted: bool
    source: Optional[str]
    evidence: Optional[str]
    granted_at: datetime
    revoked_at: Optional[datetime]


# ---------------------------------------------------------------- Funil
HEX_COLOR = r"^#[0-9A-Fa-f]{6}$"


class StageCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    probability: int = Field(default=0, ge=0, le=100)
    color: str = Field(default="#94A3B8", pattern=HEX_COLOR)
    is_won: bool = False
    is_lost: bool = False

    @model_validator(mode="after")
    def not_both(self):
        if self.is_won and self.is_lost:
            raise ValueError("Uma etapa não pode ser de ganho e de perda ao mesmo tempo.")
        return self


class StageUpdate(PartialUpdate):
    NON_NULLABLE: ClassVar[set[str]] = {"name", "probability", "color", "is_won", "is_lost"}

    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    probability: Optional[int] = Field(default=None, ge=0, le=100)
    color: Optional[str] = Field(default=None, pattern=HEX_COLOR)
    is_won: Optional[bool] = None
    is_lost: Optional[bool] = None


class StageReorder(BaseModel):
    stage_ids: list[uuid.UUID] = Field(min_length=1)


class StageOut(ORMModel):
    id: uuid.UUID
    pipeline_id: uuid.UUID
    name: str
    position: int
    probability: int
    color: str
    is_won: bool
    is_lost: bool


class PipelineCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    is_default: bool = False


class PipelineUpdate(PartialUpdate):
    NON_NULLABLE: ClassVar[set[str]] = {"name", "is_default"}

    name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    is_default: Optional[bool] = None


class PipelineOut(ORMModel):
    id: uuid.UUID
    name: str
    is_default: bool
    stages: list[StageOut]


# ---------------------------------------------------------------- Negócios
def _currency(v: str) -> str:
    v = v.upper()
    if not re.fullmatch(r"[A-Z]{3}", v):
        raise ValueError("Moeda deve ter 3 letras (ex.: BRL).")
    return v


class DealCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    company_id: uuid.UUID
    primary_contact_id: Optional[uuid.UUID] = None
    stage_id: Optional[uuid.UUID] = None  # padrão: 1ª etapa do funil padrão
    owner_id: Optional[uuid.UUID] = None
    value: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    currency: str = "BRL"
    temperature: LeadTemperature = LeadTemperature.cold
    expected_close_date: Optional[date] = None
    next_action_type: Optional[NextActionType] = None
    next_action_at: Optional[datetime] = None
    next_action_note: Optional[str] = Field(default=None, max_length=255)

    check_cur = field_validator("currency")(_currency)


class DealUpdate(PartialUpdate):
    """Edição rápida (formulário lateral). Mudança de etapa usa POST /deals/{id}/move."""

    NON_NULLABLE: ClassVar[set[str]] = {"title", "value", "currency", "temperature", "owner_id", "company_id"}

    title: Optional[str] = Field(default=None, min_length=2, max_length=200)
    company_id: Optional[uuid.UUID] = None
    primary_contact_id: Optional[uuid.UUID] = None
    owner_id: Optional[uuid.UUID] = None
    value: Optional[Decimal] = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    currency: Optional[str] = None
    temperature: Optional[LeadTemperature] = None
    expected_close_date: Optional[date] = None
    next_action_type: Optional[NextActionType] = None
    next_action_at: Optional[datetime] = None
    next_action_note: Optional[str] = Field(default=None, max_length=255)

    @field_validator("currency")
    @classmethod
    def check_cur(cls, v):
        return v if v is None else _currency(v)


class DealMove(BaseModel):
    stage_id: uuid.UUID
    # Posição na coluna de destino: ids dos cards vizinhos (acima/abaixo do ponto de soltura).
    above_id: Optional[uuid.UUID] = None
    below_id: Optional[uuid.UUID] = None
    lost_reason: Optional[str] = Field(default=None, max_length=255)


class DealOut(ORMModel):
    id: uuid.UUID
    pipeline_id: uuid.UUID
    stage_id: uuid.UUID
    title: str
    value: Decimal
    currency: str
    temperature: LeadTemperature
    status: DealStatus
    position: Decimal
    expected_close_date: Optional[date]
    next_action_type: Optional[NextActionType]
    next_action_at: Optional[datetime]
    next_action_note: Optional[str]
    stage_entered_at: datetime
    closed_at: Optional[datetime]
    lost_reason: Optional[str]
    created_at: datetime
    updated_at: datetime
    company: CompanyRef
    owner: UserRef
    primary_contact: Optional[ContactRef]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def next_action_overdue(self) -> bool:
        return (
            self.status == DealStatus.open
            and self.next_action_at is not None
            and self.next_action_at < datetime.now(timezone.utc)
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def days_in_stage(self) -> int:
        return max(0, (datetime.now(timezone.utc) - self.stage_entered_at).days)


class BoardColumn(BaseModel):
    stage: StageOut
    total_count: int
    total_value: Decimal
    deals: list[DealOut]


class Board(BaseModel):
    pipeline_id: uuid.UUID
    pipeline_name: str
    columns: list[BoardColumn]
    generated_at: datetime


# ---------------------------------------------------------------- Interações
def _require_tz(v: Optional[datetime]) -> Optional[datetime]:
    if v is not None and v.tzinfo is None:
        raise ValueError("Informe data e hora com fuso horário (ex.: 2026-10-09T14:30:00-03:00).")
    return v


class InteractionCreate(BaseModel):
    type: InteractionType
    subject: str = Field(min_length=2, max_length=200)
    notes: Optional[str] = None
    occurred_at: datetime
    duration_minutes: Optional[int] = Field(default=None, ge=0, le=1440)
    contact_id: Optional[uuid.UUID] = None

    check_tz = field_validator("occurred_at")(_require_tz)


class InteractionUpdate(PartialUpdate):
    NON_NULLABLE: ClassVar[set[str]] = {"type", "subject", "occurred_at"}

    type: Optional[InteractionType] = None
    subject: Optional[str] = Field(default=None, min_length=2, max_length=200)
    notes: Optional[str] = None
    occurred_at: Optional[datetime] = None
    duration_minutes: Optional[int] = Field(default=None, ge=0, le=1440)
    contact_id: Optional[uuid.UUID] = None

    check_tz = field_validator("occurred_at")(_require_tz)


class InteractionOut(ORMModel):
    id: uuid.UUID
    deal_id: uuid.UUID
    contact_id: Optional[uuid.UUID]
    type: InteractionType
    subject: str
    notes: Optional[str]
    occurred_at: datetime
    duration_minutes: Optional[int]
    created_at: datetime
    user: UserRef
