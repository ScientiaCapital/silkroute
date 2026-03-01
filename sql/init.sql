-- SilkRoute Database Schema
-- Cost tracking, project budgets, session state, audit trail
-- PostgreSQL 16+

-- ============================================================
-- Projects — each repo or workstream gets budget governance
-- ============================================================
CREATE TABLE IF NOT EXISTS projects (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    github_repo     TEXT DEFAULT '',
    budget_monthly_usd  NUMERIC(10, 4) NOT NULL DEFAULT 2.85,
    budget_daily_usd    NUMERIC(10, 4) NOT NULL DEFAULT 0.10,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- Cost Logs — every LLM call tracked with full attribution
-- ============================================================
CREATE TABLE IF NOT EXISTS cost_logs (
    id              BIGSERIAL PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projects(id),
    model_id        TEXT NOT NULL,
    model_tier      TEXT NOT NULL CHECK (model_tier IN ('free', 'standard', 'premium')),
    provider        TEXT NOT NULL,

    -- Token usage
    input_tokens    INTEGER NOT NULL DEFAULT 0,
    output_tokens   INTEGER NOT NULL DEFAULT 0,
    total_tokens    INTEGER NOT NULL DEFAULT 0,

    -- Cost
    cost_usd        NUMERIC(10, 6) NOT NULL DEFAULT 0.0,

    -- Context
    task_type       TEXT DEFAULT 'unknown',
    session_id      TEXT,
    request_id      TEXT,

    -- Timing
    latency_ms      INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cost_logs_project ON cost_logs(project_id);
CREATE INDEX IF NOT EXISTS idx_cost_logs_created ON cost_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_cost_logs_model ON cost_logs(model_id);
CREATE INDEX IF NOT EXISTS idx_cost_logs_tier ON cost_logs(model_tier);

-- ============================================================
-- Budget Snapshots — daily rollups for fast budget checking
-- ============================================================
CREATE TABLE IF NOT EXISTS budget_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projects(id),
    snapshot_date   DATE NOT NULL,
    total_cost_usd  NUMERIC(10, 6) NOT NULL DEFAULT 0.0,
    total_requests  INTEGER NOT NULL DEFAULT 0,
    total_tokens    BIGINT NOT NULL DEFAULT 0,

    -- Per-tier breakdown
    free_requests   INTEGER NOT NULL DEFAULT 0,
    free_cost_usd   NUMERIC(10, 6) NOT NULL DEFAULT 0.0,
    standard_requests INTEGER NOT NULL DEFAULT 0,
    standard_cost_usd NUMERIC(10, 6) NOT NULL DEFAULT 0.0,
    premium_requests INTEGER NOT NULL DEFAULT 0,
    premium_cost_usd NUMERIC(10, 6) NOT NULL DEFAULT 0.0,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(project_id, snapshot_date)
);

-- ============================================================
-- Agent Sessions — conversation state and history
-- ============================================================
CREATE TABLE IF NOT EXISTS agent_sessions (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projects(id),
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'completed', 'failed', 'timeout')),
    task            TEXT NOT NULL,
    model_id        TEXT NOT NULL,

    -- State
    iteration_count INTEGER NOT NULL DEFAULT 0,
    total_cost_usd  NUMERIC(10, 6) NOT NULL DEFAULT 0.0,
    messages_json   JSONB DEFAULT '[]'::jsonb,

    -- Timing
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- Tool Audit Log — every tool invocation recorded
-- ============================================================
CREATE TABLE IF NOT EXISTS tool_audit_log (
    id              BIGSERIAL PRIMARY KEY,
    session_id      TEXT REFERENCES agent_sessions(id),
    tool_name       TEXT NOT NULL,
    tool_input      JSONB DEFAULT '{}'::jsonb,
    tool_output     TEXT DEFAULT '',
    success         BOOLEAN NOT NULL DEFAULT true,
    error_message   TEXT DEFAULT '',
    duration_ms     INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- Provider Health — track uptime and latency per provider
-- ============================================================
CREATE TABLE IF NOT EXISTS provider_health (
    id              BIGSERIAL PRIMARY KEY,
    provider        TEXT NOT NULL,
    model_id        TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('healthy', 'degraded', 'down')),
    latency_p50_ms  INTEGER DEFAULT 0,
    latency_p99_ms  INTEGER DEFAULT 0,
    error_rate      NUMERIC(5, 4) DEFAULT 0.0,
    checked_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- Scheduled Tasks — cron jobs for daemon mode
-- ============================================================
CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id              TEXT PRIMARY KEY,
    project_id      TEXT REFERENCES projects(id),
    task_type       TEXT NOT NULL,
    cron_expression TEXT NOT NULL,
    task_config     JSONB DEFAULT '{}'::jsonb,
    enabled         BOOLEAN NOT NULL DEFAULT true,
    last_run_at     TIMESTAMPTZ,
    next_run_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- Insert default project
-- ============================================================
INSERT INTO projects (id, name, description, budget_monthly_usd)
VALUES ('default', 'Default Project', 'Default SilkRoute project', 200.00)
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- Useful views
-- ============================================================
CREATE OR REPLACE VIEW v_monthly_spend AS
SELECT
    project_id,
    DATE_TRUNC('month', created_at) AS month,
    model_tier,
    COUNT(*) AS requests,
    SUM(cost_usd) AS total_cost,
    SUM(input_tokens) AS total_input_tokens,
    SUM(output_tokens) AS total_output_tokens,
    AVG(latency_ms) AS avg_latency_ms
FROM cost_logs
GROUP BY project_id, DATE_TRUNC('month', created_at), model_tier
ORDER BY month DESC, project_id, model_tier;

CREATE OR REPLACE VIEW v_budget_remaining AS
SELECT
    p.id AS project_id,
    p.name AS project_name,
    p.budget_monthly_usd,
    COALESCE(SUM(cl.cost_usd), 0) AS spent_this_month,
    p.budget_monthly_usd - COALESCE(SUM(cl.cost_usd), 0) AS remaining,
    CASE
        WHEN COALESCE(SUM(cl.cost_usd), 0) >= p.budget_monthly_usd THEN 'EXCEEDED'
        WHEN COALESCE(SUM(cl.cost_usd), 0) >= p.budget_monthly_usd * 0.80 THEN 'CRITICAL'
        WHEN COALESCE(SUM(cl.cost_usd), 0) >= p.budget_monthly_usd * 0.50 THEN 'WARNING'
        ELSE 'OK'
    END AS status
FROM projects p
LEFT JOIN cost_logs cl
    ON cl.project_id = p.id
    AND cl.created_at >= DATE_TRUNC('month', NOW())
GROUP BY p.id, p.name, p.budget_monthly_usd;

-- ============================================================
-- Supervisor Sessions — long-running compound workflows
-- ============================================================
CREATE TABLE IF NOT EXISTS supervisor_sessions (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projects(id),
    status          TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'paused', 'completed', 'failed', 'cancelled')),
    plan_json       JSONB NOT NULL DEFAULT '{}'::jsonb,
    checkpoint_json JSONB DEFAULT NULL,
    context_json    JSONB NOT NULL DEFAULT '{}'::jsonb,
    total_cost_usd  NUMERIC(10, 6) NOT NULL DEFAULT 0.0,
    config_json     JSONB NOT NULL DEFAULT '{}'::jsonb,
    error           TEXT DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_supervisor_sessions_project ON supervisor_sessions(project_id);
CREATE INDEX IF NOT EXISTS idx_supervisor_sessions_status ON supervisor_sessions(status);

-- ============================================================
-- Skill Executions — analytics for skill usage
-- ============================================================
CREATE TABLE IF NOT EXISTS skill_executions (
    id              BIGSERIAL PRIMARY KEY,
    skill_name      TEXT NOT NULL,
    session_id      TEXT REFERENCES agent_sessions(id),
    project_id      TEXT NOT NULL REFERENCES projects(id),
    success         BOOLEAN NOT NULL DEFAULT true,
    cost_usd        NUMERIC(10, 6) NOT NULL DEFAULT 0.0,
    duration_ms     INTEGER DEFAULT 0,
    input_json      JSONB DEFAULT '{}'::jsonb,
    output_text     TEXT DEFAULT '',
    error_message   TEXT DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_skill_executions_skill ON skill_executions(skill_name);
CREATE INDEX IF NOT EXISTS idx_skill_executions_project ON skill_executions(project_id);
CREATE INDEX IF NOT EXISTS idx_skill_executions_created ON skill_executions(created_at);
