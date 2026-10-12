"""Regras de RBAC em nível de consulta e atribuição (sem banco)."""
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.deps import is_manager, resolve_owner_id, scope_owned
from app.errors import Forbidden, NotFound
from app.models import Deal, UserRole


def user(role: UserRole):
    return SimpleNamespace(id=uuid.uuid4(), role=role)


class FakeDb:
    def __init__(self, found=None):
        self.found = found

    def get(self, model, pk):
        return self.found


class TestScope:
    def test_manager_query_has_no_owner_filter(self):
        stmt = scope_owned(select(Deal), Deal, user(UserRole.sales_manager))
        assert "owner_id" not in str(stmt)

    def test_rep_query_is_restricted_to_own_portfolio(self):
        rep = user(UserRole.sales_rep)
        stmt = scope_owned(select(Deal), Deal, rep)
        assert "deals.owner_id" in str(stmt)
        assert rep.id in stmt.compile().params.values()

    def test_is_manager(self):
        assert is_manager(user(UserRole.sales_manager)) is True
        assert is_manager(user(UserRole.sales_rep)) is False


class TestResolveOwner:
    def test_defaults_to_current_user(self):
        rep = user(UserRole.sales_rep)
        assert resolve_owner_id(FakeDb(), None, rep) == rep.id

    def test_uses_explicit_default_when_given(self):
        manager, default = user(UserRole.sales_manager), uuid.uuid4()
        assert resolve_owner_id(FakeDb(), None, manager, default=default) == default

    def test_rep_can_assign_to_self(self):
        rep = user(UserRole.sales_rep)
        assert resolve_owner_id(FakeDb(SimpleNamespace(is_active=True)), rep.id, rep) == rep.id

    def test_rep_cannot_assign_to_someone_else(self):
        with pytest.raises(Forbidden):
            resolve_owner_id(FakeDb(SimpleNamespace(is_active=True)), uuid.uuid4(), user(UserRole.sales_rep))

    def test_manager_can_assign_to_active_user(self):
        target = uuid.uuid4()
        result = resolve_owner_id(FakeDb(SimpleNamespace(is_active=True)), target, user(UserRole.sales_manager))
        assert result == target

    def test_manager_cannot_assign_to_inactive_or_missing_user(self):
        manager = user(UserRole.sales_manager)
        with pytest.raises(NotFound):
            resolve_owner_id(FakeDb(SimpleNamespace(is_active=False)), uuid.uuid4(), manager)
        with pytest.raises(NotFound):
            resolve_owner_id(FakeDb(None), uuid.uuid4(), manager)
