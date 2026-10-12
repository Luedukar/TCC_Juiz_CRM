-- CRM B2B: arquitetura relacional inicial (PostgreSQL 15+)
-- Cada workspace representa uma equipe/tenant. O backend deve aplicar RBAC:
-- gestor pode consultar todos os registros do workspace; vendedor apenas os
-- negócios/contatos/empresas sob sua responsabilidade. Constraints garantem
-- integridade entre workspace, usuários e entidades; autorização é da aplicação.

BEGIN;

CREATE TYPE member_role AS ENUM ('manager', 'seller');
CREATE TYPE lead_temperature AS ENUM ('cold', 'warm', 'hot');
CREATE TYPE interaction_kind AS ENUM ('meeting', 'email', 'call', 'note');
CREATE TYPE opportunity_status AS ENUM ('open', 'won', 'lost');
CREATE TYPE consent_purpose AS ENUM ('marketing', 'communications', 'data_processing');

CREATE TABLE workspaces (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name            VARCHAR(160) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE users (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workspace_id    BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    full_name       VARCHAR(160) NOT NULL,
    email           VARCHAR(254) NOT NULL,
    password_hash   TEXT NOT NULL,
    role            member_role NOT NULL DEFAULT 'seller',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, id),
    UNIQUE (workspace_id, email)
);

CREATE TABLE companies (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workspace_id    BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    owner_user_id   BIGINT NOT NULL,
    name            VARCHAR(200) NOT NULL,
    legal_name      VARCHAR(240),
    tax_id          VARCHAR(40),
    website         VARCHAR(500),
    industry        VARCHAR(120),
    phone           VARCHAR(40),
    address         JSONB NOT NULL DEFAULT '{}'::jsonb,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, id),
    FOREIGN KEY (workspace_id, owner_user_id) REFERENCES users(workspace_id, id),
    UNIQUE (workspace_id, tax_id)
);

CREATE TABLE contacts (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workspace_id    BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    company_id      BIGINT,
    owner_user_id   BIGINT NOT NULL,
    full_name       VARCHAR(180) NOT NULL,
    email           VARCHAR(254),
    phone           VARCHAR(40),
    job_title       VARCHAR(120),
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, id),
    FOREIGN KEY (workspace_id, owner_user_id) REFERENCES users(workspace_id, id),
    FOREIGN KEY (workspace_id, company_id) REFERENCES companies(workspace_id, id) ON DELETE SET NULL (company_id)
);

CREATE TABLE pipelines (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workspace_id    BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name            VARCHAR(120) NOT NULL,
    is_default      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, id),
    UNIQUE (workspace_id, name)
);

CREATE TABLE pipeline_stages (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workspace_id    BIGINT NOT NULL,
    pipeline_id     BIGINT NOT NULL,
    name            VARCHAR(100) NOT NULL,
    position        INTEGER NOT NULL CHECK (position >= 0),
    probability     NUMERIC(5,2) NOT NULL DEFAULT 0 CHECK (probability BETWEEN 0 AND 100),
    is_won          BOOLEAN NOT NULL DEFAULT FALSE,
    is_lost         BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, id),
    UNIQUE (workspace_id, pipeline_id, id),
    UNIQUE (pipeline_id, position),
    UNIQUE (pipeline_id, name),
    CHECK (NOT (is_won AND is_lost)),
    FOREIGN KEY (workspace_id, pipeline_id) REFERENCES pipelines(workspace_id, id) ON DELETE CASCADE
);

CREATE TABLE opportunities (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workspace_id        BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    pipeline_id         BIGINT NOT NULL,
    stage_id            BIGINT NOT NULL,
    company_id          BIGINT,
    primary_contact_id  BIGINT,
    owner_user_id       BIGINT NOT NULL,
    title               VARCHAR(220) NOT NULL,
    amount              NUMERIC(14,2) CHECK (amount IS NULL OR amount >= 0),
    currency            CHAR(3) NOT NULL DEFAULT 'BRL',
    temperature         lead_temperature NOT NULL DEFAULT 'warm',
    status              opportunity_status NOT NULL DEFAULT 'open',
    expected_close_date DATE,
    next_action         VARCHAR(240),
    next_action_at      TIMESTAMPTZ,
    lost_reason         TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at           TIMESTAMPTZ,
    UNIQUE (workspace_id, id),
    FOREIGN KEY (workspace_id, pipeline_id) REFERENCES pipelines(workspace_id, id),
    FOREIGN KEY (workspace_id, pipeline_id, stage_id) REFERENCES pipeline_stages(workspace_id, pipeline_id, id),
    FOREIGN KEY (workspace_id, company_id) REFERENCES companies(workspace_id, id) ON DELETE SET NULL (company_id),
    FOREIGN KEY (workspace_id, primary_contact_id) REFERENCES contacts(workspace_id, id) ON DELETE SET NULL (primary_contact_id),
    FOREIGN KEY (workspace_id, owner_user_id) REFERENCES users(workspace_id, id)
);

CREATE TABLE interactions (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workspace_id        BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    opportunity_id      BIGINT NOT NULL,
    contact_id          BIGINT,
    created_by_user_id  BIGINT NOT NULL,
    kind                interaction_kind NOT NULL,
    subject             VARCHAR(220) NOT NULL,
    body                TEXT,
    occurred_at         TIMESTAMPTZ NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, opportunity_id) REFERENCES opportunities(workspace_id, id) ON DELETE CASCADE,
    FOREIGN KEY (workspace_id, contact_id) REFERENCES contacts(workspace_id, id) ON DELETE SET NULL (contact_id),
    FOREIGN KEY (workspace_id, created_by_user_id) REFERENCES users(workspace_id, id)
);

-- Guarda o consentimento e sua trilha de auditoria para cada titular/finalidade.
-- Não armazena texto livre sensível; source identifica a origem do registro.
CREATE TABLE data_consents (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workspace_id    BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    contact_id      BIGINT NOT NULL,
    purpose         consent_purpose NOT NULL,
    granted         BOOLEAN NOT NULL,
    source          VARCHAR(160) NOT NULL,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, contact_id) REFERENCES contacts(workspace_id, id) ON DELETE CASCADE
);

-- Consulta Kanban por pipeline/etapa, carteira do vendedor e ações pendentes.
CREATE INDEX idx_opportunities_board ON opportunities(workspace_id, pipeline_id, stage_id, status);
CREATE INDEX idx_opportunities_owner ON opportunities(workspace_id, owner_user_id, status);
CREATE INDEX idx_opportunities_next_action ON opportunities(workspace_id, next_action_at) WHERE status = 'open';
CREATE INDEX idx_interactions_opportunity_time ON interactions(workspace_id, opportunity_id, occurred_at DESC);
CREATE INDEX idx_contacts_company ON contacts(workspace_id, company_id);
CREATE INDEX idx_companies_owner ON companies(workspace_id, owner_user_id);
CREATE INDEX idx_data_consents_contact_time ON data_consents(workspace_id, contact_id, recorded_at DESC);

COMMIT;
