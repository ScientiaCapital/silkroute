# SilkRoute

**The fastest route from task to done — powered by China's best AI.**

SilkRoute is an open-source AI agent orchestrator **optimized for Chinese LLMs** with a
**model-agnostic architecture**. It routes tasks intelligently across DeepSeek, Qwen, GLM, Kimi, and
local (Ollama) models with per-project budget governance, 3-tier cost optimization, fit-to-hardware
routing, and automatic provider failover — and any OpenAI-compatible provider (including western
frontier models via OpenRouter) plugs in with a one-line registry entry.

**70% of tasks hit free-tier models. The rest cost 1/20th of GPT-4.**

It's also the **AI-first orchestration backbone for an agentic AV control plane** — driving
[Dartmouth OpenAV](https://github.com/open-avc/openavc) + Epiphan Pearl/EC20 over MCP so rooms can be
run in plain English and heal themselves. See [Agentic AV control plane](#agentic-av-control-plane).

---

## Why SilkRoute?

Every AI agent framework defaults to OpenAI or Anthropic. That's a $200+/month habit for autonomous agent workloads. Meanwhile, Chinese LLMs have quietly reached parity:

| Model | Benchmark | Cost (Input/Output per M tokens) |
|-------|-----------|--------------------------------|
| DeepSeek V3.2 | Matches GPT-4.5 on coding, reasoning | $0.25 / $0.38 |
| Qwen3-Coder 480B | 70.6% SWE-Bench Verified | $0.22 / $0.95 |
| GLM-5 (MIT) | 77.8% SWE-Bench Verified | $1.00 / $3.20 |
| Kimi K2 (1T params) | Multi-step agent orchestration | $0.39 / $1.90 |
| **Free tier models** | **Rate-limited but capable** | **$0.00 / $0.00** |

SilkRoute doesn't just support Chinese models — it's *optimized* for them. System prompts tuned for their tool-calling formats. Routing that maximizes free-tier utilization. Budget enforcement that makes runaway costs structurally impossible.

## Features

- **3-Tier Intelligent Routing** — Simple tasks → free models. Standard tasks → DeepSeek V3.2 ($0.25/M). Complex tasks → DeepSeek R1 or GLM-5. Automatic classification, no configuration needed.
- **Per-Project Budget Governance** — Hard monthly caps per project. Daily pacing prevents overnight cost spikes. Alerts at 50%, 80%, 100%. Circuit breaker kills the agent at budget limit.
- **Chinese-Model-First** — DeepSeek, Qwen, GLM, Kimi as primary providers. OpenRouter as unified gateway. Direct API support for lower latency.
- **Hybrid Local + API + Fit-to-Hardware** — Ollama support for Mac Studio (192GB), NVIDIA Spark, and edge boxes. `hardware_profile` + each model's `min_ram_gb` pick the biggest local model that fits; a `raspberry-pi` edge profile runs the orchestrator on-prem and delegates inference. Zero-cost local inference for 80%+ of tasks.
- **MCP client *and* server** — `src/silkroute/mcp_bridge` connects the agent to **N** MCP servers over stdio (register their tools alongside the built-ins), and `silkroute mcp serve` exposes SilkRoute's own tools *as* an MCP server (read-only export by default). Demonstrated end-to-end against [epiphan-mcp-server](https://github.com/ScientiaCapital/epiphan-mcp-server) and the OpenAV bridge — see below.
- **Production-safe by default** — auth is required in production (`SILKROUTE_ENVIRONMENT=production` refuses to start without `SILKROUTE_API_KEY`); `SILKROUTE_API_DEMO_MODE=true` disables money-spending endpoints for public try-it deployments.
- **24/7 Daemon Mode** — GitHub webhook listener, cron scheduler, heartbeat monitoring. Manages 70+ repos autonomously while you sleep.

## Quick Start

```bash
# Install from source (not yet on PyPI)
git clone https://github.com/ScientiaCapital/silkroute.git && cd silkroute
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Initialize workspace
silkroute init

# Add a provider key (one OpenRouter key covers DeepSeek/GLM/Qwen/Kimi),
# or set SILKROUTE_OLLAMA_ENABLED=true for a fully local, $0 setup
echo "SILKROUTE_OPENROUTER_API_KEY=sk-or-..." >> .env

# See available models and pricing
silkroute models

# Run the agent
silkroute run "Review the open PRs in my-repo and suggest improvements"

# Check costs
silkroute budget
```

### Docker (Full Stack)

```bash
git clone https://github.com/ScientiaCapital/silkroute.git
cd silkroute
cp .env.example .env  # Add your API keys
docker compose up -d

# Agent connects to LiteLLM proxy with budget enforcement
silkroute run --project my-repo "Triage all open issues and label by priority"
```

## Try the AV demo

A self-hosted, open-weight LLM (Qwen2.5, via Ollama) answers a plain-English AV question by calling
device tools over MCP — no cloud dependency anywhere in the loop.

```bash
ollama pull qwen2.5:14b   # once

# Fully self-contained — no external repo, no hardware, no creds (recommended first run):
python demo/agent_ready_av_demo.py --mock-mcp

# Or against the real epiphan-mcp-server with a canned Pearl API:
python demo/agent_ready_av_demo.py --mock-pearl

# Or against a real fleet:
python demo/agent_ready_av_demo.py --pearl-devices 192.168.1.100 \
    --pearl-username admin --pearl-password ...
```

`--mock-mcp` uses the vendored `demo/mock_epiphan_mcp.py` (a tiny MCP server serving canned
Pearl-2-Room320B data) so the whole loop runs with only silkroute + Ollama. No source is modified.

What this proves: an open-weight model, fully self-hosted (no cloud inference), talking MCP-standard
tool calling (same protocol Claude Desktop and Cursor use) — model, orchestrator, and device server
all independently swappable. The dashboard visualizes it at **`/demo`** (static, Vercel-safe).

Full walkthrough (which Ollama models, telemetry to the model-finops cost dashboard):
[`docs/av-demo-guide.md`](docs/av-demo-guide.md).

## Agentic AV control plane

SilkRoute is the AI-first orchestration layer above [OpenAV](https://github.com/open-avc/openavc)
(Dartmouth's open AV control system, deployed on 150+ rooms). The
[`epiphan-openav-bridge`](https://github.com/ScientiaCapital/epiphan-openav-bridge) repo ships
`openav-mcp` — an MCP server fronting the OpenAV orchestrator + Epiphan Pearl/EC20 — which SilkRoute
registers as an upstream MCP server and drives in plain English ("get room 320-B recording with the
camera tracking the presenter"). **OpenAV = the brains; Epiphan = the reliable hardware; SilkRoute =
the agent backbone above them** (they stay separate — "Epiphan hardware running OpenAV," never
"Epiphan OpenAV"). Model-agnostic, on-prem, self-healing. See that repo's `HANDOFF.md` to run the
whole stack end-to-end.

## Hardware Deployment Tiers

| Tier | Hardware | Local Models | Monthly Cost |
|------|----------|-------------|-------------|
| Edge | Raspberry Pi 5 (on-prem) | None — runs orchestrator/MCP, delegates inference | ~$50-150 (cloud inference) |
| Starter | Mac Mini M4 (16GB) | Qwen2.5 14B / DeepSeek R1 14B | ~$55-155 |
| Pro | Mac Studio Ultra (192GB) | Qwen3-30B, GLM-4-9B, Qwen2.5 32B, DeepSeek V3 Q4 | ~$25-45 |
| Max | Studio + NVIDIA Spark | All tiers local | ~$20-30 |
| Cloud | Hetzner VPS (4GB) | None — delegates inference | ~$54-204 |

The `raspberry-pi` profile is the AV/edge story: the orchestrator + MCP + dashboard run on the same
$80 Pi already deployed as an AV switcher; heavy inference goes to cloud or a beefier local node
(fit-to-hardware routing picks automatically).

## Architecture

```
silkroute run "task" → Agent Core → Router → LiteLLM → any model
                         ↓            ↓ (tier + fit-to-hardware)   ↓
                    Tools:         Budget Guard            Chinese/local (DeepSeek/Qwen/
                    built-ins      (per-project            GLM/Kimi/Ollama) by default;
                    + MCP client   hard caps, alerts)      frontier (Claude/GPT/Gemini)
                    (N servers);                           pluggable via OpenRouter
                    `mcp serve`
                    exposes tools
```

## Cost Comparison

Estimated monthly cost for managing 70 GitHub repositories with daily automated maintenance:

| Solution | LLM Cost | Infrastructure | Total |
|----------|----------|---------------|-------|
| OpenHands + GPT-4o | $300-500 | $50 (VPS) | $350-550 |
| Aider + Claude Sonnet | $200-400 | $0 (local) | $200-400 |
| SilkRoute + Chinese LLMs | $50-150 | $5-35 | **$55-185** |
| SilkRoute + Mac Studio (local) | $10-30 | $0 (owned) | **$10-30** |

## License

MIT — use it for anything.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines. PRs welcome, especially for:
- New MCP tool servers
- Chinese model benchmark data
- Ollama model configurations
- Documentation translations (Chinese, Spanish)

---

*Built by [ScientiaCapital](https://github.com/ScientiaCapital) — connecting China's best AI to the world's hardest problems.*
