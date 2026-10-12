"""RBAC: o gestor vê tudo; o vendedor só interage com a própria carteira."""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models import AuditLog, NextActionType

from .conftest import API, error_code


@pytest.fixture
def world(manager, rep_a, rep_b, make_company, make_deal):
    company_a, company_b = make_company(rep_a, "Empresa A"), make_company(rep_b, "Empresa B")
    return SimpleNamespace(
        manager=manager, rep_a=rep_a, rep_b=rep_b, company_a=company_a, company_b=company_b,
        a1=make_deal(rep_a, company_a, "Prospecção", title="A1", value=1000),
        a2=make_deal(rep_a, company_a, "Proposta", title="A2", value=2500),
        b1=make_deal(rep_b, company_b, "Prospecção", title="B1", value=4000),
    )


def ids(items) -> set[str]:
    return {i["id"] for i in items}


class TestDealVisibility:
    def test_rep_lists_only_own_deals(self, client, auth, world):
        a = client.get(f"{API}/deals", headers=auth(world.rep_a)).json()
        b = client.get(f"{API}/deals", headers=auth(world.rep_b)).json()
        assert ids(a["items"]) == {str(world.a1.id), str(world.a2.id)} and a["total"] == 2
        assert ids(b["items"]) == {str(world.b1.id)} and b["total"] == 1

    def test_manager_lists_every_deal(self, client, auth, world):
        body = client.get(f"{API}/deals", headers=auth(world.manager)).json()
        assert body["total"] == 3

    def test_manager_can_filter_by_owner(self, client, auth, world):
        body = client.get(f"{API}/deals", headers=auth(world.manager), params={"owner_id": str(world.rep_b.id)}).json()
        assert ids(body["items"]) == {str(world.b1.id)}

    def test_rep_filtering_by_another_owner_gets_nothing(self, client, auth, world):
        body = client.get(f"{API}/deals", headers=auth(world.rep_a), params={"owner_id": str(world.rep_b.id)}).json()
        assert body["items"] == [] and body["total"] == 0

    def test_rep_gets_404_for_someone_elses_deal_same_as_nonexistent(self, client, auth, world):
        other = client.get(f"{API}/deals/{world.b1.id}", headers=auth(world.rep_a))
        missing = client.get(f"{API}/deals/{uuid.uuid4()}", headers=auth(world.rep_a))
        assert other.status_code == missing.status_code == 404
        assert error_code(other) == error_code(missing) == "not_found"  # não revela que o registro existe

    def test_manager_reads_any_deal(self, client, auth, world):
        assert client.get(f"{API}/deals/{world.b1.id}", headers=auth(world.manager)).status_code == 200

    def test_soft_deleted_deal_disappears_for_everyone(self, client, db, auth, world):
        assert client.delete(f"{API}/deals/{world.a1.id}", headers=auth(world.rep_a)).status_code == 204
        assert client.get(f"{API}/deals/{world.a1.id}", headers=auth(world.manager)).status_code == 404
        listed = client.get(f"{API}/deals", headers=auth(world.manager)).json()
        assert str(world.a1.id) not in ids(listed["items"])
        assert db.scalar(select(AuditLog).where(AuditLog.action == "delete", AuditLog.entity == "deal")) is not None


class TestBoardVisibility:
    def test_rep_board_contains_only_own_cards_and_totals(self, client, auth, world):
        board = client.get(f"{API}/deals/board", headers=auth(world.rep_a)).json()
        cards = [d for c in board["columns"] for d in c["deals"]]
        assert {d["title"] for d in cards} == {"A1", "A2"}
        assert sum(c["total_count"] for c in board["columns"]) == 2
        assert sum(float(c["total_value"]) for c in board["columns"]) == 3500.0

    def test_manager_board_contains_everything(self, client, auth, world):
        board = client.get(f"{API}/deals/board", headers=auth(world.manager)).json()
        assert sum(c["total_count"] for c in board["columns"]) == 3
        assert sum(float(c["total_value"]) for c in board["columns"]) == 7500.0

    def test_manager_board_can_be_narrowed_to_one_rep(self, client, auth, world):
        board = client.get(f"{API}/deals/board", headers=auth(world.manager), params={"owner_id": str(world.rep_b.id)}).json()
        assert [d["title"] for c in board["columns"] for d in c["deals"]] == ["B1"]

    def test_rep_cannot_widen_board_with_owner_filter(self, client, auth, world):
        board = client.get(f"{API}/deals/board", headers=auth(world.rep_a), params={"owner_id": str(world.rep_b.id)}).json()
        assert [d for c in board["columns"] for d in c["deals"]] == []
        assert sum(c["total_count"] for c in board["columns"]) == 0

    def test_board_exposes_stage_metadata_for_the_kanban(self, client, auth, world):
        columns = client.get(f"{API}/deals/board", headers=auth(world.rep_a)).json()["columns"]
        assert [c["stage"]["name"] for c in columns] == ["Prospecção", "Qualificação", "Proposta", "Negociação", "Ganho", "Perdido"]
        assert all(c["stage"]["color"].startswith("#") for c in columns)

    def test_requires_authentication(self, client):
        assert client.get(f"{API}/deals/board").status_code == 401


