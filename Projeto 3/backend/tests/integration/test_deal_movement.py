"""Movimentação de cards no Kanban: etapa, posição, histórico e permissões."""
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models import AuditLog, DealStageHistory, DealStatus

from .conftest import API, board_titles, error_code


@pytest.fixture
def column(rep_a, make_company, make_deal):
    """Três cards na mesma coluna (Prospecção): D1, D2, D3, nessa ordem."""
    company = make_company(rep_a)
    deals = [make_deal(rep_a, company, "Prospecção", title=f"D{i}") for i in (1, 2, 3)]
    return SimpleNamespace(company=company, d1=deals[0], d2=deals[1], d3=deals[2])


def move(client, headers, deal, stage, **body):
    return client.post(f"{API}/deals/{deal.id}/move", headers=headers, json={"stage_id": str(stage.id), **body})


def history(db, deal):
    db.expire_all()
    return db.scalars(select(DealStageHistory).where(DealStageHistory.deal_id == deal.id).order_by(DealStageHistory.moved_at)).all()


class TestChangingStage:
    def test_card_moves_to_the_target_column(self, client, auth, rep_a, column, stages):
        response = move(client, auth(rep_a), column.d1, stages["Qualificação"])
        assert response.status_code == 200
        assert response.json()["stage_id"] == str(stages["Qualificação"].id)
        titles = board_titles(client, auth(rep_a))
        assert titles["Qualificação"] == ["D1"] and titles["Prospecção"] == ["D2", "D3"]

    def test_history_records_origin_destination_and_author(self, client, db, auth, rep_a, column, stages):
        move(client, auth(rep_a), column.d1, stages["Qualificação"])
        rows = history(db, column.d1)
        assert len(rows) == 1
        assert rows[0].from_stage_id == stages["Prospecção"].id and rows[0].to_stage_id == stages["Qualificação"].id
        assert rows[0].moved_by == rep_a.id  # preenchido pelo trigger via set_config

    def test_move_is_audited(self, client, db, auth, rep_a, column, stages):
        move(client, auth(rep_a), column.d1, stages["Qualificação"])
        assert db.scalar(select(AuditLog).where(AuditLog.action == "move", AuditLog.entity_id == column.d1.id)) is not None

    def test_stage_entered_at_changes_only_when_the_stage_changes(self, client, db, auth, rep_a, column, stages):
        before = client.get(f"{API}/deals/{column.d1.id}", headers=auth(rep_a)).json()["stage_entered_at"]
        move(client, auth(rep_a), column.d1, stages["Prospecção"], below_id=str(column.d3.id))  # só reordena
        same = client.get(f"{API}/deals/{column.d1.id}", headers=auth(rep_a)).json()["stage_entered_at"]
        assert same == before and history(db, column.d1) == []
        move(client, auth(rep_a), column.d1, stages["Proposta"])
        changed = client.get(f"{API}/deals/{column.d1.id}", headers=auth(rep_a)).json()["stage_entered_at"]
        assert changed != before


class TestWonAndLost:
    def test_moving_to_won_closes_the_deal(self, client, auth, rep_a, column, stages):
        body = move(client, auth(rep_a), column.d1, stages["Ganho"]).json()
        assert body["status"] == "won" and body["closed_at"] is not None and body["lost_reason"] is None

    def test_moving_to_lost_requires_a_reason(self, client, db, auth, rep_a, column, stages):
        response = move(client, auth(rep_a), column.d1, stages["Perdido"])
        assert response.status_code == 400 and error_code(response) == "lost_reason_required"
        db.expire_all()
        assert history(db, column.d1) == []  # nada foi alterado

    def test_blank_reason_is_not_accepted(self, client, auth, rep_a, column, stages):
        assert move(client, auth(rep_a), column.d1, stages["Perdido"], lost_reason="   ").status_code == 400

    def test_moving_to_lost_with_reason(self, client, auth, rep_a, column, stages):
        body = move(client, auth(rep_a), column.d1, stages["Perdido"], lost_reason="Optou pelo concorrente").json()
        assert body["status"] == "lost" and body["lost_reason"] == "Optou pelo concorrente" and body["closed_at"]

    def test_reopening_clears_closing_data(self, client, auth, rep_a, column, stages):
        move(client, auth(rep_a), column.d1, stages["Perdido"], lost_reason="Sem orçamento")
        body = move(client, auth(rep_a), column.d1, stages["Negociação"]).json()
        assert body["status"] == "open" and body["closed_at"] is None and body["lost_reason"] is None

    def test_cannot_create_deal_directly_in_closed_stage(self, client, auth, rep_a, column, stages):
        body = {"title": "Já fechado", "company_id": str(column.company.id), "stage_id": str(stages["Ganho"].id)}
        response = client.post(f"{API}/deals", headers=auth(rep_a), json=body)
        assert response.status_code == 400 and error_code(response) == "closed_stage"


