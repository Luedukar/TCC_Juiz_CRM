# CRM B2B

Sistema web de CRM para equipes de vendas B2B: funil de vendas em **Kanban** com drag-and-drop, cadastro de
empresas e contatos, histórico de interações, controle de acesso por perfil e recursos de **LGPD**.

| Camada | Tecnologias |
|---|---|
| Backend | Python 3.12, **FastAPI**, SQLAlchemy 2, Pydantic v2, argon2, PyJWT |
| Banco | **PostgreSQL** 13+ (enums, `citext`, triggers; DDL em `backend/db/schema.sql`) |
| Frontend | **React 18 + TypeScript**, Vite, Tailwind CSS 3, dnd-kit, TanStack Query |
| Testes | pytest (+ PostgreSQL real), Vitest + React Testing Library |
| CI | GitHub Actions (`.github/workflows/ci.yml`) |

## Sumário

1. [Funcionalidades](#funcionalidades) · 2. [Perfis e permissões](#perfis-e-permissões) · 3. [Início rápido](#início-rápido)
4. [Configuração](#configuração) · 5. [Uso](#uso) · 6. [Arquitetura](#arquitetura) · 7. [Segurança](#segurança)
8. [LGPD](#lgpd) · 9. [Testes e qualidade](#testes-e-qualidade) · 10. [Produção](#checklist-para-produção)
11. [Limitações conhecidas](#limitações-conhecidas) · 12. [Solução de problemas](#solução-de-problemas)

## Funcionalidades

- **Funil Kanban**: etapas customizáveis (nome, cor, probabilidade, etapas de ganho/perda), movimentação por
  drag-and-drop (mouse, toque e teclado), totais e valor por coluna, resumo com **previsão ponderada**.
- **Temperatura do lead** (frio/morno/quente) com cores e **indicador de próxima ação** (atrasada, agendada ou
  "sem próxima ação").
- **Formulário lateral** para edição rápida do negócio, com validação e erros do servidor por campo.
- **Empresas e contatos** (CNPJ validado, contato principal único por empresa).
- **Histórico de interações** (reunião, e-mail, ligação) por negócio, com data/hora e autor.
- **Histórico de movimentação** de cada negócio entre etapas (quem moveu e quando).
- **Resiliência**: esqueleto de carregamento, aviso de API lenta, quadro salvo em modo somente leitura quando a API
  cai, atualização otimista com desfazer automático em caso de erro.

## Perfis e permissões

| Recurso | Vendedor (`sales_rep`) | Gestor (`sales_manager`) |
|---|---|---|
| Negócios, empresas, contatos, interações | Apenas da **própria carteira** (`owner_id`) | Todos |
| Registro de outro vendedor | Responde **404** (não revela que existe) | — |
| Atribuir/transferir registros | Só para si mesmo | Para qualquer usuário ativo |
| Quadro Kanban | Só seus cards e totais | Tudo; pode filtrar por vendedor |
| Editar/excluir interação | Apenas as que criou | Qualquer uma |
| Usuários, funis e etapas | — | Gerencia |
| Anonimizar contato (LGPD) | — | Sim |

O papel é sempre lido do banco, nunca da claim do token.

## Início rápido

Pré-requisitos: **Docker**, **Python 3.12+** e **Node 20+**.

```bash
# 1) Banco de dados (aplica backend/db/schema.sql na primeira inicialização do volume)
cd backend
docker compose up -d db

# 2) Backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env     # defina JWT_SECRET (>= 32 caracteres):
                         # python -c "import secrets; print(secrets.token_urlsafe(48))"
python -m scripts.create_manager --name "Seu Nome" --email voce@empresa.com   # pede a senha
uvicorn app.main:app --reload                          # API em http://localhost:8000  (docs em /docs)

# 3) Frontend (em outro terminal)
cd frontend
npm install
npm run dev                                            # http://localhost:5173
```

Abra `http://localhost:5173`, entre com o gestor criado e aceite os termos. Crie vendedores em `POST /api/v1/users`
(documentação interativa em `/docs`). O Vite encaminha `/api` para a porta 8000, então não há CORS em desenvolvimento.

> O schema só é aplicado quando o volume do banco é criado. Para recriar do zero: `docker compose down -v`.

## Configuração

### Backend (`backend/.env`)

| Variável | Padrão | Descrição |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg2://crm:crm@localhost:5432/crm` | Conexão com o PostgreSQL |
| `JWT_SECRET` | **obrigatória** | Segredo de assinatura (mín. 32 caracteres); a API não sobe sem ele |
| `ACCESS_TOKEN_MINUTES` | `15` | Validade do token de acesso |
| `REFRESH_TOKEN_DAYS` | `7` | Validade do refresh token |
| `REFRESH_REUSE_GRACE_SECONDS` | `10` | Janela em que reapresentar um token recém-rotacionado é tratado como corrida entre abas, não como roubo |
| `MAX_FAILED_LOGINS` / `LOCKOUT_MINUTES` | `5` / `15` | Bloqueio temporário da conta |
| `LOGIN_RATE_LIMIT_ATTEMPTS` / `_WINDOW_SECONDS` | `5` / `60` | Falhas de login por IP na janela |
| `REFRESH_RATE_LIMIT_ATTEMPTS` / `_WINDOW_SECONDS` | `30` / `60` | Renovações por IP na janela |
| `TRUST_PROXY_HEADERS` | `false` | Use o IP de `X-Forwarded-For` (só atrás de proxy confiável) |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | Origens permitidas (lista JSON) |
| `ENVIRONMENT` | `development` | Com `production`, `/docs`, `/redoc` e `/openapi.json` são desativados |

### Frontend

| Variável | Padrão | Descrição |
|---|---|---|
| `VITE_API_URL` | `/api/v1` | URL base da API (em produção, ex.: `https://api.suaempresa.com/api/v1`) |

## Uso

**Gestor**: crie vendedores e ajuste o funil (etapas, cores, ordem) pela API; no quadro, filtre por vendedor e
acompanhe totais e previsão.
**Vendedor**: no quadro, arraste os cards entre etapas (ao soltar em "Perdido" informe o motivo), clique no ✏️ para abrir
o formulário lateral (dados do negócio, temperatura, próxima ação) e na aba **Interações** para registrar contatos.

### API (prefixo `/api/v1`)

| Grupo | Endpoints principais |
|---|---|
| Autenticação | `POST /auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/logout-all`, `GET /auth/me`, `POST /auth/accept-terms` |
| Usuários (gestor) | `GET/POST /users`, `PATCH /users/{id}` |
| Empresas | `GET/POST /companies`, `GET/PATCH/DELETE /companies/{id}` |
| Contatos | `GET/POST /contacts`, `GET/PATCH/DELETE /contacts/{id}`, `GET/POST /contacts/{id}/consents`, `POST /contacts/{id}/anonymize` |
| Funil | `GET /pipelines`, `POST/PATCH /pipelines`, `POST /pipelines/{id}/stages`, `PUT /pipelines/{id}/stages/order`, `PATCH/DELETE /stages/{id}` |
| Negócios | `GET/POST /deals`, `GET/PATCH/DELETE /deals/{id}`, `GET /deals/board`, `POST /deals/{id}/move`, `GET /deals/next-actions` |
| Interações | `GET/POST /deals/{id}/interactions`, `PATCH/DELETE /interactions/{id}` |
| Infra | `GET /health`, `GET /health/ready` (verifica o banco) |

Erros seguem sempre o formato `{"error": {"code", "message", "details", "request_id"}}`. Datas/horas usam ISO 8601
**com fuso horário**.

## Arquitetura

```
crm-b2b/
├── backend/
│   ├── app/
│   │   ├── main.py            # criação da app, middlewares, rotas
│   │   ├── config.py          # configurações (variáveis de ambiente)
│   │   ├── models.py          # ORM mapeando o schema.sql
│   │   ├── schemas.py         # validação de entrada/saída (Pydantic)
│   │   ├── security.py        # argon2, JWT, refresh tokens
│   │   ├── deps.py            # autenticação e RBAC (escopo da carteira)
│   │   ├── ratelimit.py       # limitador por janela deslizante
│   │   ├── errors.py          # erros de domínio + tratamento global
│   │   ├── audit.py           # trilha de auditoria
│   │   └── routers/           # auth, users, companies, contacts, pipelines, deals, interactions
│   ├── db/schema.sql          # DDL: tabelas, índices, triggers, funil padrão
│   ├── scripts/create_manager.py
│   ├── tests/                 # unit/ e integration/
│   └── docker-compose.yml     # db (dev) e db-test (testes)
├── frontend/
│   └── src/
│       ├── lib/               # api (sessão, timeout, erros), dnd, boardOps, snapshot, formatação
│       ├── auth/              # contexto de autenticação
│       ├── hooks/             # useBoard, API lenta, status online
│       ├── components/        # Kanban, card, coluna, formulário lateral, banners
│       └── pages/             # Login e quadro
├── scripts/quality_report.py  # consolida os resultados reais dos testes
├── docs/                      # TESTES.md, RELATORIO_QUALIDADE.md
└── .github/workflows/ci.yml
```

**Modelo de dados** (`backend/db/schema.sql`): `users`, `refresh_tokens`, `companies`, `contacts`, `contact_consents`,
`pipelines`, `pipeline_stages`, `deals`, `deal_stage_history`, `interactions`, `audit_logs`. Pontos de projeto:

- Chave estrangeira composta garante que a etapa de um negócio pertence ao **mesmo funil** dele.
- A posição do card na coluna é fracionária (`deals.position`): mover um card atualiza uma única linha, e a coluna é
  renumerada automaticamente se os vizinhos ficarem próximos demais.
- Um **trigger** atualiza `stage_entered_at`, `status` e `closed_at` ao mudar de etapa e registra o histórico.
- Exclusões lógicas (`deleted_at`) em empresas, contatos e negócios.

## Segurança

- **Senhas**: argon2id; bloqueio temporário da conta após falhas seguidas; resposta idêntica para e-mail inexistente e
  senha errada, com tempo equalizado.
- **JWT** de acesso curto (15 min) e **refresh token opaco** com rotação: só o hash é guardado; reutilizar um token já
  rotacionado revoga a sessão inteira (com tolerância para corrida entre abas). Trocar a senha ou desativar o usuário
  encerra as sessões.
- **Rate limiting** no login (só falhas contam, para não bloquear equipes atrás do mesmo IP) e no refresh.
- **Erros** padronizados e sem vazamento de detalhes internos; `X-Request-ID` em todas as respostas para suporte.
- **Autorização** sempre no servidor; a interface apenas reflete o perfil.

## LGPD

- Registro de **consentimento** por contato, finalidade (contato comercial, marketing, compartilhamento) e base legal,
  com histórico; a decisão mais recente encerra a anterior.
- **Aceite de termos** obrigatório no primeiro acesso, com data registrada.
- **Anonimização** de contato (gestor): remove dados pessoais, mantém vínculo com negócios e histórico de consentimentos.
- **Auditoria** de criação, alteração, exclusão, movimentação, consentimentos e anonimização.
- Pendências (ver limitações): política de retenção, exportação de dados do titular e texto jurídico dos termos.

## Testes e qualidade

```bash
make db-test && make test     # roda backend + frontend e gera docs/RESULTADOS_EXECUCAO.md com os números reais
```

Detalhes em [`docs/TESTES.md`](docs/TESTES.md) e o relatório em [`docs/RELATORIO_QUALIDADE.md`](docs/RELATORIO_QUALIDADE.md).
O CI executa as duas suítes, o build e a auditoria de dependências a cada push.

## Checklist para produção

- [ ] HTTPS ponta a ponta; `ENVIRONMENT=production`; `JWT_SECRET` forte e fora do repositório.
- [ ] `CORS_ORIGINS` restrito ao domínio do frontend; `TRUST_PROXY_HEADERS=true` somente atrás de proxy confiável.
- [ ] Rate limit em Redis se houver mais de uma réplica da API.
- [ ] Migrações versionadas (ex.: Alembic) a partir do `schema.sql` atual como baseline.
- [ ] Backups do PostgreSQL e rotina de restauração testada.
- [ ] Refresh token em cookie `httpOnly` (hoje fica em `localStorage`).
- [ ] Revisão jurídica dos termos de uso e da política de privacidade.
- [ ] Logs centralizados e alertas (use o `request_id` para correlacionar).

## Limitações conhecidas

- Não há telas de cadastro completo de empresas/contatos nem de administração de funis e usuários; essas operações
  existem na API (o formulário do negócio cria uma empresa rápida pela razão social).
- O refresh token fica em `localStorage` (exposto a XSS se houver falha de script injetado).
- O limitador de taxa é em memória (uma instância).
- A seleção de empresa no formulário lista até 100 registros (sem busca).
- LGPD: sem política de retenção automática nem exportação de dados do titular; a anonimização não limpa texto livre
  digitado nas anotações das interações.
- Sem testes de ponta a ponta no navegador nem de carga (veja o relatório de qualidade).

## Solução de problemas

| Sintoma | Causa provável e solução |
|---|---|
| API não sobe com erro de validação em `jwt_secret` | Defina `JWT_SECRET` (≥ 32 caracteres) no `.env` |
| `connection refused` no banco | `docker compose up -d db` e confira `DATABASE_URL` / porta 5432 |
| Tabelas não existem | O schema só roda na criação do volume: `docker compose down -v && docker compose up -d db` |
| Frontend recebe 404/erro de rede em `/api` | Backend fora do ar ou porta diferente de 8000 (ajuste `vite.config.ts` ou `VITE_API_URL`) |
| Erro de CORS em produção | Inclua a origem do frontend em `CORS_ORIGINS` (lista JSON) |
| Login responde 429 | Limite de falhas por IP; aguarde o `Retry-After` |
| Login responde 423 | Conta bloqueada por tentativas; aguarde `LOCKOUT_MINUTES` |
| `pytest` ignora os testes de integração | Defina `TEST_DATABASE_URL` (banco terminando em `_test`) |
