# CLAUDE.md — silkroute

**SilkRoute** — a model-agnostic AI agent orchestrator, optimized for Chinese LLMs.
Hybrid Python core + Next.js dashboard architecture. Also the AI-first orchestration
backbone for the agentic AV control plane (see `openav-mcp` in the sibling
`epiphan-openav-bridge` repo — SilkRoute drives OpenAV + Epiphan devices over MCP).

## Architecture

```
silkroute/
├── src/silkroute/          # Python agent core (Click CLI, Pydantic settings)
│   ├── cli.py              # CLI entry point (incl. `silkroute mcp serve`)
│   ├── config/settings.py  # Pydantic configuration system
│   ├── mcp_bridge/         # MCP client (connect to N servers) + server (expose tools)
│   ├── agent/router.py     # Model routing incl. fit-to-hardware (min_ram_gb)
│   └── providers/models.py # 17-model registry (3 tiers; model-agnostic architecture)
├── dashboard/              # Next.js 15 App Router + Tailwind
│   └── src/app/            # 6 pages: Overview, Projects, Models, Budget, Task History, AV/Edge Demo
├── demo/                   # AV demo agents; mock Pearl + vendored mock epiphan MCP (--mock-mcp)
├── docs/                   # Guides + design/implementation plans (docs/plans/)
├── scripts/                # Deployment entrypoints (start.sh)
├── sql/init.sql            # PostgreSQL schema (12 tables, 2 views) — fresh-install bootstrap
│   └── migrations/         # Numbered catch-up migrations for existing DBs (`silkroute db migrate`)
├── docker-compose.yml      # LiteLLM + Postgres + Redis
├── litellm_config.yaml     # Chinese model routing config
├── pyproject.toml          # Python build config (hatchling)
└── tests/                  # pytest test suite
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Python | 3.12+ |
| Python CLI | Click + Rich |
| Configuration | Pydantic Settings |
| Model Registry | Dataclasses + Enums |
| Dashboard | Next.js 15, React 19, Tailwind CSS v4 |
| Database | PostgreSQL 16 |
| Cache | Redis 7 |
| LLM Proxy | LiteLLM |
| Providers | DeepSeek, Qwen, GLM, Kimi — direct vendor APIs when keys are configured, OpenRouter as fallback |

## Dev Commands

```bash
# Python
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
silkroute --version         # Should print 0.1.0
silkroute models            # Show the 17-model registry
silkroute mcp serve         # Expose SilkRoute's tools as an MCP server (read-only default)
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

- **Model-agnostic, Chinese-LLM-optimized** — the registry ships Chinese + local (Ollama) models and
  the routing is tuned for them (sovereign, low-cost, $0 local). The *architecture* is model-agnostic:
  the router treats models opaquely, so any OpenAI-compatible / litellm provider — including western
  frontier models (Claude/GPT/Gemini) via OpenRouter — plugs in with a one-line `ModelSpec`. Default
  posture stays local-first for sovereignty; frontier is opt-in per deployment.
- **3-tier routing** — Free → Standard → Premium based on task complexity; fit-to-hardware selection
  (`min_ram_gb` + `hardware_profile`, incl. a `raspberry-pi` edge profile that delegates inference)
- **Budget governance** — Per-project hard caps, daily pacing
- **Security** — auth-on-by-default in production (`SILKROUTE_ENVIRONMENT=production` + `SILKROUTE_API_KEY`);
  `SILKROUTE_API_DEMO_MODE=true` disables money-spending endpoints for public try-it deployments
- **MCP** — SilkRoute is both an MCP client (bridge to N servers) and an MCP server (`silkroute mcp serve`)
- **GitHub org** — ScientiaCapital/silkroute
