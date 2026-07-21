# Edge Deployment — SilkRoute on Raspberry Pi 5 / Ubuntu

How to run the SilkRoute agent as the **AI brain of a room controller** — driving a real
Epiphan Pearl + EC20 through the `epiphan-openav-bridge` stack, in plain English.

This doc covers the **SilkRoute layer only**. The device layer (Docker stack: OpenAV
orchestrator + Pearl/EC20 microservices, plus the `openav-mcp` server) is set up first —
follow `epiphan-openav-bridge/demo/DEPLOY-RPI5.md` (or the illustrated
"Setting Up Your Raspberry Pi Room Controller" guide) through its final step, then come back here.

```
"start recording and move the camera to preset 1"
        │
        ▼
SilkRoute agent (this repo) ── selects a model by hardware profile + task tier
        │  MCP (stdio)
        ▼
openav-mcp ── HTTP ──▶ orchestrator :8080 / pearl :8081 / ec20 :8082 (Docker)
        │
        ▼
Pearl Mini (REST v2.0)      EC20 (VISCA over tcp/5678)
```

## Pick your posture: where does inference run?

| Box | Profile | FREE/STANDARD work | PREMIUM work |
|---|---|---|---|
| **Raspberry Pi 5** (8GB) | `raspberry-pi` | cloud (delegated) | cloud |
| **Ubuntu ≥16GB** (NUC/mini-PC) | `mac-mini` | **local Ollama Qwen2.5 14B** — $0, offline, sovereign | cloud |
| **Ubuntu ≥64GB** | `mac-studio` | local Qwen2.5 32B | cloud |

The profile names encode a **local-RAM budget**, not a literal machine — an Ubuntu box with
16GB uses `mac-mini`. A Pi 5 can't usefully run a 7B+ model (memory-bound, ~4–6 tok/s), so
its profile has a 0GB budget and every tier delegates to the cloud. PREMIUM (self-healing,
ambiguous requests) always escalates to the cloud, even on a big box.

**Cloud brain by tier** (what delegated work routes to): standard multi-step control →
GLM-4.7 / DeepSeek V3.2 (the capability-scored defaults); hardest → Kimi K2 / Claude
Sonnet 5. Claude Haiku 4.5 is in the STANDARD tier as the latency-first western option —
like all western models it's opt-in (needs `SILKROUTE_OPENROUTER_API_KEY`) and sits after
the Chinese/local picks in the routing chain; select it explicitly with
`--model anthropic/claude-haiku-4-5` when speed matters most. Override any run with `--model`.

## Raspberry Pi 5 (cloud-delegated)

```bash
# after the bridge stack + openav-mcp are running (see the bridge guide)
git clone https://github.com/ScientiaCapital/silkroute && cd silkroute
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env
```

Edit `.env`:

```bash
SILKROUTE_OPENROUTER_API_KEY=sk-or-...        # required: inference is delegated
SILKROUTE_HARDWARE_PROFILE=raspberry-pi
SILKROUTE_OLLAMA_ENABLED=false

SILKROUTE_MCP_OPENAV_ENABLED=true
SILKROUTE_MCP_OPENAV_COMMAND=/home/<user>/epiphan-openav-bridge/openav-mcp/.venv/bin/python
# Example IPs — substitute YOUR devices' addresses and credentials (and change
# the EC20's factory-default admin/admin):
SILKROUTE_MCP_OPENAV_DEVICES=[{"alias":"room-pearl","host":"192.168.1.100","username":"admin","password":"<pearl-pw>","kind":"pearl"},{"alias":"room-cam","host":"192.168.1.101","username":"admin","password":"<ec20-pw>","kind":"ec20"}]
SILKROUTE_MCP_OPENAV_ORCHESTRATOR_URL=http://localhost:8080
SILKROUTE_MCP_OPENAV_PEARL_URL=http://localhost:8081
SILKROUTE_MCP_OPENAV_EC20_URL=http://localhost:8082
# flip to true when you want the agent to actually move devices:
SILKROUTE_MCP_OPENAV_MUTATING=false
```

SilkRoute launches `openav-mcp` itself as an MCP subprocess — you don't run
`python -m openav_mcp` by hand once this is configured.

## Ubuntu (local sovereign model)

Same as above, plus local inference:

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:14b          # 16GB box; use qwen2.5:32b on a >=24GB box
```

```bash
SILKROUTE_HARDWARE_PROFILE=mac-mini   # 16GB budget (mac-studio for 64GB)
SILKROUTE_OLLAMA_ENABLED=true
SILKROUTE_OLLAMA_BASE_URL=http://localhost:11434
# OpenRouter key still recommended: PREMIUM-tier work escalates to the cloud
SILKROUTE_OPENROUTER_API_KEY=sk-or-...
```

Routine room control now runs entirely on-box ($0, works with the internet down).

## Verify

```bash
# 1. Model routing honors the profile:
silkroute models                              # registry incl. Claude Haiku 4.5
# 2. Read-only end-to-end (safe — no device mutation):
silkroute run "what is the status of the pearl and the camera?"
# 3. Control (requires SILKROUTE_MCP_OPENAV_MUTATING=true):
silkroute run "move the camera to preset 1, then start recording"
```

## Security posture

- `SILKROUTE_MCP_OPENAV_MUTATING=false` (default) launches openav-mcp with
  `--read-only`: only status/inspection tools exist. Control is an explicit opt-in.
- The default tool allowlist excludes two of the bridge's 12 tools:
  `ec20_tracking` (AI tracking not yet wire-controllable — CGI path pending) and
  `ec20_ptz` (absolute-degree moves await on-hardware calibration; `ec20_jog` and
  presets cover live framing without it).
- If you expose SilkRoute's REST API or dashboard beyond localhost, set
  `SILKROUTE_API_KEY` (strong secret) and `SILKROUTE_ENVIRONMENT=production` —
  the CLI-only flow above doesn't need it, a networked deployment does.
- Keep the Pi on a static IP / DHCP reservation, and give devices reservations too —
  the agent addresses devices by the IPs in `SILKROUTE_MCP_OPENAV_DEVICES`.

## Future: RunPod / remote-GPU delegation

The `raspberry-pi` posture doesn't care *where* the cloud brain lives. Pointing the
OpenRouter key at a RunPod-hosted vLLM endpoint (or any OpenAI-compatible URL) is the
planned next experiment for a fully self-hosted delegated brain.
