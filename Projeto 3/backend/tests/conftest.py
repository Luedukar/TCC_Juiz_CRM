"""Configuração global dos testes.

As variáveis de ambiente precisam ser definidas ANTES de importar `app.*`, porque as
configurações são lidas (e cacheadas) na primeira importação.
"""
import os

os.environ.setdefault("JWT_SECRET", "segredo-de-teste-com-mais-de-32-caracteres-123456")
os.environ.setdefault("ENVIRONMENT", "test")
# Nos testes, reapresentar um refresh token rotacionado conta como reuso imediatamente
# (os testes de corrida entre abas ajustam esse valor explicitamente).
os.environ["REFRESH_REUSE_GRACE_SECONDS"] = "0"

# Segurança: a aplicação só enxerga o banco de testes, nunca o de desenvolvimento.
if os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

import pytest  # noqa: E402
from argon2 import PasswordHasher  # noqa: E402

from app import security  # noqa: E402

# Parâmetros leves de argon2 apenas nos testes (a suíte cria muitos usuários).
security._ph = PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1)


def pytest_collection_modifyitems(items):
    for item in items:
        if "/integration/" in str(item.fspath).replace("\\", "/"):
            item.add_marker(pytest.mark.integration)
