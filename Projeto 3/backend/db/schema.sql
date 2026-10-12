-- =====================================================================
-- CRM B2B - Schema PostgreSQL (Entregável 1)
-- Requer PostgreSQL 13+ (gen_random_uuid nativo; pgcrypto por segurança)
-- =====================================================================

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;

-- ---------------------------------------------------------------------
-- Tipos enumerados
-- ---------------------------------------------------------------------
CREATE TYPE user_role        AS ENUM ('sales_manager', 'sales_rep');
CREATE TYPE lead_temperature AS ENUM ('cold', 'warm', 'hot');
CREATE TYPE deal_status      AS ENUM ('open', 'won', 'lost');
CREATE TYPE interaction_type AS ENUM ('meeting', 'email', 'call');
CREATE TYPE next_action_type AS ENUM ('meeting', 'email', 'call', 'proposal', 'follow_up', 'other');
CREATE TYPE consent_purpose  AS ENUM ('commercial_contact', 'marketing', 'data_sharing');
CREATE TYPE consent_basis    AS ENUM ('consent', 'legitimate_interest', 'contract');

-- ---------------------------------------------------------------------
-- Função utilitária: updated_at automático
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------
-- USUÁRIOS E AUTENTICAÇÃO
-- ---------------------------------------------------------------------
CREATE TABLE users (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name           varchar(150) NOT NULL,
  email          citext NOT NULL UNIQUE,
  password_hash  text NOT NULL,                       -- argon2id/bcrypt, nunca senha em claro
  role           user_role NOT NULL DEFAULT 'sales_rep',
  is_active      boolean NOT NULL DEFAULT true,
  failed_logins  smallint NOT NULL DEFAULT 0,         -- apoio ao rate limit / bloqueio temporário
  locked_until   timestamptz,
  last_login_at  timestamptz,
  terms_accepted_at timestamptz,                      -- aceite dos termos/política de privacidade (LGPD)
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_users_updated BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Refresh tokens com rotação e detecção de reuso (family_id)
CREATE TABLE refresh_tokens (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  family_id    uuid NOT NULL,                         -- agrupa tokens de uma mesma sessão
  token_hash   char(64) NOT NULL UNIQUE,              -- SHA-256 do token; o token em si não é armazenado
  expires_at   timestamptz NOT NULL,
  revoked_at   timestamptz,
  replaced_by  uuid REFERENCES refresh_tokens(id),
  user_agent   text,
  ip_address   inet,
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_refresh_tokens_user   ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_family ON refresh_tokens(family_id);

-- ---------------------------------------------------------------------
-- EMPRESAS E CONTATOS
-- ---------------------------------------------------------------------
CREATE TABLE companies (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id     uuid NOT NULL REFERENCES users(id),    -- dono da carteira (base do RBAC)
  legal_name   varchar(200) NOT NULL,
  trade_name   varchar(200),
  cnpj         char(14) UNIQUE CHECK (cnpj IS NULL OR cnpj ~ '^[0-9]{14}$'),
  industry     varchar(100),
  size         varchar(30),                           -- ex.: micro, pequena, média, grande
  website      varchar(255),
  phone        varchar(30),
  address_line varchar(255),
  city         varchar(100),
  state        char(2),
  zip_code     varchar(10),
  notes        text,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now(),
  deleted_at   timestamptz                            -- soft delete
);
CREATE INDEX idx_companies_owner ON companies(owner_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_companies_name  ON companies(lower(legal_name));
CREATE TRIGGER trg_companies_updated BEFORE UPDATE ON companies
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE contacts (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id     uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  owner_id       uuid NOT NULL REFERENCES users(id),
  full_name      varchar(150) NOT NULL,
  email          citext,
  phone          varchar(30),
  job_title      varchar(100),
  is_primary     boolean NOT NULL DEFAULT false,
  notes          text,
  anonymized_at  timestamptz,                         -- LGPD: anonimização a pedido do titular
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now(),
  deleted_at     timestamptz
);
CREATE INDEX idx_contacts_company ON contacts(company_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_contacts_owner   ON contacts(owner_id)   WHERE deleted_at IS NULL;
CREATE INDEX idx_contacts_email   ON contacts(email);
-- No máximo um contato principal por empresa
CREATE UNIQUE INDEX uq_contacts_primary_per_company
  ON contacts(company_id) WHERE is_primary AND deleted_at IS NULL;
CREATE TRIGGER trg_contacts_updated BEFORE UPDATE ON contacts
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- LGPD: registro de consentimento / base legal por contato e finalidade
CREATE TABLE contact_consents (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  contact_id  uuid NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
  purpose     consent_purpose NOT NULL,
  basis       consent_basis NOT NULL DEFAULT 'consent',
  granted     boolean NOT NULL,
  source      varchar(100),                           -- ex.: formulário, reunião, e-mail
  evidence    text,                                   -- referência/prova do consentimento
  recorded_by uuid REFERENCES users(id),
  granted_at  timestamptz NOT NULL DEFAULT now(),
  revoked_at  timestamptz
);
CREATE INDEX idx_consents_contact ON contact_consents(contact_id, purpose);

-- ---------------------------------------------------------------------
-- FUNIL DE VENDAS (núcleo do modelo)
-- ---------------------------------------------------------------------
CREATE TABLE pipelines (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name        varchar(100) NOT NULL UNIQUE,
  is_default  boolean NOT NULL DEFAULT false,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_pipelines_default ON pipelines((true)) WHERE is_default;

-- Etapas customizáveis: ordem, probabilidade e cor por etapa
CREATE TABLE pipeline_stages (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  pipeline_id  uuid NOT NULL REFERENCES pipelines(id) ON DELETE CASCADE,
  name         varchar(80) NOT NULL,
  position     integer NOT NULL CHECK (position >= 0),
  probability  smallint NOT NULL DEFAULT 0 CHECK (probability BETWEEN 0 AND 100),
  color        char(7) NOT NULL DEFAULT '#94A3B8' CHECK (color ~ '^#[0-9A-Fa-f]{6}$'),
  is_won       boolean NOT NULL DEFAULT false,
  is_lost      boolean NOT NULL DEFAULT false,
  created_at   timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_stage_not_both CHECK (NOT (is_won AND is_lost)),
  CONSTRAINT uq_stage_name     UNIQUE (pipeline_id, name),
  CONSTRAINT uq_stage_position UNIQUE (pipeline_id, position) DEFERRABLE INITIALLY DEFERRED,
  CONSTRAINT uq_stage_with_pipeline UNIQUE (id, pipeline_id)  -- alvo da FK composta em deals
);

CREATE TABLE deals (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  pipeline_id       uuid NOT NULL,
  stage_id          uuid NOT NULL,
  company_id        uuid NOT NULL REFERENCES companies(id),
  primary_contact_id uuid REFERENCES contacts(id) ON DELETE SET NULL,
  owner_id          uuid NOT NULL REFERENCES users(id),   -- vendedor responsável (RBAC)
  title             varchar(200) NOT NULL,
  value             numeric(14,2) NOT NULL DEFAULT 0 CHECK (value >= 0),
  currency          char(3) NOT NULL DEFAULT 'BRL',
  temperature       lead_temperature NOT NULL DEFAULT 'cold',  -- cold=azul, warm=amarelo, hot=vermelho (UI)
  status            deal_status NOT NULL DEFAULT 'open',
  position          numeric(20,10) NOT NULL DEFAULT 0,    -- ordem do card na coluna (ordenação fracionária)
  expected_close_date date,
  -- Indicador de próxima ação
  next_action_type  next_action_type,
  next_action_at    timestamptz,
  next_action_note  varchar(255),
  stage_entered_at  timestamptz NOT NULL DEFAULT now(),
  closed_at         timestamptz,
  lost_reason       varchar(255),
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  deleted_at        timestamptz,
  -- Garante que a etapa pertence ao mesmo funil do negócio
  CONSTRAINT fk_deal_stage_pipeline FOREIGN KEY (stage_id, pipeline_id)
    REFERENCES pipeline_stages(id, pipeline_id),
  CONSTRAINT chk_deal_closed CHECK (
    (status = 'open' AND closed_at IS NULL) OR (status <> 'open' AND closed_at IS NOT NULL)
  ),
  CONSTRAINT chk_deal_lost_reason CHECK (status <> 'lost' OR lost_reason IS NOT NULL)
);
-- Consulta principal do Kanban: cards por responsável/etapa na ordem de exibição
CREATE INDEX idx_deals_board     ON deals(pipeline_id, stage_id, position) WHERE deleted_at IS NULL AND status = 'open';
CREATE INDEX idx_deals_owner     ON deals(owner_id, stage_id)              WHERE deleted_at IS NULL;
CREATE INDEX idx_deals_company   ON deals(company_id);
CREATE INDEX idx_deals_next_act  ON deals(next_action_at)                  WHERE deleted_at IS NULL AND status = 'open';
CREATE TRIGGER trg_deals_updated BEFORE UPDATE ON deals
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Histórico de movimentação entre etapas (auditoria + métricas de funil)
CREATE TABLE deal_stage_history (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  deal_id       uuid NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
  from_stage_id uuid REFERENCES pipeline_stages(id),
  to_stage_id   uuid NOT NULL REFERENCES pipeline_stages(id),
  moved_by      uuid REFERENCES users(id),
  moved_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_stage_history_deal ON deal_stage_history(deal_id, moved_at DESC);

-- Trigger: ao mudar de etapa, atualiza stage_entered_at/status e registra histórico.
-- A aplicação pode informar o usuário via: SET LOCAL app.current_user_id = '<uuid>';
CREATE OR REPLACE FUNCTION deals_on_stage_change() RETURNS trigger AS $$
DECLARE
  v_won  boolean;
  v_lost boolean;
BEGIN
  IF NEW.stage_id IS DISTINCT FROM OLD.stage_id THEN
    NEW.stage_entered_at := now();
    SELECT is_won, is_lost INTO v_won, v_lost FROM pipeline_stages WHERE id = NEW.stage_id;
    IF v_won THEN
      NEW.status := 'won';  NEW.closed_at := COALESCE(NEW.closed_at, now());
    ELSIF v_lost THEN
      NEW.status := 'lost'; NEW.closed_at := COALESCE(NEW.closed_at, now());
    ELSE
      NEW.status := 'open'; NEW.closed_at := NULL;
    END IF;
    INSERT INTO deal_stage_history(deal_id, from_stage_id, to_stage_id, moved_by)
    VALUES (NEW.id, OLD.stage_id, NEW.stage_id,
            NULLIF(current_setting('app.current_user_id', true), '')::uuid);
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER trg_deals_stage_change BEFORE UPDATE OF stage_id ON deals
  FOR EACH ROW EXECUTE FUNCTION deals_on_stage_change();

-- ---------------------------------------------------------------------
-- HISTÓRICO DE INTERAÇÕES
-- ---------------------------------------------------------------------
CREATE TABLE interactions (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  deal_id          uuid NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
  contact_id       uuid REFERENCES contacts(id) ON DELETE SET NULL,
  user_id          uuid NOT NULL REFERENCES users(id),
  type             interaction_type NOT NULL,
  subject          varchar(200) NOT NULL,
  notes            text,
  occurred_at      timestamptz NOT NULL,              -- data e hora da interação
  duration_minutes integer CHECK (duration_minutes IS NULL OR duration_minutes >= 0),
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_interactions_deal ON interactions(deal_id, occurred_at DESC);
CREATE INDEX idx_interactions_user ON interactions(user_id, occurred_at DESC);
CREATE TRIGGER trg_interactions_updated BEFORE UPDATE ON interactions
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------
-- AUDITORIA (LGPD: rastreabilidade de acesso/alteração de dados pessoais)
-- ---------------------------------------------------------------------
CREATE TABLE audit_logs (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id     uuid REFERENCES users(id) ON DELETE SET NULL,
  action      varchar(50) NOT NULL,                   -- ex.: create, update, delete, export, anonymize
  entity      varchar(50) NOT NULL,
  entity_id   uuid,
  details     jsonb,
  ip_address  inet,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_entity ON audit_logs(entity, entity_id);
CREATE INDEX idx_audit_user   ON audit_logs(user_id, created_at DESC);

-- ---------------------------------------------------------------------
-- SEED: funil padrão com etapas iniciais (customizáveis depois)
-- ---------------------------------------------------------------------
WITH p AS (
  INSERT INTO pipelines(name, is_default) VALUES ('Funil Padrão', true) RETURNING id
)
INSERT INTO pipeline_stages(pipeline_id, name, position, probability, color, is_won, is_lost)
SELECT p.id, s.name, s.pos, s.prob, s.color, s.won, s.lost
FROM p, (VALUES
  ('Prospecção',   0,  10, '#94A3B8', false, false),
  ('Qualificação', 1,  25, '#60A5FA', false, false),
  ('Proposta',     2,  50, '#FBBF24', false, false),
  ('Negociação',   3,  75, '#FB923C', false, false),
  ('Ganho',        4, 100, '#22C55E', true,  false),
  ('Perdido',      5,   0, '#EF4444', false, true)
) AS s(name, pos, prob, color, won, lost);

COMMIT;
