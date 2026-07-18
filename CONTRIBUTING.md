# Contributing to SilkRoute

Thanks for your interest in SilkRoute — a model-agnostic AI agent orchestrator,
optimized for Chinese LLMs (DeepSeek, Qwen, GLM, Kimi), with cost-aware 3-tier
routing and an MCP bridge.

PRs are welcome, especially for:
- New MCP tool servers
- Chinese model benchmark data
- Ollama model configurations
- Documentation translations (Chinese, Spanish)

## Ground rules

- **Chinese/local-first by default.** The registry ships Chinese + local (Ollama) models and the
  routing is tuned for them (sovereign, low-cost, $0 local). The architecture is model-agnostic:
  western frontier models (Claude/GPT/Gemini) ship **opt-in** via a one-line `ModelSpec` through
  OpenRouter — don't add a "reject non-Chinese" guard. Use direct vendor APIs when keys are
  configured, OpenRouter as the fallback gateway.
- **Tests first.** New features and bug fixes ship with tests. The suite is large
  and green — keep it that way.
- **Small, focused PRs.** One concern per PR; describe the "why", not just the "what".

## Local setup

```bash
# Python core
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
silkroute --version          # → 0.1.0
silkroute models             # list the model registry

# Dashboard (optional)
cd dashboard && npm install && npm run dev   # localhost:3000
```

Copy `.env.example` → `.env` and set at least one provider
(`SILKROUTE_OPENROUTER_API_KEY`, a direct vendor key, or `SILKROUTE_OLLAMA_ENABLED=true`
for a zero-cost local setup).

## Before you push

```bash
pytest                # run the test suite
pytest --cov=src      # with coverage
ruff check src/       # lint
cd dashboard && npm run lint
```

## Security

- The REST API is **auth-on-by-default in production**: set `SILKROUTE_ENVIRONMENT=production`
  and a strong `SILKROUTE_API_KEY`, or `create_app()` refuses to start. Empty-key
  dev mode is for local development only.
- For public / try-it deployments, set `SILKROUTE_API_DEMO_MODE=true` to disable the
  money-spending endpoints (`/runtime/invoke`, `/runtime/stream`, `POST /tasks`).
- Never commit secrets. `.env` and `*.env.local` are gitignored; only `.env.example` is tracked.

## Commit style

Conventional-commit prefixes scoped by area, e.g.
`feat(api):`, `feat(mcp):`, `feat(dashboard):`, `fix:`, `chore:`, `docs:`.

## Project layout

See [CLAUDE.md](CLAUDE.md) for the architecture map and `.claude/rules/coding.md`
for the coding rules. In short:
- `src/silkroute/` — Python agent core (Click CLI, Pydantic settings, providers, MCP bridge)
- `dashboard/` — Next.js 15 dashboard
- `tests/` — pytest suite
- `docs/plans/` — design + implementation plans

## License

By contributing you agree your contributions are licensed under the project's MIT license.
