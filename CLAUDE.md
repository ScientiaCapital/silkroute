# CLAUDE.md — silkroute

**SilkRoute** — AI agent orchestrator for Chinese LLMs.
Hybrid Python core + Next.js dashboard architecture.

## Architecture

```
silkroute/
├── src/silkroute/          # Python agent core (Click CLI, Pydantic settings)
│   ├── cli.py              # CLI entry point
│   ├── config/settings.py  # Pydantic configuration system
│   └── providers/models.py # 13-model registry (3 tiers)
├── dashboard/              # Next.js 15 App Router + Tailwind
│   └── src/app/            # 3 pages: Overview, Models, Budget
├── sql/init.sql            # PostgreSQL schema (7 tables, 2 views)
├── docker-compose.yml      # LiteLLM + Postgres + Redis
├── litellm_config.yaml     # Chinese model routing config
├── pyproject.toml          # Python build config (hatchling)
└── tests/                  # pytest test suite
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Python CLI | Click + Rich |
| Configuration | Pydantic Settings |
| Model Registry | Dataclasses + Enums |
| Dashboard | Next.js 15, React 19, Tailwind CSS v4 |
| Database | PostgreSQL 16 |
| Cache | Redis 7 |
| LLM Proxy | LiteLLM |
| Providers | DeepSeek, Qwen, GLM, Kimi (via OpenRouter) |

## Dev Commands

```bash
# Python
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
silkroute --version         # Should print 0.1.0
silkroute models            # Show 13 Chinese models
pytest                      # Run Python tests
pytest --cov=src            # With coverage
ruff check src/             # Lint

# Dashboard
cd dashboard
npm install
npm run dev                 # localhost:3000
npm run lint                # ESLint

# Docker (full stack)
docker compose up -d        # Start Postgres + Redis + LiteLLM
docker compose down         # Stop all
```

## Key Conventions

- **No OpenAI** — Chinese LLMs only (DeepSeek, Qwen, GLM, Kimi)
- **3-tier routing** — Free → Standard → Premium based on task complexity
- **Budget governance** — Per-project hard caps, daily pacing
- **GitHub org** — ScientiaCapital/silkroute
