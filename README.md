# SilkRoute

**The fastest route from task to done — powered by China's best AI.**

SilkRoute is the first open-source AI agent orchestrator built exclusively for Chinese LLMs. It routes tasks intelligently across DeepSeek, Qwen, GLM, and Kimi models with per-project budget governance, 3-tier cost optimization, and automatic provider failover.

**70% of tasks hit free-tier models. The rest cost 1/20th of GPT-4.**

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
- **Hybrid Local + API** — Ollama support for Mac Studio (192GB) and NVIDIA Spark. Route to local models when available, API when not. Zero-cost inference for 80%+ of tasks.
- **MCP Client Bridge** — `src/silkroute/mcp_bridge` connects the agent to any MCP-compatible server over stdio and registers its tools alongside the built-ins. Demonstrated end-to-end against [epiphan-mcp-server](https://github.com/ScientiaCapital/epiphan-mcp-server) — see "Try the AV demo" below.
- **24/7 Daemon Mode** — GitHub webhook listener, cron scheduler, heartbeat monitoring. Manages 70+ repos autonomously while you sleep.

## Quick Start

```bash
# Install
pip install silkroute

# Initialize workspace
silkroute init

# Add your OpenRouter API key
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

A self-hosted, open-weight LLM (Qwen2.5, served locally via Ollama) answers a
plain-English AV question by calling [epiphan-mcp-server](https://github.com/ScientiaCapital/epiphan-mcp-server)'s
tools directly over MCP — no cloud dependency anywhere in the loop.

```bash
ollama pull qwen2.5:14b   # once

python demo/agent_ready_av_demo.py --mock-pearl
# or, against a real fleet:
python demo/agent_ready_av_demo.py --pearl-devices 192.168.1.100 \
    --pearl-username admin --pearl-password ...
```

`--mock-pearl` starts a tiny stub Pearl API server (`demo/pearl_mock_server.py`)
instead of hitting real hardware — useful for a fast, deterministic demo run.
epiphan-mcp-server's source is never modified either way.

What this proves: an open-weight model, fully self-hosted (no cloud inference
calls), talking MCP-standard tool calling (the same protocol Claude Desktop and
Cursor use) — model, orchestrator, and device server are all independently
swappable.

## Hardware Deployment Tiers

| Tier | Hardware | Local Models | Monthly Cost |
|------|----------|-------------|-------------|
| Starter | Mac Mini M4 (16GB) | API only | ~$55-155 |
| Pro | Mac Studio Ultra (192GB) | Qwen3-30B, GLM-4-9B, DeepSeek V3 Q4 | ~$25-45 |
| Max | Studio + NVIDIA Spark | All tiers local | ~$20-30 |
| Cloud | Hetzner VPS (4GB) | API only | ~$54-204 |

## Architecture

```
silkroute run "task" → Agent Core → Task Classifier → LiteLLM Proxy → Chinese LLMs
                         ↓              ↓                  ↓
                    Tools (built-in  Budget Guard      DeepSeek / Qwen / GLM / Kimi
                    + MCP bridge)   (per-project       (via OpenRouter, direct API,
                                     hard caps,          or local Ollama)
                                     alerts)
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
