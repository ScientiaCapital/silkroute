# SilkRoute — AI Agent Orchestrator for Chinese LLMs

## Overview

SilkRoute is a specialized AI agent orchestrator for Chinese LLMs (DeepSeek, Qwen, GLM, Kimi).
Built on [pi.dev](https://pi.dev) as a pi extension package.

## Architecture

- **@silkroute/pi-china-router** — 3-tier model routing (Free/Standard/Premium) with keyword-based task classification
- **@silkroute/pi-budget-guard** — Per-project budget governance with PostgreSQL persistence
- **dashboard/** — Next.js 15 monitoring dashboard (Overview, Models, Budget, Sessions)

## Model Tiers

| Tier | Use Case | Cost Range | Default Model |
|------|----------|-----------|---------------|
| FREE | Summarize, format, triage, local tasks | $0 | Qwen3 Coder (Free) |
| STANDARD | Code review, implement, fix, refactor | $0.06–$1.00/M | DeepSeek V3.2 |
| PREMIUM | Architecture, security audit, migration | $0.22–$3.20/M | DeepSeek R1 |

## Commands

- `/tier [free|standard|premium|auto]` — Set or show routing tier
- `/models` — Show all 13 Chinese LLM models with pricing
- `/budget` — Show remaining budget and spend breakdown

## Key Conventions

- **No OpenAI** — Chinese LLMs only (DeepSeek, Qwen, GLM, Kimi)
- **Budget-first** — Every session has a cost cap. Check `/budget` before expensive operations.
- **Tier routing is automatic** — Tasks are classified by keywords. Override with `/tier`.

## Providers

Models are accessed via OpenRouter (primary), Kimi For Coding (direct), and Ollama (local).
Set `SILKROUTE_OPENROUTER_API_KEY` for the quickest setup.
