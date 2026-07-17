-- Migration 0001: Agent Memories — persistent cross-session memory
--
-- Retroactive: this table already ships in init.sql for fresh installs.
-- This file lets an *existing* database catch up via `silkroute db migrate`.
-- All statements are idempotent (IF NOT EXISTS) so re-running is safe.

CREATE TABLE IF NOT EXISTS agent_memories (
    id                BIGSERIAL PRIMARY KEY,
    project_id        TEXT REFERENCES projects(id),  -- NULL = global scope
    kind              TEXT NOT NULL DEFAULT 'fact'
        CHECK (kind IN ('fact', 'preference', 'outcome')),
    content           TEXT NOT NULL,
    importance        REAL NOT NULL DEFAULT 0.5
        CHECK (importance >= 0.0 AND importance <= 1.0),
    source_session_id TEXT,          -- no FK: session row may not exist for fail-open writes
    token_estimate    INTEGER NOT NULL DEFAULT 0,
    recall_count      INTEGER NOT NULL DEFAULT 0,
    last_recalled_at  TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_memories_project ON agent_memories(project_id);
CREATE INDEX IF NOT EXISTS idx_agent_memories_recall
    ON agent_memories(project_id, importance DESC, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_memories_dedup
    ON agent_memories (COALESCE(project_id, ''), md5(content));
CREATE INDEX IF NOT EXISTS idx_agent_memories_fts
    ON agent_memories USING GIN (to_tsvector('english', content));
