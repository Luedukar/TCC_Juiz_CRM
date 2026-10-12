import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UserCreate(InputModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=256)
    role: Literal["sales_manager", "sales_rep"] = "sales_rep"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    email: str
    role: str
    is_active: bool


class LoginInput(InputModel):
    email: str
    password: str


class RefreshInput(InputModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class CompanyCreate(InputModel):
    name: str = Field(min_length=1, max_length=300)
    legal_name: str | None = None
    tax_id: str | None = None
    website: str | None = None
    industry: str | None = None
    phone: str | None = None
    address: dict = Field(default_factory=dict)


class CompanyUpdate(InputModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    legal_name: str | None = None
    tax_id: str | None = None
    website: str | None = None
    industry: str | None = None
    phone: str | None = None
    address: dict | None = None


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    legal_name: str | None
    tax_id: str | None
    website: str | None
    industry: str | None
    phone: str | None
    address: dict
    owner_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ContactCreate(InputModel):
    company_id: uuid.UUID | None = None
    first_name: str = Field(min_length=1, max_length=200)
    last_name: str = Field(min_length=1, max_length=200)
    email: str | None = None
    phone: str | None = None
    job_title: str | None = None


class ContactUpdate(InputModel):
    company_id: uuid.UUID | None = None
    first_name: str | None = Field(default=None, min_length=1, max_length=200)
    last_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = None
    phone: str | None = None
    job_title: str | None = None


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID | None
    owner_id: uuid.UUID
    first_name: str
    last_name: str
    email: str | None
    phone: str | None
    job_title: str | None
    created_at: datetime
    updated_at: datetime


class PipelineCreate(InputModel):
    name: str = Field(min_length=1, max_length=200)
    is_default: bool = False


class PipelineUpdate(InputModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    is_default: bool | None = None


class PipelineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    is_default: bool
    created_by: uuid.UUID


class StageCreate(InputModel):
    name: str = Field(min_length=1, max_length=200)
    position: int = Field(ge=0)
    probability: int = Field(default=0, ge=0, le=100)
    is_won: bool = False
    is_lost: bool = False


class StageUpdate(InputModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    probability: int | None = Field(default=None, ge=0, le=100)
    is_won: bool | None = None
    is_lost: bool | None = None


class StageReorder(InputModel):
    stage_ids: list[uuid.UUID] = Field(min_length=1)


class StageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pipeline_id: uuid.UUID
    name: str
    position: int
    probability: int
    is_won: bool
    is_lost: bool


class DealCreate(InputModel):
    pipeline_id: uuid.UUID
    stage_id: uuid.UUID
    company_id: uuid.UUID | None = None
    primary_contact_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=300)
    amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    temperature: Literal["cold", "warm", "hot"] = "warm"
    expected_close_date: date | None = None
    next_action: str | None = None
    next_action_at: datetime | None = None


class DealUpdate(InputModel):
    company_id: uuid.UUID | None = None
    primary_contact_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=300)
    amount: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    temperature: Literal["cold", "warm", "hot"] | None = None
    expected_close_date: date | None = None
    next_action: str | None = None
    next_action_at: datetime | None = None
    lost_reason: str | None = None


class DealMove(InputModel):
    stage_id: uuid.UUID


class DealOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pipeline_id: uuid.UUID
    stage_id: uuid.UUID
    company_id: uuid.UUID | None
    primary_contact_id: uuid.UUID | None
    owner_id: uuid.UUID
    title: str
    amount: Decimal
    currency: str
    temperature: str
    expected_close_date: date | None
    next_action: str | None
    next_action_at: datetime | None
    lost_reason: str | None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None


class InteractionCreate(InputModel):
    contact_id: uuid.UUID | None = None
    type: Literal["meeting", "email", "call"]
    subject: str = Field(min_length=1, max_length=300)
    notes: str | None = None
    occurred_at: datetime
    duration_minutes: int | None = Field(default=None, ge=0)


class InteractionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    deal_id: uuid.UUID
    contact_id: uuid.UUID | None
    created_by: uuid.UUID
    type: str
    subject: str
    notes: str | None
    occurred_at: datetime
    duration_minutes: int | None
    created_at: datetime


class ConsentCreate(InputModel):
    purpose: str = Field(min_length=1, max_length=300)
    status: Literal["granted", "withdrawn"]
    legal_basis: str | None = None
    source: str | None = None


class ConsentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    contact_id: uuid.UUID
    purpose: str
    status: str
    legal_basis: str | None
    source: str | None
    recorded_by: uuid.UUID | None
    recorded_at: datetime
