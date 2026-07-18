# CLAUDE.md — silkroute

**SilkRoute** — a model-agnostic AI agent orchestrator, optimized for Chinese LLMs.
Hybrid Python core + Next.js dashboard architecture.

**Shipped today:** the 21-model registry + cost-aware routing, an MCP client/server bridge, budget
governance, and a self-contained AV/edge demo that drives a *mock* Epiphan Pearl over MCP — including
a self-healing detect→fix→verify loop against that mock.

**Where this is going (the north star):** the AI-first orchestration backbone for an agentic AV
control plane — driving the real [Dartmouth OpenAV](https://github.com/Dartmouth-OpenAV) + Epiphan
devices over MCP so live rooms can be run in plain English and heal themselves. The device-facing
bridge lives in the sibling `epiphan-openav-bridge` repo (`openav-mcp`); the live-room path is
in progress, not yet shipped here.

## Architecture

```
silkroute/
├── src/silkroute/          # Python agent core (Click CLI, Pydantic settings)
│   ├── cli.py              # CLI entry point (incl. `silkroute mcp serve`)
│   ├── config/settings.py  # Pydantic configuration system
│   ├── mcp_bridge/         # MCP client (connect to N servers) + server (expose tools)
│   ├── agent/router.py     # Model routing incl. fit-to-hardware (min_ram_gb)
│   ├── providers/models.py # 21-model registry (3 tiers; Chinese/local + opt-in western frontier)
│   ├── api/                # FastAPI REST API + auth (prod gate, demo mode)
│   ├── autoresearch/       # Autonomous experiment engine + self-healing room-health target/executor
│   ├── daemon/ db/ mantis/ # Daemon (webhook/cron/heartbeat), DB repos, agent runtime/skills
│   └── ...                 # network/ (SSRF), integrations/, config/
├── dashboard/              # Next.js 15 App Router + Tailwind
│   └── src/app/            # 6 pages: Overview, Projects, Models, Budget, Task History, AV/Edge Demo
├── demo/                   # AV demo agents; mock Pearl + vendored mock epiphan MCP (--mock-mcp);
│                           #   self_healing_demo.py (detect→fix→verify against the mock room)
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
| Providers | DeepSeek, Qwen, GLM, Kimi — direct vendor APIs when keys are configured, OpenRouter as fallback; western frontier (Claude/GPT/Gemini) opt-in via OpenRouter |

## Dev Commands

```bash
# Python
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
silkroute --version         # Should print 0.1.0
silkroute models            # Show the 21-model registry
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
  the router treats models opaquely. Western frontier models (Claude Sonnet 5, GPT-5.6, Gemini 3.5)
  already **ship in the registry** as one-line `ModelSpec`s that route via the OpenRouter fallback with
  no router changes — listed after Chinese/local in every tier. Default posture stays local-first for
  sovereignty; frontier is opt-in per deployment (needs `SILKROUTE_OPENROUTER_API_KEY`).
- **Self-healing loop (shipped, mock)** — `autoresearch/` evolves a remediation *playbook*; the
  executor (`autoresearch/heal.py`, `demo/self_healing_demo.py`, dashboard `/demo/heal`) does a real
  detect→fix→verify cycle against the mock room. Against **live** rooms it's the north-star vision.
- **3-tier routing** — Free → Standard → Premium based on task complexity; fit-to-hardware selection
  (`min_ram_gb` + `hardware_profile`, incl. a `raspberry-pi` edge profile that delegates inference)
- **Budget governance** — Per-project hard caps, daily pacing
- **Security** — auth-on-by-default in production (`SILKROUTE_ENVIRONMENT=production` + `SILKROUTE_API_KEY`);
  `SILKROUTE_API_DEMO_MODE=true` disables money-spending endpoints for public try-it deployments
- **MCP** — SilkRoute is both an MCP client (bridge to N servers) and an MCP server (`silkroute mcp serve`)
- **GitHub org** — ScientiaCapital/silkroute
