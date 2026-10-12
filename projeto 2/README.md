# Vela CRM — gestão de vendas B2B

CRM para equipes B2B com funis configuráveis, oportunidades em Kanban, contatos e empresas, histórico de interações e controle de acesso por papel e carteira.

## Requisitos

- PostgreSQL 15 ou superior.
- Python 3.10 ou superior para a API e os testes.
- Node.js 20 ou superior para o frontend.

## Estrutura

```text
app/                         API FastAPI, autenticação e regras de acesso
frontend/                    React + TypeScript, interface Kanban
migrations/                  alterações incrementais do banco
schema.sql                   esquema PostgreSQL inicial
tests/                       testes de permissões e movimentação
requirements.txt             dependências da API
requirements-dev.txt         dependências de teste
```

## 1. Banco de dados

Crie um banco PostgreSQL e configure uma URL de conexão. Exemplo em `psql`:

```sql
CREATE USER crm WITH PASSWORD 'troque-esta-senha';
CREATE DATABASE crm OWNER crm;
```

Na raiz do projeto, copie `.env.example` para `.env`. Ajuste `DATABASE_URL` com as credenciais locais e defina um `JWT_SECRET` aleatório com pelo menos 32 caracteres. O exemplo de `.env.example` é apenas para desenvolvimento local; troque as credenciais antes de qualquer uso compartilhado.

Execute os scripts na ordem indicada:

```powershell
psql "postgresql://crm:SENHA@localhost:5432/crm" -f schema.sql
psql "postgresql://crm:SENHA@localhost:5432/crm" -f migrations/002_auth_sessions.sql
```

O sistema ainda não tem endpoint de cadastro público de usuários. Crie o workspace e o usuário gestor inicial por provisionamento administrativo. Gere uma senha Argon2 com:

```powershell
python -c "from app.security import hash_password; print(hash_password('SENHA_FORTE'))"
```

Use o hash retornado ao inserir o gestor. Exemplo SQL (substitua `HASH_ARGON2_GERADO` pelo valor impresso e ajuste os dados):

```sql
WITH created_workspace AS (
  INSERT INTO workspaces (name) VALUES ('Equipe Comercial') RETURNING id
)
INSERT INTO users (workspace_id, full_name, email, password_hash, role)
SELECT id, 'Gestor CRM', 'gestor@empresa.com', 'HASH_ARGON2_GERADO', 'manager' FROM created_workspace;
```

O CTE cria o workspace e usa seu ID para criar o gestor na mesma instrução. Em seguida, configure um funil e suas etapas como gestor pelas rotas da API ou por provisionamento.

## 2. API

A partir da raiz, instale as dependências e inicie o servidor:

```powershell
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

A API fica em `http://localhost:8000`. O contrato interativo fica em `http://localhost:8000/docs`; `/health` verifica a conexão com o banco.

### Rotas principais

| Área | Rotas |
|---|---|
| Autenticação | `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me` |
| Empresas e contatos | `GET/POST /companies`, `GET/POST /contacts` |
| Funis e etapas | `GET/POST /pipelines`, `POST /pipelines/{pipeline_id}/stages` |
| Oportunidades | `GET/POST /opportunities`, `GET/PATCH /opportunities/{opportunity_id}` |
| Interações | `GET/POST /opportunities/{opportunity_id}/interactions` |
| Consentimento | `POST /contacts/{contact_id}/consents` |
| Usuários | `GET /users` (gestores) |

### Acesso e segurança

- Gestores consultam os registros de sua equipe; vendedores têm o escopo da própria carteira nas consultas e alterações de oportunidades, empresas e contatos.
- Todas as consultas de negócio são limitadas ao `workspace_id` da sessão.
- Access tokens JWT têm duração curta. Refresh tokens são armazenados como hash, rotacionados no refresh e revogáveis no logout.
- Senhas devem ser armazenadas como hashes Argon2 com `app.security.hash_password`.
- O limite inicial de login é `5/minute` por endereço IP, configurável por `LOGIN_RATE_LIMIT`.
- Exceções inesperadas são registradas no log e respondem com mensagem genérica.
- A lista de origens CORS vem de `CORS_ORIGINS`; o padrão local é `http://localhost:5173`.

O rate limiter usa armazenamento local por padrão. Em múltiplas instâncias, configure armazenamento compartilhado do SlowAPI antes de escalar horizontalmente.

## 3. Frontend

Em outro terminal:

```powershell
cd frontend
Copy-Item .env.example .env
npm install
npm run dev
```

A interface fica em `http://localhost:5173`. Ajuste `VITE_API_URL` em `frontend/.env` para apontar à API. A origem do navegador também precisa estar em `CORS_ORIGINS` no `.env` da raiz do backend. Para gerar a versão de produção, execute `npm run build` dentro de `frontend/`.

O Kanban oferece troca de funil, busca, filtro de oportunidades quentes, ordenação, movimentação de cards, criação e edição rápida em painel lateral. A interface apresenta carregamento, erro após 15 segundos sem resposta em consultas GET e falha de rede, e reverte uma movimentação quando a API não a aceita. A sessão é mantida no armazenamento local do navegador e renova o access token após resposta 401.

## 4. Testes automatizados e qualidade

Instale as dependências da API e de desenvolvimento e execute a suíte na raiz:

```powershell
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q
```

### Cobertura implementada

| Caso | Resultado esperado | Resultado da última execução |
|---|---|---|
| Vendedor lista oportunidades | Somente oportunidades próprias | Passou |
| Gestor lista oportunidades | Todas as oportunidades do workspace | Passou |
| Vendedor move oportunidade própria para etapa do mesmo funil | Movimento aplicado | Passou |
| Vendedor tenta mover oportunidade de outro vendedor | Resposta 404 e card inalterado | Passou |
| Oportunidade é movida para etapa de outro funil | Resposta 422 e card inalterado | Passou |
| PATCH com `null` em campo obrigatório | Validação rejeita o payload | Passou |

**Resultado registrado:** `6 passed` em Python 3.14 com pytest 8.4.2. A execução exibiu um `DeprecationWarning` dentro do SlowAPI instalado; não houve falhas. A compilação de produção do frontend também concluiu com `npm run build`.

Os testes substituem a conexão por um fake e chamam diretamente as funções das rotas. Assim, verificam as regras de autorização e movimentação sem depender de PostgreSQL. Não cobrem autenticação JWT ponta a ponta, integração com banco real, comportamento do navegador ou compilação do frontend.

## Documentação por módulo

- [Backend](README-backend.md)
- [Frontend](frontend/README.md)







