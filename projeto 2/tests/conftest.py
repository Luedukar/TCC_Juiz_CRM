import os

# A API valida segredo durante a importação; estes testes não autenticam via JWT.
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-at-least-32-characters-long")