class TestWritesAreScoped:
    def test_rep_cannot_edit_or_delete_someone_elses_deal(self, client, auth, world):
        patch = client.patch(f"{API}/deals/{world.b1.id}", headers=auth(world.rep_a), json={"title": "invadido"})
        delete = client.delete(f"{API}/deals/{world.b1.id}", headers=auth(world.rep_a))
        assert patch.status_code == delete.status_code == 404
        assert client.get(f"{API}/deals/{world.b1.id}", headers=auth(world.manager)).json()["title"] == "B1"

    def test_rep_cannot_create_deal_in_someone_elses_company(self, client, auth, world):
        response = client.post(f"{API}/deals", headers=auth(world.rep_a), json={"title": "Intruso", "company_id": str(world.company_b.id)})
        assert response.status_code == 404

    def test_rep_creates_deal_in_own_portfolio(self, client, auth, world):
        response = client.post(f"{API}/deals", headers=auth(world.rep_a), json={"title": "Novo A", "company_id": str(world.company_a.id)})
        assert response.status_code == 201
        assert response.json()["owner"]["id"] == str(world.rep_a.id)

    def test_rep_cannot_assign_new_deal_to_another_rep(self, client, auth, world):
        body = {"title": "Presente", "company_id": str(world.company_a.id), "owner_id": str(world.rep_b.id)}
        assert client.post(f"{API}/deals", headers=auth(world.rep_a), json=body).status_code == 403

    def test_rep_cannot_transfer_own_deal(self, client, auth, world):
        response = client.patch(f"{API}/deals/{world.a1.id}", headers=auth(world.rep_a), json={"owner_id": str(world.rep_b.id)})
        assert response.status_code == 403

    def test_manager_creating_deal_defaults_to_company_owner(self, client, auth, world):
        response = client.post(f"{API}/deals", headers=auth(world.manager), json={"title": "Do gestor", "company_id": str(world.company_a.id)})
        assert response.status_code == 201 and response.json()["owner"]["id"] == str(world.rep_a.id)

    def test_manager_transfer_moves_visibility_between_reps(self, client, auth, world):
        response = client.patch(f"{API}/deals/{world.a1.id}", headers=auth(world.manager), json={"owner_id": str(world.rep_b.id)})
        assert response.status_code == 200
        assert client.get(f"{API}/deals/{world.a1.id}", headers=auth(world.rep_a)).status_code == 404
        assert client.get(f"{API}/deals/{world.a1.id}", headers=auth(world.rep_b)).status_code == 200

    def test_unknown_fields_cannot_change_ownership_implicitly(self, client, auth, world):
        client.patch(f"{API}/deals/{world.a1.id}", headers=auth(world.rep_a), json={"title": "ok", "created_by": str(world.rep_b.id)})
        assert client.get(f"{API}/deals/{world.a1.id}", headers=auth(world.rep_a)).json()["owner"]["id"] == str(world.rep_a.id)


