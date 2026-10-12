# CRM B2B API — Entregável 2

## Inicialização

1. Crie um banco PostgreSQL e configure as variáveis de ambiente com base em `.env.example`.
2. Execute `schema.sql` e depois `migrations/002_auth_sessions.sql` nessa ordem.
3. Instale as dependências: `python -m pip install -r requirements.txt`.
4. Inicie a API: `uvicorn app.main:app --reload`.
5. Consulte `/docs` para o contrato OpenAPI.

A inicialização exige `JWT_SECRET` com pelo menos 32 caracteres. Senhas devem ser gravadas com Argon2 usando `app.security.hash_password`; o cadastro de usuários é responsabilidade do provisionamento administrativo nesta etapa.

## Rotas principais

- `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me`
- `GET/POST /companies` e `GET/POST /contacts`
- `GET/POST /pipelines` e `POST /pipelines/{id}/stages` (configuração restrita a gestores)
- `GET/POST /opportunities`, `GET/PATCH /opportunities/{id}`
- `GET/POST /opportunities/{id}/interactions`
- `POST /contacts/{id}/consents`
- `GET /users` (gestores)

As rotas de pipeline suportam leitura para membros autenticados. O vendedor cria empresas, contatos e oportunidades para sua carteira; gestores podem consultar a equipe inteira e configurar funis/etapas.

## Segurança entregue

- Access JWT curto e refresh JWT persistido como hash, com rotação transacional e revogação por logout.
- Rate limit configurável em `/auth/login` (padrão 5/minuto por endereço IP).
- Dependências de autenticação e autorização por papel; gestores acessam todo o workspace, vendedores veem apenas a própria carteira nas rotas de oportunidades/empresas/contatos.
- Erros inesperados são registrados no log e retornam mensagem genérica. Erros HTTP mantêm status e detalhes apropriados.
- Queries incluem `workspace_id` para isolamento entre equipes.

Rate limit padrão usa memória local; em execução com múltiplos workers/instâncias, configure um storage compartilhado no SlowAPI antes de escalar horizontalmente.
## Entregável 3 — Frontend

O frontend está em `frontend/`. Siga `frontend/README.md` para instalar e executar. O servidor da API libera a origem definida por `CORS_ORIGINS` no `.env` da raiz (padrão Vite: `http://localhost:5173`).

## Testes do Entregável 4

Instale dependências de desenvolvimento com `python -m pip install -r requirements-dev.txt` (além de `requirements.txt`) e execute `python -m pytest -q`.

Cobertura focada: escopo de leitura por papel e workspace, movimento de oportunidade na própria carteira e etapa do mesmo funil, tentativa de movimentar oportunidade de outro vendedor e rejeição de etapa pertencente a outro funil; validação contra valores nulos em campos obrigatórios. A suíte substitui a conexão ao PostgreSQL por um fake de consultas; não requer banco em execução.

Última execução: `6 passed` (Python 3.14, pytest 8.4.2). O pytest exibiu um `DeprecationWarning` originado pelo SlowAPI instalado, sem falha nos testes.


