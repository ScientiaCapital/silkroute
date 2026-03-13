# silkroute — Coding Rules

## Project Structure
- Python core: `src/silkroute/` — CLI, config, model registry
- Dashboard: `dashboard/` — Next.js 15 App Router

## Hard Constraints
- **No OpenAI** — Chinese LLMs only via OpenRouter (DeepSeek, Qwen, GLM, Kimi)
- **No blanket-ignore `.claude/`** in .gitignore — only ephemeral observer files

## Model Routing
- 3-tier: Free → Standard → Premium based on task complexity
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
