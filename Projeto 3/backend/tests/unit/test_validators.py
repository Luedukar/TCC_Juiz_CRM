"""Validações dos schemas (sem banco)."""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas import (
    CompanyUpdate, DealCreate, DealUpdate, InteractionCreate, StageCreate, UserCreate, validate_cnpj,
)

import uuid


class TestCnpj:
    def test_valid_cnpj_is_normalized_to_digits(self):
        assert validate_cnpj("11.222.333/0001-81") == "11222333000181"

    def test_none_is_accepted(self):
        assert validate_cnpj(None) is None

    @pytest.mark.parametrize("value", ["11.222.333/0001-82", "00000000000000", "123", "abc", "11222333000181999"])
    def test_invalid_cnpj_is_rejected(self, value):
        with pytest.raises(ValueError):
            validate_cnpj(value)


class TestUserCreate:
    def test_accepts_strong_password(self):
        user = UserCreate(name="Ana Souza", email="ana@empresa.com", password="Senha-forte-123")
        assert user.role.value == "sales_rep"

    @pytest.mark.parametrize("password", ["curta1", "somenteletrasmuitolonga", "1234567890123"])
    def test_rejects_weak_password(self, password):
        with pytest.raises(ValidationError):
            UserCreate(name="Ana Souza", email="ana@empresa.com", password=password)

    def test_rejects_invalid_email(self):
        with pytest.raises(ValidationError):
            UserCreate(name="Ana", email="nao-e-email", password="Senha-forte-123")


class TestPartialUpdates:
    def test_explicit_null_on_required_field_is_rejected(self):
        with pytest.raises(ValidationError):
            DealUpdate(title=None)

    def test_explicit_null_on_optional_field_is_accepted(self):
        update = DealUpdate(next_action_at=None)
        assert "next_action_at" in update.model_fields_set

    def test_omitted_fields_are_not_set(self):
        assert DealUpdate(title="Novo título").model_fields_set == {"title"}

    def test_company_update_validates_cnpj(self):
        with pytest.raises(ValidationError):
            CompanyUpdate(cnpj="11222333000100")


class TestDealAndInteraction:
    def test_currency_is_uppercased(self):
        deal = DealCreate(title="Negócio", company_id=uuid.uuid4(), currency="usd")
        assert deal.currency == "USD"

    def test_invalid_currency_is_rejected(self):
        with pytest.raises(ValidationError):
            DealCreate(title="Negócio", company_id=uuid.uuid4(), currency="REAL")

    def test_negative_value_is_rejected(self):
        with pytest.raises(ValidationError):
            DealCreate(title="Negócio", company_id=uuid.uuid4(), value="-1")

    def test_interaction_requires_timezone(self):
        with pytest.raises(ValidationError):
            InteractionCreate(type="call", subject="Ligação", occurred_at=datetime(2026, 10, 9, 14, 30))

    def test_interaction_with_timezone_is_accepted(self):
        item = InteractionCreate(type="call", subject="Ligação", occurred_at=datetime(2026, 10, 9, 14, 30, tzinfo=timezone.utc))
        assert item.occurred_at.tzinfo is not None


class TestStage:
    def test_stage_cannot_be_won_and_lost(self):
        with pytest.raises(ValidationError):
            StageCreate(name="Etapa", is_won=True, is_lost=True)

    def test_color_must_be_hex(self):
        with pytest.raises(ValidationError):
            StageCreate(name="Etapa", color="vermelho")
