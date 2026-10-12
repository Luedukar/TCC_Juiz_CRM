-- Execute depois de schema.sql. Refresh tokens são rotacionados e persistidos
-- somente como hash; revogação por usuário permite logout e invalidação de sessões.
CREATE TABLE refresh_sessions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    token_hash CHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, user_id) REFERENCES users(workspace_id, id) ON DELETE CASCADE
);
CREATE INDEX idx_refresh_sessions_user ON refresh_sessions(workspace_id, user_id) WHERE revoked_at IS NULL;
