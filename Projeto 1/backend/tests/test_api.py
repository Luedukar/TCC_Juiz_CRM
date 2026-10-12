import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.limits import limiter
from app.main import app
from app.models import Company, Deal, Pipeline, PipelineStage, User
from app.security import hash_password


@pytest.fixture()
def client():
    limiter.reset()
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with TestingSession() as db:
        manager = User(
            full_name="Sales Manager",
            email="manager@example.com",
            password_hash=hash_password("manager-password-123"),
            role="sales_manager",
        )
        seller = User(
            full_name="Sales Rep",
            email="seller@example.com",
            password_hash=hash_password("seller-password-123"),
            role="sales_rep",
        )
        other = User(
            full_name="Other Rep",
            email="other@example.com",
            password_hash=hash_password("other-password-123"),
            role="sales_rep",
        )
        db.add_all([manager, seller, other])
        db.flush()
        pipeline = Pipeline(name="Default", is_default=True, created_by=manager.id)
        db.add(pipeline)
        db.flush()
        stage = PipelineStage(pipeline_id=pipeline.id, name="Prospecting", position=0)
        second_stage = PipelineStage(pipeline_id=pipeline.id, name="Qualified", position=1)
        db.add_all([stage, second_stage])
        company = Company(name="Example Corp", owner_id=seller.id)
        db.add(company)
        db.flush()
        deal = Deal(
            pipeline_id=pipeline.id,
            stage_id=stage.id,
            company_id=company.id,
            owner_id=seller.id,
            title="Enterprise deal",
        )
        other_deal = Deal(
            pipeline_id=pipeline.id,
            stage_id=stage.id,
            owner_id=other.id,
            title="Other deal",
        )
        db.add_all([deal, other_deal])
        db.commit()
        deal_id = deal.id
        second_stage_id = second_stage.id
        other_deal_id = other_deal.id

    def override_get_db():
        with TestingSession() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client, seller, manager, deal_id, second_stage_id, other_deal_id, manager.id, other.id
    app.dependency_overrides.clear()
    limiter.reset()
    Base.metadata.drop_all(engine)
    engine.dispose()


def bearer(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_seller_sees_only_own_deals(client):
    test_client, *_ = client
    headers = bearer(test_client, "seller@example.com", "seller-password-123")

    response = test_client.get("/api/deals", headers=headers)

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["title"] == "Enterprise deal"


def test_seller_cannot_read_other_seller_deal(client):
    test_client = client[0]
    other_deal_id = client[5]
    headers = bearer(test_client, "seller@example.com", "seller-password-123")

    response = test_client.get(f"/api/deals/{other_deal_id}", headers=headers)

    assert response.status_code == 404


def test_unauthenticated_user_cannot_view_pipeline_deals(client):
    test_client, *_ = client

    response = test_client.get("/api/deals")

    assert response.status_code == 401


def test_seller_cannot_update_move_or_delete_another_sellers_deal(client):
    test_client = client[0]
    second_stage_id = client[4]
    other_deal_id = client[5]
    headers = bearer(test_client, "seller@example.com", "seller-password-123")

    update = test_client.patch(
        f"/api/deals/{other_deal_id}",
        headers=headers,
        json={"title": "Alteração indevida"},
    )
    move = test_client.post(
        f"/api/deals/{other_deal_id}/stage",
        headers=headers,
        json={"stage_id": str(second_stage_id)},
    )
    delete = test_client.delete(f"/api/deals/{other_deal_id}", headers=headers)

    assert update.status_code == 404
    assert move.status_code == 404
    assert delete.status_code == 404


def test_seller_cannot_transfer_own_deal_to_another_owner(client):
    test_client, _, _, deal_id, _, _, _, other_user_id = client
    headers = bearer(test_client, "seller@example.com", "seller-password-123")

    response = test_client.patch(
        f"/api/deals/{deal_id}",
        headers=headers,
        json={"owner_id": str(other_user_id)},
    )

    assert response.status_code == 403


def test_manager_sees_all_deals(client):
    test_client, *_ = client
    headers = bearer(test_client, "manager@example.com", "manager-password-123")

    response = test_client.get("/api/deals", headers=headers)

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_manager_can_move_any_deal_and_is_recorded_in_history(client):
    test_client, _, _, _, second_stage_id, other_deal_id, manager_id, _ = client
    headers = bearer(test_client, "manager@example.com", "manager-password-123")

    moved = test_client.post(
        f"/api/deals/{other_deal_id}/stage",
        headers=headers,
        json={"stage_id": str(second_stage_id)},
    )
    history = test_client.get(f"/api/deals/{other_deal_id}/stage-history", headers=headers)

    assert moved.status_code == 200
    assert moved.json()["stage_id"] == str(second_stage_id)
    assert history.status_code == 200
    assert len(history.json()) == 1
    assert history.json()[0]["changed_by"] == str(manager_id)


def test_seller_can_move_own_deal_and_history_is_recorded(client):
    test_client, _, _, deal_id, second_stage_id, *_ = client
    headers = bearer(test_client, "seller@example.com", "seller-password-123")

    response = test_client.post(
        f"/api/deals/{deal_id}/stage",
        headers=headers,
        json={"stage_id": str(second_stage_id)},
    )

    assert response.status_code == 200
    assert response.json()["stage_id"] == str(second_stage_id)
    history = test_client.get(f"/api/deals/{deal_id}/stage-history", headers=headers)
    assert history.status_code == 200
    assert len(history.json()) == 1


def test_refresh_token_rotates_and_rejects_reuse(client):
    test_client, *_ = client
    login = test_client.post(
        "/api/auth/login",
        json={"email": "seller@example.com", "password": "seller-password-123"},
    )
    assert login.status_code == 200
    old_refresh = login.json()["refresh_token"]

    rotated = test_client.post("/api/auth/refresh", json={"refresh_token": old_refresh})

    assert rotated.status_code == 200
    assert rotated.json()["refresh_token"] != old_refresh
    replay = test_client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
    assert replay.status_code == 401


def test_manager_can_reorder_pipeline_stages(client):
    test_client, _, _, _, second_stage_id, *_ = client
    headers = bearer(test_client, "manager@example.com", "manager-password-123")
    pipeline_id = test_client.get("/api/pipelines", headers=headers).json()[0]["id"]
    first_stage_id = test_client.get(
        f"/api/pipelines/{pipeline_id}/stages", headers=headers
    ).json()[0]["id"]

    response = test_client.post(
        f"/api/pipelines/{pipeline_id}/stages/reorder",
        headers=headers,
        json={"stage_ids": [str(second_stage_id), first_stage_id]},
    )

    assert response.status_code == 200
    assert [stage["id"] for stage in response.json()] == [str(second_stage_id), first_stage_id]


def test_login_rate_is_limited():
    from app.main import limiter

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with TestingSession() as db:
        db.add(
            User(
                full_name="Manager",
                email="manager@example.com",
                password_hash=hash_password("manager-password-123"),
                role="sales_manager",
            )
        )
        db.commit()

    def override_get_db():
        with TestingSession() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    limiter.reset()
    with TestClient(app) as test_client:
        for _ in range(5):
            assert test_client.post(
                "/api/auth/login",
                json={"email": "manager@example.com", "password": "manager-password-123"},
            ).status_code == 200
        limited = test_client.post(
            "/api/auth/login",
            json={"email": "manager@example.com", "password": "manager-password-123"},
        )
        assert limited.status_code == 429
    app.dependency_overrides.clear()
    limiter.reset()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_frontend_origin_is_allowed_by_cors(client):
    test_client, *_ = client

    response = test_client.options(
        "/api/auth/login",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
