# silkroute — Coding Rules

## Project Structure
- Python core: `src/silkroute/` — CLI, config, model registry
- Dashboard: `dashboard/` — Next.js 15 App Router

## Hard Constraints
- **Model-agnostic, Chinese-LLM-optimized** — default to Chinese + local (Ollama) models
  (DeepSeek, Qwen, GLM, Kimi) for sovereignty and cost; direct vendor APIs when keys are configured,
  OpenRouter as fallback. The architecture is provider-neutral: western frontier models
  (Claude/GPT/Gemini) plug in via a one-line `ModelSpec` (OpenRouter) — no router changes. Don't add
  a "reject non-Chinese" guard; keep local-first as the default posture, not a hard block.
- **No blanket-ignore `.claude/`** in .gitignore — only ephemeral observer files

## Model Routing
- 3-tier: Free → Standard → Premium based on task complexity
- Fit-to-hardware: `select_model(hardware_profile=...)` prefers a local model that fits the box's
  `min_ram_gb`; `raspberry-pi`/VPS profiles (budget 0) delegate inference to the cloud
- Budget governance: per-project hard caps with daily pacing
- Model registry lives in `src/silkroute/providers/models.py`

## Python Standards
- Requires Python 3.12+ (`pyproject.toml` enforces `>=3.12`)
- CLI: Click + Rich (`src/silkroute/cli.py`)
- Config: Pydantic Settings (`src/silkroute/config/settings.py`)
- Tests: pytest — run with `pytest --cov=src`
- Lint: ruff — run with `ruff check src/`
- Install: `pip install -e ".[dev]"` inside `.venv`
- Build system: hatchling via `pyproject.toml`

## Dashboard Standards
- Framework: Next.js 15, React 19, Tailwind CSS v4
- Location: `dashboard/` subdirectory
- Dev: `cd dashboard && npm run dev` (localhost:3000)
- Lint: `npm run lint` (ESLint)

## Docker
- Full stack: `docker compose up -d` (Postgres 16 + Redis 7 + LiteLLM)
- Schema: `sql/init.sql`
- LiteLLM config: `litellm_config.yaml`
