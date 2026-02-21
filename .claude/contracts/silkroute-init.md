# Feature Contract: silkroute-init

**Created:** 2026-02-21
**Scope:** FULL (>10 files, new project, new architecture)
**Observer Required:** observer-full (Sonnet)

---

## Summary

Initialize the `silkroute` project — an open-source AI agent orchestrator built exclusively for Chinese LLMs. Hybrid Python core + Next.js dashboard architecture.

## IN SCOPE

### Python Core (`src/silkroute/`)
- `__init__.py` — version = "0.1.0"
- `cli.py` — Click CLI with commands: init, run, budget, status, models, daemon
- `config/settings.py` — Pydantic settings with 5 sub-configs (Provider, Budget, Agent, Daemon, Database)
- `providers/models.py` — 13-model registry across 3 tiers (Free/Standard/Premium) + 2 local

### Next.js Dashboard (`dashboard/`)
- App Router with TypeScript + Tailwind CSS
- 3 pages: Overview (`/`), Models (`/models`), Budget (`/budget`)
- Root layout with sidebar navigation
- TypeScript port of model registry data (`lib/models.ts`)
- Shared types (`lib/types.ts`)

### Infrastructure (root)
- `pyproject.toml` — hatchling build, dependencies, dev extras
- `docker-compose.yml` — LiteLLM + Postgres + Redis stack
- `litellm_config.yaml` — Chinese model routing config
- `sql/init.sql` — 7 tables + 2 views for cost tracking
- `.env.example` — template with all env var placeholders (NO real keys)
- `.gitignore` — Python + Node + observer ephemeral
- `CLAUDE.md` — project instructions + observer protocol

### Observer Infrastructure (`.claude/`)
- `agents/observer-lite.md` — Haiku, 4 quick checks
- `agents/observer-full.md` — Sonnet, 7 drift patterns + devil's advocate
- `settings.local.json` — PreToolUse + PostToolUse hooks
- `PROJECT_CONTEXT.md` — initial context
- Empty ephemeral files: OBSERVER_QUALITY.md, OBSERVER_ARCH.md, OBSERVER_ALERTS.md

### Tests (`tests/`)
- `test_settings.py` — verify ModelTier enum, BudgetConfig defaults, hardware profiles
- `test_models.py` — verify model count, tier distribution, cost estimation, registry lookup

## OUT OF SCOPE

- Agent loop implementation (Phase 02)
- LiteLLM proxy health checks (Phase 01-02)
- Budget tracking API routes (Phase 04)
- Daemon mode implementation (Phase 07)
- Vercel deployment of dashboard
- Docker stack running locally
- Real API keys or secrets
- CI/CD pipeline (GitHub Actions)
- CONTRIBUTING.md, LICENSE file

## File Ownership (Builder Assignment)

| Builder | Files | Cannot Touch |
|---------|-------|-------------|
| Python Builder | `src/silkroute/**`, `tests/**`, `pyproject.toml`, `sql/`, `docker-compose.yml`, `litellm_config.yaml` | `dashboard/**` |
| Dashboard Builder | `dashboard/**` | `src/silkroute/**`, `tests/**` |
| Infra Builder | `.gitignore`, `.env.example`, `CLAUDE.md`, `README.md`, `.claude/**` | `src/silkroute/**`, `dashboard/src/**` |

## Interfaces / Contracts

### Python CLI Interface
```
silkroute --version          → "0.1.0"
silkroute models             → Rich table with 13 models
silkroute models --tier free → Filtered by tier
silkroute init [path]        → Creates workspace dirs + config
silkroute run "task"         → Stub (Phase 02)
silkroute budget             → Cost estimator table
silkroute status             → Version + health stubs
silkroute daemon             → Stub (Phase 07)
```

### Model Registry Data Shape (shared between Python + TS)
```typescript
interface ModelSpec {
  modelId: string;       // e.g. "deepseek/deepseek-v3.2"
  name: string;          // e.g. "DeepSeek V3.2"
  provider: Provider;    // "deepseek" | "qwen" | "z-ai" | "moonshotai" | "ollama"
  tier: ModelTier;       // "free" | "standard" | "premium"
  inputCostPerM: number;
  outputCostPerM: number;
  contextWindow: number;
  maxOutputTokens: number;
  capabilities: Capability[];
  supportsTooCallling: boolean;
  isMoe: boolean;
  isFree: boolean;
}
```

### Dashboard Pages
| Route | Purpose | Data Source |
|-------|---------|------------|
| `/` | Overview: project count, today's spend, model health | Static mock data |
| `/models` | Interactive model registry browser | `lib/models.ts` (TS port) |
| `/budget` | Budget tracker with per-project spend | Static mock data |

## Success Criteria

- [ ] `silkroute --version` outputs `0.1.0`
- [ ] `silkroute models` displays 13 models in Rich table
- [ ] `npm run dev` in `dashboard/` loads on localhost:3000
- [ ] All 3 dashboard pages render without errors
- [ ] `pytest tests/` passes with 0 failures
- [ ] `grep -r "sk-" . --include="*.py" --include="*.ts"` returns 0 matches
- [ ] `.env.example` contains only placeholder values
- [ ] Observer reports show 0 BLOCKERs
- [ ] GitHub repo `ScientiaCapital/silkroute` exists and is public

## Observer Checkpoints

- [ ] Architecture Observer approves this contract before Phase 2
- [ ] Code Quality Observer runs after each builder completes
- [ ] Security gate passes before Phase 4 (ship)
- [ ] No files modified outside declared file ownership boundaries

## URLs (ScientiaCapital org)

All URLs must reference `ScientiaCapital/silkroute`, NOT `tkipper/silkroute`.
