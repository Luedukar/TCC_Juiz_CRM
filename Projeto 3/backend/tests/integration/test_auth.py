"""Autenticação: login, bloqueio, rate limit, refresh tokens e sessões."""
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.config import get_settings
from app.models import User, UserRole

from .conftest import API, PASSWORD, error_code


def login(client, email, password=PASSWORD):
    return client.post(f"{API}/auth/login", json={"email": email, "password": password})


@pytest.fixture
def relaxed_rate_limit(monkeypatch):
    """Isola o bloqueio de conta do rate limit por IP."""
    monkeypatch.setattr(get_settings(), "login_rate_limit_attempts", 1000)


class TestLogin:
    def test_success_returns_tokens_and_user(self, client, rep_a):
        response = login(client, rep_a.email)
        assert response.status_code == 200
        body = response.json()
        assert body["token_type"] == "bearer" and body["access_token"] and body["refresh_token"]
        assert body["user"]["email"] == rep_a.email
        assert body["user"]["role"] == "sales_rep"
        assert "password_hash" not in body["user"]

    def test_wrong_password_and_unknown_email_look_identical(self, client, rep_a):
        wrong = login(client, rep_a.email, "senha-errada-123")
        unknown = login(client, "ninguem@teste.com", "senha-errada-123")
        assert wrong.status_code == unknown.status_code == 401
        assert error_code(wrong) == error_code(unknown) == "invalid_credentials"
        assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]

    def test_inactive_user_cannot_login(self, client, make_user):
        user = make_user(is_active=False)
        assert login(client, user.email).status_code == 401

    def test_email_is_case_insensitive(self, client, make_user):
        user = make_user(email="Maria.Silva@Teste.com")
        assert login(client, "maria.silva@teste.com").status_code == 200

    def test_successful_login_updates_last_login_and_resets_failures(self, client, db, make_user, relaxed_rate_limit):
        user = make_user()
        login(client, user.email, "errada-123456")
        assert login(client, user.email).status_code == 200
        db.expire_all()
        refreshed = db.get(User, user.id)
        assert refreshed.failed_logins == 0 and refreshed.last_login_at is not None


class TestAccountLockout:
    def test_account_locks_after_max_failures(self, client, db, make_user, relaxed_rate_limit):
        user = make_user()
        for _ in range(get_settings().max_failed_logins):
            assert login(client, user.email, "errada-123456").status_code == 401
        locked = login(client, user.email)  # mesmo com a senha correta
        assert locked.status_code == 423
        assert error_code(locked) == "account_locked"

    def test_lock_expires(self, client, db, make_user, relaxed_rate_limit):
        user = make_user()
        for _ in range(get_settings().max_failed_logins):
            login(client, user.email, "errada-123456")
        db.expire_all()
        db.get(User, user.id).locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
        assert login(client, user.email).status_code == 200


class TestLoginRateLimit:
    def test_only_failures_count_towards_the_limit(self, client, make_user):
        users = [make_user() for _ in range(8)]
        assert all(login(client, u.email).status_code == 200 for u in users)  # 8 > limite, mas são sucessos

    def test_blocks_ip_after_too_many_failures_with_retry_after(self, client, rep_a):
        limit = get_settings().login_rate_limit_attempts
        for _ in range(limit):
            assert login(client, "ninguem@teste.com", "errada-123456").status_code == 401
        blocked = login(client, rep_a.email)  # até credencial correta é recusada durante o bloqueio
        assert blocked.status_code == 429
        assert error_code(blocked) == "rate_limited"
        assert int(blocked.headers["Retry-After"]) >= 1