class TestOrderingInsideAColumn:
    def test_drop_between_two_cards(self, client, auth, rep_a, column, stages):
        response = move(client, auth(rep_a), column.d3, stages["Prospecção"], above_id=str(column.d1.id), below_id=str(column.d2.id))
        assert response.status_code == 200
        assert Decimal(response.json()["position"]) == Decimal(1536)
        assert board_titles(client, auth(rep_a))["Prospecção"] == ["D1", "D3", "D2"]

    def test_drop_at_top(self, client, auth, rep_a, column, stages):
        move(client, auth(rep_a), column.d3, stages["Prospecção"], below_id=str(column.d1.id))
        assert board_titles(client, auth(rep_a))["Prospecção"] == ["D3", "D1", "D2"]

    def test_drop_at_bottom(self, client, auth, rep_a, column, stages):
        move(client, auth(rep_a), column.d1, stages["Prospecção"], above_id=str(column.d3.id))
        assert board_titles(client, auth(rep_a))["Prospecção"] == ["D2", "D3", "D1"]

    def test_drop_without_neighbors_appends_to_the_end(self, client, auth, rep_a, column, stages):
        move(client, auth(rep_a), column.d1, stages["Prospecção"])
        assert board_titles(client, auth(rep_a))["Prospecção"] == ["D2", "D3", "D1"]

    def test_drop_into_empty_column(self, client, auth, rep_a, column, stages):
        body = move(client, auth(rep_a), column.d2, stages["Negociação"]).json()
        assert Decimal(body["position"]) == Decimal(1024)

    def test_drop_between_cards_of_another_column(self, client, auth, rep_a, column, stages, make_deal):
        e1 = make_deal(rep_a, column.company, "Proposta", title="E1")
        e2 = make_deal(rep_a, column.company, "Proposta", title="E2")
        move(client, auth(rep_a), column.d1, stages["Proposta"], above_id=str(e1.id), below_id=str(e2.id))
        assert board_titles(client, auth(rep_a))["Proposta"] == ["E1", "D1", "E2"]

    def test_column_is_rebalanced_when_neighbors_are_too_close(self, client, db, auth, rep_a, make_company, make_deal, stages):
        company = make_company(rep_a)
        d1 = make_deal(rep_a, company, "Prospecção", title="D1", position=1)
        d2 = make_deal(rep_a, company, "Prospecção", title="D2", position=Decimal("1.0000010000"))
        d3 = make_deal(rep_a, company, "Prospecção", title="D3", position=5)
        response = move(client, auth(rep_a), d3, stages["Prospecção"], above_id=str(d1.id), below_id=str(d2.id))
        assert response.status_code == 200
        assert board_titles(client, auth(rep_a))["Prospecção"] == ["D1", "D3", "D2"]

    def test_many_consecutive_inserts_keep_a_strict_order(self, client, auth, rep_a, column, stages, make_deal):
        """Inserir sempre logo abaixo do mesmo card (pior caso) força o rebalanceamento e nunca corrompe a ordem."""
        top, bottom = column.d1, column.d2
        inserted = []
        for i in range(35):  # 1024 / 2**30 < intervalo mínimo: o rebalanceamento ocorre no meio do laço
            card = make_deal(rep_a, column.company, "Qualificação", title=f"Q{i}")
            move(client, auth(rep_a), card, stages["Prospecção"], above_id=str(top.id), below_id=str(bottom.id))
            inserted.append(card.title)
            bottom = card  # cada novo card entra logo abaixo de D1, apertando o intervalo
        order = board_titles(client, auth(rep_a))["Prospecção"]
        assert order[0] == "D1" and order[1] == "Q34" and order[-2:] == ["D2", "D3"]
        assert sorted(order) == sorted(["D1", "D2", "D3", *inserted])


