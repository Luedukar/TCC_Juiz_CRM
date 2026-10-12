from pydantic import BaseModel, Field, EmailStr, model_validator
from typing import Literal
from datetime import date, datetime
from decimal import Decimal

class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    workspace_id: int

class RefreshIn(BaseModel):
    refresh_token: str

class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    legal_name: str | None = Field(default=None, max_length=240)
    tax_id: str | None = Field(default=None, max_length=40)
    website: str | None = Field(default=None, max_length=500)
    industry: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    address: dict = Field(default_factory=dict)
    notes: str | None = None

class ContactCreate(BaseModel):
    company_id: int | None = None
    full_name: str = Field(min_length=1, max_length=180)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    job_title: str | None = Field(default=None, max_length=120)
    notes: str | None = None

class PipelineCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    is_default: bool = False

class StageCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    position: int = Field(ge=0)
    probability: Decimal = Field(default=0, ge=0, le=100)
    is_won: bool = False
    is_lost: bool = False

class OpportunityCreate(BaseModel):
    pipeline_id: int
    stage_id: int
    company_id: int | None = None
    primary_contact_id: int | None = None
    title: str = Field(min_length=1, max_length=220)
    amount: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="BRL", min_length=3, max_length=3)
    temperature: Literal["cold", "warm", "hot"] = "warm"
    expected_close_date: date | None = None
    next_action: str | None = Field(default=None, max_length=240)
    next_action_at: datetime | None = None

class OpportunityPatch(BaseModel):
    stage_id: int | None = None
    owner_user_id: int | None = None
    title: str | None = Field(default=None, min_length=1, max_length=220)
    amount: Decimal | None = Field(default=None, ge=0)
    temperature: Literal["cold", "warm", "hot"] | None = None
    status: Literal["open", "won", "lost"] | None = None
    expected_close_date: date | None = None
    next_action: str | None = Field(default=None, max_length=240)
    next_action_at: datetime | None = None
    lost_reason: str | None = None

    @model_validator(mode="after")
    def reject_null_for_required_fields(self):
        nullable = {"amount", "expected_close_date", "next_action", "next_action_at", "lost_reason"}
        invalid = [name for name in self.model_fields_set if name not in nullable and getattr(self, name) is None]
        if invalid:
            raise ValueError(f"Campos não podem ser nulos: {', '.join(invalid)}")
        return self

class InteractionCreate(BaseModel):
    contact_id: int | None = None
    kind: Literal["meeting", "email", "call", "note"]
    subject: str = Field(min_length=1, max_length=220)
    body: str | None = None
    occurred_at: datetime

class ConsentCreate(BaseModel):
    purpose: Literal["marketing", "communications", "data_processing"]
    granted: bool
    source: str = Field(min_length=1, max_length=160)