class TestRefreshTokens:
    def test_refresh_rotates_the_token(self, client, rep_a):
        first = login(client, rep_a.email).json()
        response = client.post(f"{API}/auth/refresh", json={"refresh_token": first["refresh_token"]})
        assert response.status_code == 200
        second = response.json()
        assert second["refresh_token"] != first["refresh_token"]
        assert client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {second['access_token']}"}).status_code == 200

    def test_reusing_a_rotated_token_revokes_the_whole_session(self, client, rep_a):
        first = login(client, rep_a.email).json()
        second = client.post(f"{API}/auth/refresh", json={"refresh_token": first["refresh_token"]}).json()

        reuse = client.post(f"{API}/auth/refresh", json={"refresh_token": first["refresh_token"]})
        assert reuse.status_code == 401 and error_code(reuse) == "refresh_reuse_detected"

        after = client.post(f"{API}/auth/refresh", json={"refresh_token": second["refresh_token"]})
        assert after.status_code == 401  # o token novo também foi revogado

    def test_near_simultaneous_refresh_is_a_conflict_not_a_theft(self, client, rep_a, monkeypatch):
        monkeypatch.setattr(get_settings(), "refresh_reuse_grace_seconds", 10)
        first = login(client, rep_a.email).json()
        second = client.post(f"{API}/auth/refresh", json={"refresh_token": first["refresh_token"]}).json()

        conflict = client.post(f"{API}/auth/refresh", json={"refresh_token": first["refresh_token"]})
        assert conflict.status_code == 401 and error_code(conflict) == "refresh_conflict"

        # A sessão NÃO foi derrubada: o token novo continua válido.
        assert client.post(f"{API}/auth/refresh", json={"refresh_token": second["refresh_token"]}).status_code == 200

    def test_unknown_refresh_token_is_rejected(self, client):
        response = client.post(f"{API}/auth/refresh", json={"refresh_token": "x" * 48})
        assert response.status_code == 401 and error_code(response) == "invalid_refresh_token"

    def test_expired_refresh_token_is_rejected(self, client, db, rep_a):
        from app.models import RefreshToken

        tokens = login(client, rep_a.email).json()
        db.query(RefreshToken).update({"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)})
        db.commit()
        assert client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401

    def test_logout_revokes_the_session_and_is_idempotent(self, client, rep_a):
        tokens = login(client, rep_a.email).json()
        assert client.post(f"{API}/auth/logout", json={"refresh_token": tokens["refresh_token"]}).status_code == 204
        assert client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401
        assert client.post(f"{API}/auth/logout", json={"refresh_token": "y" * 48}).status_code == 204

    def test_logout_all_revokes_every_session(self, client, rep_a):
        one, two = login(client, rep_a.email).json(), login(client, rep_a.email).json()
        headers = {"Authorization": f"Bearer {one['access_token']}"}
        assert client.post(f"{API}/auth/logout-all", headers=headers).status_code == 204
        for tokens in (one, two):
            assert client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401


class TestAccessTokenValidation:
    def test_missing_token(self, client):
        response = client.get(f"{API}/auth/me")
        assert response.status_code == 401 and error_code(response) == "not_authenticated"

    def test_garbage_token(self, client):
        response = client.get(f"{API}/auth/me", headers={"Authorization": "Bearer isto.nao.vale"})
        assert response.status_code == 401 and error_code(response) == "invalid_token"

    def test_expired_token_has_specific_code(self, client, rep_a):
        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        token = jwt.encode(
            {"sub": str(rep_a.id), "role": "sales_rep", "type": "access", "iat": past - timedelta(minutes=5), "exp": past},
            get_settings().jwt_secret, algorithm="HS256",
        )
        response = client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401 and error_code(response) == "token_expired"

    def test_token_of_deactivated_user_stops_working(self, client, db, auth, rep_a):
        headers = auth(rep_a)
        assert client.get(f"{API}/auth/me", headers=headers).status_code == 200
        db.expire_all()
        db.get(User, rep_a.id).is_active = False
        db.commit()
        assert client.get(f"{API}/auth/me", headers=headers).status_code == 401

    def test_role_claim_is_not_trusted_for_authorization(self, client, auth, rep_a):
        """Um token de vendedor com claim 'sales_manager' forjada não ganha acesso (o papel vem do banco)."""
        token = jwt.encode(
            {"sub": str(rep_a.id), "role": "sales_manager", "type": "access",
             "iat": datetime.now(timezone.utc), "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
            get_settings().jwt_secret, algorithm="HS256",
        )
        assert client.get(f"{API}/users", headers={"Authorization": f"Bearer {token}"}).status_code == 403


class TestTermsAndUsers:
    def test_accept_terms_records_timestamp(self, client, auth, make_user):
        user = make_user(accepted_terms=False)
        assert user.terms_accepted_at is None
        response = client.post(f"{API}/auth/accept-terms", headers=auth(user))
        assert response.status_code == 200 and response.json()["terms_accepted_at"] is not None

    def test_rep_cannot_list_or_create_users(self, client, auth, rep_a):
        assert client.get(f"{API}/users", headers=auth(rep_a)).status_code == 403
        body = {"name": "Novo", "email": "novo@teste.com", "password": PASSWORD}
        assert client.post(f"{API}/users", headers=auth(rep_a), json=body).status_code == 403

    def test_manager_creates_user_who_can_login(self, client, auth, manager):
        body = {"name": "Novo Vendedor", "email": "novo@teste.com", "password": PASSWORD}
        created = client.post(f"{API}/users", headers=auth(manager), json=body)
        assert created.status_code == 201 and created.json()["role"] == "sales_rep"
        assert login(client, "novo@teste.com").status_code == 200

    def test_duplicate_email_has_friendly_message(self, client, auth, manager, rep_a):
        body = {"name": "Outro", "email": rep_a.email, "password": PASSWORD}
        response = client.post(f"{API}/users", headers=auth(manager), json=body)
        assert response.status_code == 409 and response.json()["error"]["message"] == "Este e-mail já está em uso."

    def test_weak_password_is_rejected(self, client, auth, manager):
        body = {"name": "Novo", "email": "novo@teste.com", "password": "123"}
        assert client.post(f"{API}/users", headers=auth(manager), json=body).status_code == 422

    def test_deactivating_user_kills_access_and_refresh(self, client, auth, manager, rep_a):
        tokens = login(client, rep_a.email).json()
        response = client.patch(f"{API}/users/{rep_a.id}", headers=auth(manager), json={"is_active": False})
        assert response.status_code == 200
        assert client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401
        assert client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}).status_code == 401

    def test_password_change_revokes_existing_sessions(self, client, auth, manager, rep_a):
        tokens = login(client, rep_a.email).json()
        client.patch(f"{API}/users/{rep_a.id}", headers=auth(manager), json={"password": "Outra-senha-456"})
        assert client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401
        assert login(client, rep_a.email, "Outra-senha-456").status_code == 200

    def test_manager_cannot_deactivate_or_demote_self(self, client, auth, manager):
        assert client.patch(f"{API}/users/{manager.id}", headers=auth(manager), json={"is_active": False}).status_code == 400
        assert client.patch(f"{API}/users/{manager.id}", headers=auth(manager), json={"role": "sales_rep"}).status_code == 400
