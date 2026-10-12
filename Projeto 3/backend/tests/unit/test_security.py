"""JWT, hash de senha e refresh tokens (sem banco)."""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest

from app import security
from app.config import get_settings
from app.models import UserRole


def fake_user(role=UserRole.sales_rep):
    return SimpleNamespace(id=uuid.uuid4(), role=role)


def encode(payload: dict, secret: str | None = None, algorithm: str = "HS256") -> str:
    return jwt.encode(payload, secret or get_settings().jwt_secret, algorithm=algorithm)


def valid_payload(**overrides) -> dict:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(uuid.uuid4()), "role": "sales_rep", "type": "access", "iat": now, "exp": now + timedelta(minutes=5)}
    payload.update(overrides)
    return payload


class TestPasswords:
    def test_hash_and_verify(self):
        hashed = security.hash_password("Senha-forte-123")
        assert hashed != "Senha-forte-123"
        assert security.verify_password(hashed, "Senha-forte-123") is True

    def test_wrong_password_is_rejected(self):
        hashed = security.hash_password("Senha-forte-123")
        assert security.verify_password(hashed, "outra-senha") is False

    def test_malformed_hash_is_rejected_without_raising(self):
        assert security.verify_password("isto-nao-e-um-hash", "qualquer") is False

    def test_same_password_generates_different_hashes(self):
        assert security.hash_password("Senha-forte-123") != security.hash_password("Senha-forte-123")


class TestAccessToken:
    def test_roundtrip_contains_subject_role_and_type(self):
        user = fake_user(UserRole.sales_manager)
        token, expires_in = security.create_access_token(user)
        payload = security.decode_access_token(token)
        assert payload["sub"] == str(user.id)
        assert payload["role"] == "sales_manager"
        assert payload["type"] == "access"
        assert expires_in == get_settings().access_token_minutes * 60

    def test_expired_token_raises_expired_signature(self):
        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        token = encode(valid_payload(iat=past - timedelta(minutes=5), exp=past))
        with pytest.raises(jwt.ExpiredSignatureError):
            security.decode_access_token(token)

    def test_token_signed_with_other_secret_is_rejected(self):
        token = encode(valid_payload(), secret="x" * 40)
        with pytest.raises(jwt.PyJWTError):
            security.decode_access_token(token)

    def test_unsigned_token_alg_none_is_rejected(self):
        token = jwt.encode(valid_payload(), None, algorithm="none")
        with pytest.raises(jwt.PyJWTError):
            security.decode_access_token(token)

    def test_token_of_another_type_is_rejected(self):
        with pytest.raises(jwt.PyJWTError):
            security.decode_access_token(encode(valid_payload(type="refresh")))

    def test_token_without_expiration_is_rejected(self):
        payload = valid_payload()
        del payload["exp"]
        with pytest.raises(jwt.PyJWTError):
            security.decode_access_token(encode(payload))

    def test_tampered_payload_is_rejected(self):
        token = security.create_access_token(fake_user())[0]
        header, body, signature = token.split(".")
        forged = f"{header}.{body[:-2]}AA.{signature}"
        with pytest.raises(jwt.PyJWTError):
            security.decode_access_token(forged)


class TestRefreshToken:
    def test_only_hash_matches_and_is_sha256_hex(self):
        raw, hashed = security.new_refresh_token()
        assert security.hash_token(raw) == hashed
        assert len(hashed) == 64
        assert raw != hashed

    def test_tokens_are_unique_and_long(self):
        first, _ = security.new_refresh_token()
        second, _ = security.new_refresh_token()
        assert first != second
        assert len(first) >= 60
