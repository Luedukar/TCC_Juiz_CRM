BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name       TEXT NOT NULL,
    email           TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('sales_manager', 'sales_rep')),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE companies (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    legal_name      TEXT,
    tax_id          TEXT,
    website         TEXT,
    industry        TEXT,
    phone           TEXT,
    address         JSONB NOT NULL DEFAULT '{}'::jsonb,
    owner_id        UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX companies_tax_id_unique
    ON companies (tax_id) WHERE tax_id IS NOT NULL;
CREATE INDEX companies_owner_id_idx ON companies (owner_id);
CREATE INDEX companies_name_idx ON companies (name);

CREATE TABLE contacts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      UUID REFERENCES companies(id) ON DELETE SET NULL,
    owner_id        UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    first_name      TEXT NOT NULL,
    last_name       TEXT NOT NULL,
    email           TEXT,
    phone           TEXT,
    job_title       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX contacts_company_id_idx ON contacts (company_id);
CREATE INDEX contacts_owner_id_idx ON contacts (owner_id);
CREATE INDEX contacts_email_idx ON contacts (email) WHERE email IS NOT NULL;

CREATE TABLE pipelines (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    is_default      BOOLEAN NOT NULL DEFAULT FALSE,
    created_by      UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (name)
);

CREATE UNIQUE INDEX pipelines_single_default_idx
    ON pipelines (is_default) WHERE is_default;

CREATE TABLE pipeline_stages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id     UUID NOT NULL REFERENCES pipelines(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    position        INTEGER NOT NULL CHECK (position >= 0),
    probability     SMALLINT NOT NULL DEFAULT 0 CHECK (probability BETWEEN 0 AND 100),
    is_won          BOOLEAN NOT NULL DEFAULT FALSE,
    is_lost         BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (pipeline_id, id),
    UNIQUE (pipeline_id, position),
    UNIQUE (pipeline_id, name),
    CHECK (NOT (is_won AND is_lost))
);

CREATE TABLE deals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id     UUID NOT NULL,
    stage_id        UUID NOT NULL,
    company_id      UUID REFERENCES companies(id) ON DELETE SET NULL,
    primary_contact_id UUID REFERENCES contacts(id) ON DELETE SET NULL,
    owner_id        UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    title           TEXT NOT NULL,
    amount          NUMERIC(14, 2) NOT NULL DEFAULT 0 CHECK (amount >= 0),
    currency        CHAR(3) NOT NULL DEFAULT 'USD',
    temperature     TEXT NOT NULL DEFAULT 'warm'
                    CHECK (temperature IN ('cold', 'warm', 'hot')),
    expected_close_date DATE,
    next_action     TEXT,
    next_action_at  TIMESTAMPTZ,
    lost_reason     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at       TIMESTAMPTZ,
    FOREIGN KEY (pipeline_id, stage_id)
        REFERENCES pipeline_stages (pipeline_id, id) ON DELETE RESTRICT
);

CREATE INDEX deals_owner_stage_idx ON deals (owner_id, pipeline_id, stage_id);
CREATE INDEX deals_pipeline_stage_idx ON deals (pipeline_id, stage_id);
CREATE INDEX deals_company_id_idx ON deals (company_id);
CREATE INDEX deals_primary_contact_id_idx ON deals (primary_contact_id);
CREATE INDEX deals_next_action_at_idx ON deals (owner_id, next_action_at)
    WHERE next_action_at IS NOT NULL;

CREATE TABLE deal_stage_history (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deal_id         UUID NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
    from_stage_id   UUID REFERENCES pipeline_stages(id) ON DELETE RESTRICT,
    to_stage_id     UUID NOT NULL REFERENCES pipeline_stages(id) ON DELETE RESTRICT,
    changed_by      UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    changed_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX deal_stage_history_deal_changed_idx
    ON deal_stage_history (deal_id, changed_at DESC);

CREATE TABLE interactions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deal_id         UUID NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
    contact_id      UUID REFERENCES contacts(id) ON DELETE SET NULL,
    created_by      UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    type            TEXT NOT NULL CHECK (type IN ('meeting', 'email', 'call')),
    subject         TEXT NOT NULL,
    notes           TEXT,
    occurred_at     TIMESTAMPTZ NOT NULL,
    duration_minutes INTEGER CHECK (duration_minutes IS NULL OR duration_minutes >= 0),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX interactions_deal_occurred_idx
    ON interactions (deal_id, occurred_at DESC);
CREATE INDEX interactions_contact_id_idx ON interactions (contact_id);

CREATE TABLE data_consents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contact_id      UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    purpose         TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('granted', 'withdrawn')),
    legal_basis     TEXT,
    source          TEXT,
    recorded_by     UUID REFERENCES users(id) ON DELETE SET NULL,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX data_consents_contact_recorded_idx
    ON data_consents (contact_id, recorded_at DESC);

CREATE TABLE auth_refresh_tokens (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    jti             UUID NOT NULL UNIQUE,
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX auth_refresh_tokens_user_id_idx ON auth_refresh_tokens (user_id);

COMMIT;