class TestInvalidMoves:
    def test_neighbor_from_another_column_is_rejected(self, client, auth, rep_a, column, stages, make_deal):
        outsider = make_deal(rep_a, column.company, "Proposta", title="Fora")
        response = move(client, auth(rep_a), column.d1, stages["Prospecção"], above_id=str(outsider.id))
        assert response.status_code == 400 and error_code(response) == "invalid_neighbor"

    def test_card_cannot_be_its_own_neighbor(self, client, auth, rep_a, column, stages):
        response = move(client, auth(rep_a), column.d1, stages["Prospecção"], above_id=str(column.d1.id))
        assert response.status_code == 400 and error_code(response) == "invalid_neighbor"

    def test_neighbors_in_wrong_order_are_rejected(self, client, auth, rep_a, column, stages):
        response = move(client, auth(rep_a), column.d3, stages["Prospecção"], above_id=str(column.d2.id), below_id=str(column.d1.id))
        assert response.status_code == 400 and error_code(response) == "invalid_neighbor"

    def test_stage_from_another_pipeline_is_rejected(self, client, db, auth, manager, rep_a, column):
        pipeline = client.post(f"{API}/pipelines", headers=auth(manager), json={"name": "Outro funil"}).json()
        stage = client.post(f"{API}/pipelines/{pipeline['id']}/stages", headers=auth(manager), json={"name": "Lá"}).json()
        response = client.post(f"{API}/deals/{column.d1.id}/move", headers=auth(rep_a), json={"stage_id": stage["id"]})
        assert response.status_code == 400 and error_code(response) == "stage_pipeline_mismatch"

    def test_unknown_stage(self, client, auth, rep_a, column):
        import uuid

        response = client.post(f"{API}/deals/{column.d1.id}/move", headers=auth(rep_a), json={"stage_id": str(uuid.uuid4())})
        assert response.status_code == 400 and error_code(response) == "stage_not_found"

    def test_invalid_payload(self, client, auth, rep_a, column):
        assert client.post(f"{API}/deals/{column.d1.id}/move", headers=auth(rep_a), json={"stage_id": "nao-e-uuid"}).status_code == 422


class TestMovePermissions:
    def test_rep_cannot_move_someone_elses_card(self, client, auth, rep_a, rep_b, make_company, make_deal, stages):
        deal = make_deal(rep_b, make_company(rep_b), "Prospecção", title="Do B")
        response = move(client, auth(rep_a), deal, stages["Qualificação"])
        assert response.status_code == 404
        assert board_titles(client, auth(rep_b))["Prospecção"] == ["Do B"]  # nada mudou

    def test_rep_cannot_use_someone_elses_card_as_reference(self, client, auth, rep_a, rep_b, column, make_company, make_deal, stages):
        foreign = make_deal(rep_b, make_company(rep_b), "Prospecção", title="Do B")
        response = move(client, auth(rep_a), column.d1, stages["Prospecção"], above_id=str(foreign.id))
        assert response.status_code == 400 and error_code(response) == "invalid_neighbor"

    def test_manager_can_move_any_card(self, client, auth, manager, column, stages):
        response = move(client, auth(manager), column.d1, stages["Proposta"])
        assert response.status_code == 200 and response.json()["stage_id"] == str(stages["Proposta"].id)

    def test_move_requires_authentication(self, client, column, stages):
        assert client.post(f"{API}/deals/{column.d1.id}/move", json={"stage_id": str(stages['Proposta'].id)}).status_code == 401


class TestCreatingDeals:
    def test_new_deal_lands_in_first_open_stage_with_history(self, client, db, auth, rep_a, column):
        response = client.post(f"{API}/deals", headers=auth(rep_a), json={"title": "Novo", "company_id": str(column.company.id)})
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == DealStatus.open.value and body["temperature"] == "cold"
        assert board_titles(client, auth(rep_a))["Prospecção"][-1] == "Novo"  # entra no fim da coluna
        rows = db.scalars(select(DealStageHistory).where(DealStageHistory.deal_id == body["id"])).all()
        assert len(rows) == 1 and rows[0].from_stage_id is None and rows[0].moved_by == rep_a.id

    def test_primary_contact_must_belong_to_the_company(self, client, auth, rep_a, column, make_company, make_contact):
        other = make_contact(rep_a, make_company(rep_a))
        body = {"title": "X", "company_id": str(column.company.id), "primary_contact_id": str(other.id)}
        response = client.post(f"{API}/deals", headers=auth(rep_a), json=body)
        assert response.status_code == 400 and error_code(response) == "contact_company_mismatch"

    def test_quick_edit_updates_temperature_and_next_action(self, client, auth, rep_a, column):
        body = {"temperature": "hot", "next_action_type": "call", "next_action_at": "2030-01-01T10:00:00-03:00", "next_action_note": "Ligar"}
        updated = client.patch(f"{API}/deals/{column.d1.id}", headers=auth(rep_a), json=body).json()
        assert updated["temperature"] == "hot" and updated["next_action_type"] == "call" and updated["next_action_overdue"] is False

    def test_required_field_cannot_be_nulled(self, client, auth, rep_a, column):
        assert client.patch(f"{API}/deals/{column.d1.id}", headers=auth(rep_a), json={"title": None}).status_code == 422