class TestCompaniesAndContacts:
    def test_company_visibility(self, client, auth, world):
        listed = client.get(f"{API}/companies", headers=auth(world.rep_a)).json()
        assert ids(listed["items"]) == {str(world.company_a.id)}
        assert client.get(f"{API}/companies/{world.company_b.id}", headers=auth(world.rep_a)).status_code == 404
        assert client.get(f"{API}/companies", headers=auth(world.manager)).json()["total"] == 2

    def test_rep_cannot_assign_company_to_another_rep(self, client, auth, world):
        body = {"legal_name": "Nova Empresa", "owner_id": str(world.rep_b.id)}
        assert client.post(f"{API}/companies", headers=auth(world.rep_a), json=body).status_code == 403

    def test_contact_scoped_to_company_owner(self, client, auth, world, make_contact):
        contact = make_contact(world.rep_a, world.company_a, "Fulano")
        assert client.get(f"{API}/contacts/{contact.id}", headers=auth(world.rep_a)).status_code == 200
        assert client.get(f"{API}/contacts/{contact.id}", headers=auth(world.rep_b)).status_code == 404
        assert client.get(f"{API}/contacts", headers=auth(world.rep_b)).json()["total"] == 0
        assert client.get(f"{API}/contacts", headers=auth(world.manager)).json()["total"] == 1

    def test_rep_cannot_create_contact_in_someone_elses_company(self, client, auth, world):
        body = {"company_id": str(world.company_b.id), "full_name": "Intruso"}
        assert client.post(f"{API}/contacts", headers=auth(world.rep_a), json=body).status_code == 404

    def test_only_manager_can_anonymize_contact(self, client, auth, world, make_contact):
        contact = make_contact(world.rep_a, world.company_a, "Fulano", email="fulano@empresa.com", phone="11999999999")
        assert client.post(f"{API}/contacts/{contact.id}/anonymize", headers=auth(world.rep_a)).status_code == 403
        done = client.post(f"{API}/contacts/{contact.id}/anonymize", headers=auth(world.manager))
        assert done.status_code == 200
        body = done.json()
        assert body["email"] is None and body["phone"] is None and body["full_name"] != "Fulano" and body["anonymized_at"]
        edit = client.patch(f"{API}/contacts/{contact.id}", headers=auth(world.manager), json={"full_name": "Volta"})
        assert edit.status_code == 400 and error_code(edit) == "contact_anonymized"

    def test_consent_history_keeps_latest_decision_and_audit(self, client, db, auth, world, make_contact):
        contact = make_contact(world.rep_a, world.company_a)
        url = f"{API}/contacts/{contact.id}/consents"
        grant = {"purpose": "marketing", "granted": True, "source": "formulário"}
        assert client.post(url, headers=auth(world.rep_a), json=grant).status_code == 201
        assert client.post(url, headers=auth(world.rep_a), json={**grant, "granted": False}).status_code == 201
        history = client.get(url, headers=auth(world.rep_a)).json()
        assert [h["granted"] for h in history] == [False, True]  # mais recente primeiro
        assert history[1]["revoked_at"] is not None  # decisão anterior foi encerrada
        assert client.get(url, headers=auth(world.rep_b)).status_code == 404
        actions = {a.action for a in db.scalars(select(AuditLog)).all()}
        assert {"consent_granted", "consent_revoked"} <= actions


class TestInteractions:
    def payload(self, **extra):
        return {"type": "call", "subject": "Primeiro contato", "occurred_at": datetime.now(timezone.utc).isoformat(), **extra}

    def test_rep_cannot_read_or_write_interactions_of_others(self, client, auth, world):
        url = f"{API}/deals/{world.b1.id}/interactions"
        assert client.get(url, headers=auth(world.rep_a)).status_code == 404
        assert client.post(url, headers=auth(world.rep_a), json=self.payload()).status_code == 404

    def test_rep_registers_and_lists_own_interactions_in_reverse_chronological_order(self, client, auth, world):
        url = f"{API}/deals/{world.a1.id}/interactions"
        old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        client.post(url, headers=auth(world.rep_a), json=self.payload(subject="Antiga", occurred_at=old))
        client.post(url, headers=auth(world.rep_a), json=self.payload(subject="Recente"))
        items = client.get(url, headers=auth(world.rep_a)).json()["items"]
        assert [i["subject"] for i in items] == ["Recente", "Antiga"]
        assert items[0]["user"]["id"] == str(world.rep_a.id)

    def test_only_author_or_manager_can_change_an_interaction(self, client, auth, world):
        url = f"{API}/deals/{world.a1.id}/interactions"
        by_manager = client.post(url, headers=auth(world.manager), json=self.payload(subject="Do gestor")).json()["id"]
        by_rep = client.post(url, headers=auth(world.rep_a), json=self.payload(subject="Do vendedor")).json()["id"]

        assert client.patch(f"{API}/interactions/{by_manager}", headers=auth(world.rep_a), json={"subject": "x"}).status_code == 403
        assert client.delete(f"{API}/interactions/{by_manager}", headers=auth(world.rep_a)).status_code == 403
        assert client.patch(f"{API}/interactions/{by_rep}", headers=auth(world.manager), json={"subject": "Editado"}).status_code == 200
        assert client.patch(f"{API}/interactions/{by_rep}", headers=auth(world.rep_b), json={"subject": "x"}).status_code == 404

    def test_naive_datetime_is_rejected(self, client, auth, world):
        response = client.post(f"{API}/deals/{world.a1.id}/interactions", headers=auth(world.rep_a), json=self.payload(occurred_at="2026-10-09T14:30:00"))
        assert response.status_code == 422

    def test_contact_must_belong_to_the_deal_company(self, client, auth, world, make_contact):
        foreign = make_contact(world.rep_b, world.company_b)
        response = client.post(f"{API}/deals/{world.a1.id}/interactions", headers=auth(world.rep_a), json=self.payload(contact_id=str(foreign.id)))
        assert response.status_code == 400 and error_code(response) == "contact_company_mismatch"


