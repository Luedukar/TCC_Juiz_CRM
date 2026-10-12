"""Configuração do funil: etapas customizáveis, ordem e integridade."""
import pytest

from .conftest import API, error_code


@pytest.fixture
def pipeline(client, auth, manager):
    created = client.post(f"{API}/pipelines", headers=auth(manager), json={"name": "Funil de testes"}).json()
    for name in ("Contato", "Reunião", "Fechamento"):
        client.post(f"{API}/pipelines/{created['id']}/stages", headers=auth(manager), json={"name": name})
    return client.get(f"{API}/pipelines/{created['id']}", headers=auth(manager)).json()


def stage_names(client, headers, pipeline_id):
    return [s["name"] for s in client.get(f"{API}/pipelines/{pipeline_id}", headers=headers).json()["stages"]]


class TestStages:
    def test_stages_are_appended_in_order(self, pipeline):
        assert [s["name"] for s in pipeline["stages"]] == ["Contato", "Reunião", "Fechamento"]
        assert [s["position"] for s in pipeline["stages"]] == [0, 1, 2]

    def test_reorder_swaps_positions_despite_unique_constraint(self, client, auth, manager, pipeline):
        reversed_ids = [s["id"] for s in reversed(pipeline["stages"])]
        response = client.put(f"{API}/pipelines/{pipeline['id']}/stages/order", headers=auth(manager), json={"stage_ids": reversed_ids})
        assert response.status_code == 200
        assert stage_names(client, auth(manager), pipeline["id"]) == ["Fechamento", "Reunião", "Contato"]

    def test_reorder_requires_every_stage_exactly_once(self, client, auth, manager, pipeline):
        ids = [s["id"] for s in pipeline["stages"]]
        for bad in (ids[:2], ids + [ids[0]]):
            response = client.put(f"{API}/pipelines/{pipeline['id']}/stages/order", headers=auth(manager), json={"stage_ids": bad})
            assert response.status_code == 400 and error_code(response) == "invalid_stage_order"
        assert stage_names(client, auth(manager), pipeline["id"]) == ["Contato", "Reunião", "Fechamento"]

    def test_duplicate_stage_name_has_friendly_message(self, client, auth, manager, pipeline):
        response = client.post(f"{API}/pipelines/{pipeline['id']}/stages", headers=auth(manager), json={"name": "Contato"})
        assert response.status_code == 409 and response.json()["error"]["message"] == "Já existe uma etapa com este nome neste funil."

    def test_stage_cannot_be_both_won_and_lost(self, client, auth, manager, pipeline):
        body = {"name": "Estranha", "is_won": True, "is_lost": True}
        assert client.post(f"{API}/pipelines/{pipeline['id']}/stages", headers=auth(manager), json=body).status_code == 422

    def test_update_stage_color_and_probability(self, client, auth, manager, pipeline):
        stage = pipeline["stages"][0]
        updated = client.patch(f"{API}/stages/{stage['id']}", headers=auth(manager), json={"color": "#22C55E", "probability": 30}).json()
        assert updated["color"] == "#22C55E" and updated["probability"] == 30

    def test_invalid_probability_is_rejected(self, client, auth, manager, pipeline):
        assert client.patch(f"{API}/stages/{pipeline['stages'][0]['id']}", headers=auth(manager), json={"probability": 150}).status_code == 422

    def test_empty_stage_can_be_deleted(self, client, auth, manager, pipeline):
        assert client.delete(f"{API}/stages/{pipeline['stages'][2]['id']}", headers=auth(manager)).status_code == 204
        assert stage_names(client, auth(manager), pipeline["id"]) == ["Contato", "Reunião"]

    def test_stage_with_deals_cannot_be_deleted(self, client, db, auth, manager, rep_a, make_company, pipeline):
        import uuid
        from decimal import Decimal

        from app.models import Deal

        company = make_company(rep_a)
        stage = pipeline["stages"][0]
        db.add(Deal(pipeline_id=uuid.UUID(stage["pipeline_id"]), stage_id=uuid.UUID(stage["id"]), company_id=company.id, owner_id=rep_a.id, title="Preso", value=Decimal(0)))
        db.commit()
        response = client.delete(f"{API}/stages/{stage['id']}", headers=auth(manager))
        assert response.status_code == 409 and error_code(response) == "stage_in_use"


class TestPipelines:
    def test_only_one_default_pipeline(self, client, auth, manager):
        created = client.post(f"{API}/pipelines", headers=auth(manager), json={"name": "Novo padrão", "is_default": True}).json()
        pipelines = client.get(f"{API}/pipelines", headers=auth(manager)).json()
        assert [p["id"] for p in pipelines if p["is_default"]] == [created["id"]]

    def test_default_cannot_be_unset_directly(self, client, auth, manager):
        default = next(p for p in client.get(f"{API}/pipelines", headers=auth(manager)).json() if p["is_default"])
        assert client.patch(f"{API}/pipelines/{default['id']}", headers=auth(manager), json={"is_default": False}).status_code == 400

    def test_duplicate_pipeline_name(self, client, auth, manager):
        client.post(f"{API}/pipelines", headers=auth(manager), json={"name": "Repetido"})
        response = client.post(f"{API}/pipelines", headers=auth(manager), json={"name": "Repetido"})
        assert response.status_code == 409 and response.json()["error"]["message"] == "Já existe um funil com este nome."
