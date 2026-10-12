# Orbit CRM

CRM web para equipes de vendas B2B, com oportunidades em Kanban, autenticação JWT e permissões por carteira.

## Stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy e PostgreSQL.
- **Frontend:** React, TypeScript, Vite e Tailwind CSS.
- **Testes:** Pytest e Vitest com React Testing Library.

## Funcionalidades

- Cadastro e gerenciamento de empresas, contatos e oportunidades.
- Funis e etapas configuráveis por gestores, incluindo reordenação das etapas.
- Movimentação de oportunidades no Kanban com histórico auditável.
- Registro de reuniões, e-mails, ligações e consentimentos LGPD.
- JWT de curta duração com refresh token rotativo e revogável.
- Gestores visualizam a carteira completa; vendedores acessam somente os próprios registros.
- Rate limit de login, mensagens de erro consistentes e estados de carregamento/falha no quadro.

## Requisitos

- Windows com PowerShell, Python 3.11 ou superior, Node.js 20.19+ (ou 22.12+) e npm.
- PostgreSQL 14 ou superior.
- `psql` no `PATH` caso escolha aplicar o schema manualmente.

## Configuração local

### 1. Preparar PostgreSQL

Crie um usuário e um banco de dados. Ajuste os nomes e a senha para seu ambiente:

```powershell
psql -U postgres -c "CREATE ROLE crm WITH LOGIN PASSWORD 'troque-esta-senha';"
psql -U postgres -c "CREATE DATABASE crm OWNER crm;"
```

O arquivo [schema.sql](./schema.sql) cria as tabelas, índices, restrições e a extensão `pgcrypto`. Aplique-o com:

```powershell
psql -h localhost -U crm -d crm -f .\schema.sql
```

Se o banco for compartilhado por outros sistemas, faça backup antes de aplicar o schema. O DDL cria objetos com nomes próprios do CRM.

### 2. Configurar e iniciar o backend

Em um terminal PowerShell:

```powershell
Set-Location .\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edite `backend\.env` e configure pelo menos:

```dotenv
DATABASE_URL=postgresql+psycopg://crm:troque-esta-senha@localhost:5432/crm
JWT_SECRET_KEY=use-um-segredo-aleatorio-forte
BOOTSTRAP_EMAIL=gestor@empresa.com
BOOTSTRAP_PASSWORD=use-uma-senha-com-pelo-menos-12-caracteres
```

Use um segredo JWT aleatório forte, por exemplo gerado localmente com `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Se a senha do PostgreSQL tiver caracteres especiais, codifique-os para uso em uma URL de conexão.

Crie o primeiro gestor e inicie a API:

```powershell
python -m app.bootstrap
python -m uvicorn app.main:app --reload
```

O bootstrap cria o schema através dos modelos SQLAlchemy caso ainda não exista e insere o gestor configurado no `.env`. Ele para com erro explícito se um gestor já existir; não é uma operação para repetir.

A API fica em `http://localhost:8000`. A documentação interativa do FastAPI fica em `http://localhost:8000/docs`; a verificação de saúde fica em `http://localhost:8000/health`.

Depois do primeiro login, crie o funil inicial e suas etapas pela documentação `/docs` usando `POST /api/pipelines` e `POST /api/pipelines/{pipeline_id}/stages`. O projeto não insere etapas de vendas padrão automaticamente; por exemplo, crie etapas com posições consecutivas (`0`, `1`, `2`) e probabilidades adequadas ao seu processo comercial.

### 3. Configurar e iniciar o frontend

Em outro terminal PowerShell:

```powershell
Set-Location .\frontend
Copy-Item .env.example .env
npm install
npm run dev
```

O Vite inicia o frontend em `http://localhost:5173`. A variável `VITE_API_BASE_URL` em `frontend\.env` deve apontar para a API, por padrão `http://localhost:8000/api`.

Para permitir outra origem de frontend, inclua-a em `CORS_ORIGINS` no `backend\.env`, separada por vírgulas. Não use curingas com credenciais em produção.

## Testes e build

Execute a partir da raiz do projeto:

```powershell
$env:PYTHONPATH = ".\backend"
python -m pytest .\backend\tests -q
npm --prefix .\frontend test
npm --prefix .\frontend run build
npm --prefix .\frontend audit
```

Consulte [QUALITY_REPORT.md](./QUALITY_REPORT.md) para os testes cobertos e o resultado da última execução.

## Endpoints principais

Todas as rotas CRM usam o prefixo `/api` e exigem `Authorization: Bearer <access_token>`, salvo login, refresh e logout.

| Recurso | Rotas |
| --- | --- |
| Sessão e usuários | `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me`, `POST /auth/users` (gestor) |
| Empresas | `GET/POST /companies`, `GET/PATCH/DELETE /companies/{id}` |
| Contatos e consentimento | `GET/POST /contacts`, `GET/PATCH/DELETE /contacts/{id}`, `GET/POST /contacts/{id}/consents` |
| Funis e etapas | `GET/POST /pipelines`, `PATCH/DELETE /pipelines/{id}`, rotas `/pipelines/{id}/stages` e `/pipelines/{id}/stages/reorder` (gestor para alterações) |
| Oportunidades | `GET/POST /deals`, `GET/PATCH/DELETE /deals/{id}`, `POST /deals/{id}/stage` |
| Histórico e interações | `GET /deals/{id}/stage-history`, `GET/POST /deals/{id}/interactions` |

## Configurações operacionais

- `ACCESS_TOKEN_MINUTES`, `REFRESH_TOKEN_DAYS` e `JWT_ALGORITHM` controlam os tokens.
- `LOGIN_RATE_LIMIT` configura o limite por endereço IP; padrão `5/minute`.
- `RATE_LIMIT_STORAGE_URI` usa `memory://` por padrão. Em produção com mais de um processo/instância, configure armazenamento compartilhado compatível com SlowAPI, como Redis.
- `ENVIRONMENT=production` requer um `JWT_SECRET_KEY` diferente do segredo padrão de desenvolvimento.
- O frontend mantém os tokens na sessão do navegador. Sirva a aplicação por HTTPS em produção e proteja-a contra XSS.
- O rate limit em memória, as origens CORS locais e o servidor Vite são configurações de desenvolvimento; ajuste-as para produção.

## Estrutura

```text
.
├── backend/
│   ├── app/                 # API, modelos, autenticação e rotas
│   ├── tests/               # Testes Pytest
│   ├── .env.example
│   └── requirements.txt
├── frontend/
│   ├── src/                 # Aplicação React e testes Vitest
│   ├── .env.example
│   └── package.json
├── schema.sql
└── QUALITY_REPORT.md
```