class TestNextActions:
    def test_overdue_actions_are_scoped_and_flagged(self, client, auth, world, make_deal, db):
        past = datetime.now(timezone.utc) - timedelta(hours=3)
        for deal in (world.a1, world.b1):
            deal.next_action_type, deal.next_action_at = NextActionType.call, past
        db.commit()
        rep = client.get(f"{API}/deals/next-actions", headers=auth(world.rep_a)).json()
        assert [d["title"] for d in rep] == ["A1"] and rep[0]["next_action_overdue"] is True
        assert len(client.get(f"{API}/deals/next-actions", headers=auth(world.manager)).json()) == 2

    def test_future_actions_outside_window_are_not_listed(self, client, auth, world, db):
        world.a1.next_action_type = NextActionType.meeting
        world.a1.next_action_at = datetime.now(timezone.utc) + timedelta(days=5)
        db.commit()
        assert client.get(f"{API}/deals/next-actions", headers=auth(world.rep_a), params={"window_hours": 24}).json() == []
        assert len(client.get(f"{API}/deals/next-actions", headers=auth(world.rep_a), params={"window_hours": 24 * 6}).json()) == 1


MANAGER_ONLY = [
    ("GET", "/users", None),
    ("POST", "/users", {"name": "X Y", "email": "x@y.com", "password": "Senha-forte-123"}),
    ("PATCH", "/users/{uid}", {"name": "Novo"}),
    ("POST", "/pipelines", {"name": "Novo funil"}),
    ("PATCH", "/pipelines/{uid}", {"name": "Renomeado"}),
    ("POST", "/pipelines/{uid}/stages", {"name": "Etapa"}),
    ("PUT", "/pipelines/{uid}/stages/order", {"stage_ids": [str(uuid.uuid4())]}),
    ("PATCH", "/stages/{uid}", {"name": "Etapa"}),
    ("DELETE", "/stages/{uid}", None),
    ("POST", "/contacts/{uid}/anonymize", None),
]

PROTECTED = [
    ("GET", "/auth/me"), ("GET", "/deals"), ("GET", "/deals/board"), ("GET", "/deals/next-actions"),
    ("GET", "/companies"), ("GET", "/contacts"), ("GET", "/pipelines"), ("GET", "/users"),
    ("POST", "/deals"), ("POST", "/companies"), ("POST", "/contacts"),
]


class TestEndpointMatrix:
    @pytest.mark.parametrize("method,path,body", MANAGER_ONLY)
    def test_manager_only_endpoints_reject_reps(self, client, auth, rep_a, method, path, body):
        response = client.request(method, API + path.format(uid=uuid.uuid4()), headers=auth(rep_a), json=body)
        assert response.status_code == 403, f"{method} {path} deveria ser exclusivo do gestor"
        assert error_code(response) == "forbidden"

    @pytest.mark.parametrize("method,path", PROTECTED)
    def test_protected_endpoints_require_authentication(self, client, method, path):
        assert client.request(method, API + path).status_code == 401

    def test_rep_can_read_pipelines(self, client, auth, rep_a):
        response = client.get(f"{API}/pipelines", headers=auth(rep_a))
        assert response.status_code == 200 and response.json()[0]["is_default"] is True
