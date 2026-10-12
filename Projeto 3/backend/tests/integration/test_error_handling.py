"""Tratamento global de erros: formato único, mensagens amigáveis e nada de vazamento interno."""
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.database import get_db
from app.main import create_app

from .conftest import API, error_code

CNPJ_VALIDO = "11.222.333/0001-81"


def assert_standard_shape(response):
    error = response.json()["error"]
    assert {"code", "message", "request_id"} <= set(error)
    assert isinstance(error["message"], str) and error["message"]
    return error


class TestFriendlyErrors:
    def test_validation_error_lists_fields(self, client, auth, rep_a):
        response = client.post(f"{API}/companies", headers=auth(rep_a), json={"legal_name": "Empresa X", "cnpj": "11.222.333/0001-00"})
        assert response.status_code == 422
        error = assert_standard_shape(response)
        assert error["code"] == "validation_error"
        assert any(d["field"] == "cnpj" and "CNPJ" in d["message"] for d in error["details"])

    def test_missing_fields_are_reported_by_name(self, client, auth, rep_a):
        error = assert_standard_shape(client.post(f"{API}/deals", headers=auth(rep_a), json={}))
        assert {"title", "company_id"} <= {d["field"] for d in error["details"]}

    def test_duplicate_cnpj_is_a_friendly_conflict(self, client, auth, rep_a):
        body = {"legal_name": "Empresa X", "cnpj": CNPJ_VALIDO}
        assert client.post(f"{API}/companies", headers=auth(rep_a), json=body).json()["cnpj"] == "11222333000181"
        response = client.post(f"{API}/companies", headers=auth(rep_a), json={**body, "legal_name": "Outra"})
        assert response.status_code == 409
        assert error_code(response) == "constraint_violation"
        assert response.json()["error"]["message"] == "Já existe uma empresa cadastrada com este CNPJ."

    def test_second_primary_contact_replaces_the_first(self, client, auth, rep_a, make_company):
        company = make_company(rep_a)
        first = client.post(f"{API}/contacts", headers=auth(rep_a), json={"company_id": str(company.id), "full_name": "Primeiro", "is_primary": True}).json()
        client.post(f"{API}/contacts", headers=auth(rep_a), json={"company_id": str(company.id), "full_name": "Segundo", "is_primary": True})
        assert client.get(f"{API}/contacts/{first['id']}", headers=auth(rep_a)).json()["is_primary"] is False

    def test_unknown_route_uses_standard_shape(self, client):
        response = client.get("/api/v1/nao-existe")
        assert response.status_code == 404 and assert_standard_shape(response)["code"] == "not_found"

    def test_wrong_method_uses_standard_shape(self, client):
        response = client.delete(f"{API}/auth/login")
        assert response.status_code == 405 and assert_standard_shape(response)["code"] == "method_not_allowed"

    def test_unauthorized_uses_standard_shape(self, client):
        assert assert_standard_shape(client.get(f"{API}/deals"))["code"] == "not_authenticated"


class TestRequestId:
    def test_response_carries_a_generated_request_id(self, client):
        response = client.get("/health")
        assert response.status_code == 200 and response.headers["X-Request-ID"]

    def test_client_provided_request_id_is_echoed_in_header_and_error_body(self, client):
        response = client.get(f"{API}/deals", headers={"X-Request-ID": "abc-123"})
        assert response.headers["X-Request-ID"] == "abc-123"
        assert response.json()["error"]["request_id"] == "abc-123"

    def test_security_headers_are_present(self, client):
        headers = client.get("/health").headers
        assert headers["X-Content-Type-Options"] == "nosniff" and headers["Cache-Control"] == "no-store"


class TestUnexpectedFailures:
    def test_unhandled_exception_does_not_leak_internals(self):
        app = create_app()

        @app.get("/__boom")
        def boom():
            raise RuntimeError("segredo-interno-do-servidor")

        response = TestClient(app, raise_server_exceptions=False).get("/__boom")
        assert response.status_code == 500
        error = assert_standard_shape(response)
        assert error["code"] == "internal_error"
        assert "segredo-interno" not in response.text and "Traceback" not in response.text

    def test_database_outage_becomes_503_with_retry_after(self):
        app = create_app()

        def broken_db():
            raise OperationalError("SELECT 1", {}, Exception("conexão recusada"))
            yield  # pragma: no cover

        app.dependency_overrides[get_db] = broken_db
        response = TestClient(app, raise_server_exceptions=False).post(f"{API}/auth/login", json={"email": "a@b.com", "password": "x"})
        assert response.status_code == 503
        assert assert_standard_shape(response)["code"] == "service_unavailable"
        assert response.headers["Retry-After"] == "5" and "conexão recusada" not in response.text

    def test_readiness_probe_checks_the_database(self, client):
        assert client.get("/health/ready").json() == {"status": "ready"}
