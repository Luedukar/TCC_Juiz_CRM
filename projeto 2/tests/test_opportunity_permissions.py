from contextlib import contextmanager
from copy import deepcopy
import re

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app import main
from app.schemas import OpportunityPatch

WORKSPACE = 7
PIPELINE = 3
STAGES = {31: PIPELINE, 32: PIPELINE, 99: 44}
INITIAL = [
    {"id": 101, "workspace_id": WORKSPACE, "pipeline_id": PIPELINE, "stage_id": 31, "owner_user_id": 11, "title": "Carteira da Ana", "status": "open"},
    {"id": 102, "workspace_id": WORKSPACE, "pipeline_id": PIPELINE, "stage_id": 31, "owner_user_id": 12, "title": "Carteira do Bruno", "status": "open"},
    {"id": 103, "workspace_id": WORKSPACE + 1, "pipeline_id": PIPELINE, "stage_id": 31, "owner_user_id": 11, "title": "Outro workspace", "status": "open"},
]

class FakeConnection:
    """Implementa somente as consultas usadas pelas rotas sob teste."""
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        if normalized.startswith("SELECT pipeline_id FROM opportunities"):
            deal_id, workspace_id = params
            row = next((r for r in self.rows if r["id"] == deal_id and r["workspace_id"] == workspace_id), None)
            return Result({"pipeline_id": row["pipeline_id"]} if row else None)
        if normalized.startswith("SELECT * FROM opportunities WHERE id=%s"):
            deal_id, workspace_id = params[:2]
            row = next((r for r in self.rows if r["id"] == deal_id and r["workspace_id"] == workspace_id), None)
            if row and "owner_user_id=%s" in normalized and row["owner_user_id"] != params[2]:
                row = None
            return Result(deepcopy(row) if row else None)
        if normalized.startswith("SELECT id FROM pipeline_stages"):
            stage_id, workspace_id, pipeline_id = params
            stage_pipeline = STAGES.get(stage_id)
            return Result({"id": stage_id} if stage_pipeline == pipeline_id and workspace_id == WORKSPACE else None)
        if normalized.startswith("SELECT * FROM opportunities WHERE"):
            workspace_id = params[0]
            selected = [r for r in self.rows if r["workspace_id"] == workspace_id and r["status"] == "open"]
            cursor = 1
            if "owner_user_id=%s" in normalized:
                owner = params[cursor]
                cursor += 1
                selected = [r for r in selected if r["owner_user_id"] == owner]
            if "pipeline_id=%s" in normalized:
                pipeline_id = params[cursor]
                selected = [r for r in selected if r["pipeline_id"] == pipeline_id]
            return Result(deepcopy(selected))
        if normalized.startswith("UPDATE opportunities SET"):
            assignment = normalized.split(" SET ", 1)[1].split(" WHERE ", 1)[0]
            fields = re.findall(r"([a-z_]+)=%s", assignment)
            values = list(params)
            updates = dict(zip(fields, values))
            deal_id, workspace_id = values[len(fields):len(fields) + 2]
            row = next((r for r in self.rows if r["id"] == deal_id and r["workspace_id"] == workspace_id), None)
            if row and "owner_user_id=%s" in normalized:
                owner = values[len(fields) + 2]
                if row["owner_user_id"] != owner:
                    row = None
            if row:
                row.update(updates)
                return Result(deepcopy(row))
            return Result(None)
        raise AssertionError(f"Consulta não prevista no fake: {normalized}")

class Result:
    def __init__(self, value):
        self.value = value
    def fetchone(self):
        return self.value if isinstance(self.value, dict) else None
    def fetchall(self):
        return self.value if isinstance(self.value, list) else []

@pytest.fixture
def fake_db(monkeypatch):
    rows = deepcopy(INITIAL)
    @contextmanager
    def connect():
        yield FakeConnection(rows)
    monkeypatch.setattr(main, "connection", connect)
    return rows

@pytest.fixture
def seller():
    return {"id": 11, "workspace_id": WORKSPACE, "role": "seller", "full_name": "Ana"}

@pytest.fixture
def manager():
    return {"id": 50, "workspace_id": WORKSPACE, "role": "manager", "full_name": "Gestor"}

def test_seller_lists_only_opportunities_in_own_portfolio(fake_db, seller):
    result = main.list_opportunities(user=seller)
    assert [deal["id"] for deal in result] == [101]

def test_manager_lists_all_workspace_opportunities(fake_db, manager):
    result = main.list_opportunities(user=manager)
    assert {deal["id"] for deal in result} == {101, 102}

def test_seller_can_move_own_opportunity_to_stage_in_same_pipeline(fake_db, seller):
    result = main.update_opportunity(101, OpportunityPatch(stage_id=32), user=seller)
    assert result["stage_id"] == 32
    assert fake_db[0]["stage_id"] == 32

def test_seller_cannot_move_opportunity_owned_by_another_seller(fake_db, seller):
    with pytest.raises(HTTPException) as error:
        main.update_opportunity(102, OpportunityPatch(stage_id=32), user=seller)
    assert error.value.status_code == 404
    assert fake_db[1]["stage_id"] == 31

def test_opportunity_cannot_move_to_stage_from_another_pipeline(fake_db, manager):
    with pytest.raises(HTTPException) as error:
        main.update_opportunity(101, OpportunityPatch(stage_id=99), user=manager)
    assert error.value.status_code == 422
    assert fake_db[0]["stage_id"] == 31

def test_patch_rejects_null_for_non_nullable_fields():
    with pytest.raises(ValidationError):
        OpportunityPatch(title=None)
