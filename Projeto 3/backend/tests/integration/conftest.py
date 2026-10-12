"""Fixtures de integração: PostgreSQL real, schema.sql aplicado e dados mínimos por teste.

Execução local:
    docker compose --profile test up -d db-test
    export TEST_DATABASE_URL=postgresql+psycopg2://crm:crm@localhost:5433/crm_test
    pytest
"""
import itertools
import os
import pathlib
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import make_url, select, text

from app.database import get_engine, get_sessionmaker
from app.main import create_app
from app.models import Company, Contact, Deal, Pipeline, PipelineStage, User, UserRole
from app.ratelimit import limiter
from app.security import create_access_token, hash_password

API = "/api/v1"
PASSWORD = "Senha-forte-123"
SCHEMA_SQL = pathlib.Path(__file__).resolve().parents[2] / "db" / "schema.sql"


@pytest.fixture(scope="session", autouse=True)
def _database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Defina TEST_DATABASE_URL (banco PostgreSQL cujo nome termine em _test) para rodar os testes de integração.")
    if not (make_url(url).database or "").endswith("_test"):
        pytest.exit("TEST_DATABASE_URL precisa apontar para um banco cujo nome termine em '_test' (a suíte recria o schema).", returncode=2)

    raw = get_engine().raw_connection()
    try:
        raw.autocommit = True
        cursor = raw.cursor()
        cursor.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        cursor.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
    finally:
        raw.close()
    yield


@pytest.fixture(autouse=True)
def _clean_state(_database):
    """Estado limpo em cada teste. O funil padrão semeado pelo schema.sql é preservado."""
    limiter.reset()
    with get_engine().begin() as conn:
        conn.execute(text("TRUNCATE users, audit_logs RESTART IDENTITY CASCADE"))
        conn.execute(text("DELETE FROM pipelines WHERE is_default = false"))
    yield


@pytest.fixture
def db():
    session = get_sessionmaker()()
    yield session
    session.close()


@pytest.fixture
def client():
    return TestClient(create_app())


@pytest.fixture
def make_user(db):
    def _make(name="Usuário", role=UserRole.sales_rep, email=None, password=PASSWORD, accepted_terms=True, **extra):
        user = User(
            name=name,
            email=email or f"{uuid.uuid4().hex[:10]}@teste.com",
            password_hash=hash_password(password),
            role=role,
            terms_accepted_at=datetime.now(timezone.utc) if accepted_terms else None,
            **extra,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    return _make


@pytest.fixture
def manager(make_user):
    return make_user(name="Gestora", role=UserRole.sales_manager)


@pytest.fixture
def rep_a(make_user):
    return make_user(name="Vendedor A")


@pytest.fixture
def rep_b(make_user):
    return make_user(name="Vendedor B")


@pytest.fixture
def auth():
    def _headers(user):
        token, _ = create_access_token(user)
        return {"Authorization": f"Bearer {token}"}

    return _headers


@pytest.fixture
def stages(db) -> dict[str, PipelineStage]:
    rows = db.scalars(
        select(PipelineStage).join(Pipeline, Pipeline.id == PipelineStage.pipeline_id).where(Pipeline.is_default.is_(True))
    ).all()
    return {s.name: s for s in rows}


@pytest.fixture
def make_company(db):
    def _make(owner, name=None, **extra):
        company = Company(owner_id=owner.id, legal_name=name or f"Empresa {uuid.uuid4().hex[:6]}", **extra)
        db.add(company)
        db.commit()
        db.refresh(company)
        return company

    return _make


@pytest.fixture
def make_contact(db):
    def _make(owner, company, name="Contato Teste", **extra):
        contact = Contact(owner_id=owner.id, company_id=company.id, full_name=name, **extra)
        db.add(contact)
        db.commit()
        db.refresh(contact)
        return contact

    return _make


@pytest.fixture
def make_deal(db, stages):
    counter = itertools.count(1)

    def _make(owner, company, stage="Prospecção", title=None, position=None, value=0, **extra):
        target = stages[stage]
        deal = Deal(
            pipeline_id=target.pipeline_id,
            stage_id=target.id,
            company_id=company.id,
            owner_id=owner.id,
            title=title or f"Negócio {uuid.uuid4().hex[:6]}",
            value=Decimal(value),
            position=Decimal(position if position is not None else next(counter) * 1024),
            **extra,
        )
        db.add(deal)
        db.commit()
        db.refresh(deal)
        return deal

    return _make


def board_titles(client, headers, **params) -> dict[str, list[str]]:
    """Kanban como {nome_da_etapa: [títulos dos cards na ordem exibida]}."""
    response = client.get(f"{API}/deals/board", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return {c["stage"]["name"]: [d["title"] for d in c["deals"]] for c in response.json()["columns"]}


def error_code(response) -> str:
    return response.json()["error"]["code"]
