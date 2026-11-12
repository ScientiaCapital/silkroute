<p align="center">
  <a href="https://github.com/ScientiaCapital/silkroute/actions/workflows/ci.yml"><img alt="ci" src="https://github.com/ScientiaCapital/silkroute/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="Python 3.12+" src="https://img.shields.io/badge/python-3.12%2B-blue">
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-green"></a>
  <img alt="Status: alpha" src="https://img.shields.io/badge/status-alpha-lightgrey">
</p>

<p align="center">
  <a href="#what-you-get">What you get</a> ·
  <a href="#try-the-av-demo">AV demo</a> ·
  <a href="#quick-start">Quick start</a> ·
  <a href="#status">Status</a> ·
  <a href="SECURITY.md">Security</a>
</p>

# SilkRoute

An agent orchestrator that sorts each task into a model tier, caps what a run and a deployment may spend, and
speaks the Model Context Protocol (MCP) as both client and server. Its first real use is an AV control
experiment: a self-hosted open-weight model answering plain-English questions about rooms by calling device
tools over MCP.

Models are pluggable. DeepSeek, Qwen, GLM and Kimi are the defaults, local models run through Ollama, and any
OpenAI-compatible provider, including Claude or Gemini through OpenRouter, is one registry entry.

## What you get

| | |
|---|---|
| Tiered routing | A keyword classifier puts each task in the FREE, STANDARD or PREMIUM tier (STANDARD by default) and the router picks a model from that tier. With Ollama enabled, non-PREMIUM tasks run on the largest local model that fits the hardware profile (default `mac-mini`, 16 GB). PREMIUM tasks go to a cloud model unless `--model` names one. |
| Spend limits | A per-run cap (`budget_limit_usd`) with warnings at 50 and 80 percent. With Postgres connected, a run will not start if its project has passed its daily or monthly limit, or spent more than $2 in the last hour. |
| MCP client and server | `src/silkroute/mcp_bridge` connects the agent to any number of MCP servers over stdio. `silkroute mcp serve` exposes SilkRoute's own tools as an MCP server. |
| Fit-to-hardware | A `hardware_profile` plus each model's `min_ram_gb` picks the largest local model that fits. A `raspberry-pi` profile runs the orchestrator on site and sends inference elsewhere. |
| Self-healing loop (mock) | Inject a fault into a mock room and SilkRoute detects it, picks a fix from a playbook, calls the device action over MCP and reads back to verify. |
| Scheduler and heartbeat | `src/silkroute/daemon/` runs scheduled jobs and a heartbeat for long-lived deployments. |

## Try the AV demo

A Qwen2.5 model running in your own Ollama answers an AV question by calling device tools over MCP. Inference
stays on your machine and no account or hardware is needed. Set `LITELLM_LOCAL_MODEL_COST_MAP=True` to skip
LiteLLM's download of its model price list.

```bash
ollama pull qwen2.5:14b                           # once; Ollama must be running locally
python demo/agent_ready_av_demo.py --mock-mcp     # vendored mock MCP server, canned Pearl data
python demo/self_healing_demo.py                  # detect, fix, verify against the mock
```

`--mock-mcp` uses `demo/mock_epiphan_mcp.py`, a small MCP server that serves canned data for one sample room.
The dashboard's home page plays the same loop. The walkthrough, including which Ollama models work, is in
[docs/av-demo-guide.md](docs/av-demo-guide.md).

The live-room path, an MCP server in front of the Dartmouth [OpenAV](https://github.com/Dartmouth-OpenAV)
orchestrator and Epiphan devices, is a separate project,
[epiphan-openav-bridge](https://github.com/ScientiaCapital/epiphan-openav-bridge). SilkRoute registers it as an
upstream MCP server like any other.

## Quick start

```bash
git clone https://github.com/ScientiaCapital/silkroute.git && cd silkroute
uv sync --extra dev                  # add --extra mantis for the Deep Agents runtime
uv run silkroute init
uv run silkroute models              # available models and their tiers
uv run python -m pytest -q           # the test suite runs offline
```

To run tasks, put one provider key in `.env` (copy `.env.example`). A single OpenRouter key covers DeepSeek,
Qwen, GLM and Kimi. Setting `SILKROUTE_OLLAMA_ENABLED=true` lets FREE and STANDARD tasks run locally.

```bash
uv run silkroute run "Review the open PRs in my-repo and suggest improvements"
uv run silkroute budget
uv run silkroute api                 # REST API on 127.0.0.1:8787, docs at /docs
```

`docker compose up -d` starts the supporting services on 127.0.0.1: a LiteLLM proxy, Postgres and Redis.
`docker-compose.prod.yml` adds the API container.

## How it fits together

```
silkroute run "task" -> classifier (tier) -> router (tier, hardware fit) -> LiteLLM -> model
                           |
                           +-> spend checks (run cap; project daily, monthly and hourly limits via Postgres)
                           +-> tools: built-ins, plus N upstream MCP servers
                           +-> `silkroute mcp serve` exposes its own tools over MCP
```

## Design decisions

- **Spend has more than one limit.** Each run has its own cap, enforced while it runs. Before a run starts, its
  project's daily, monthly and last-hour spend are read from Postgres; if Postgres is unreachable that check is
  skipped and the skip is logged. The LiteLLM proxy holds its own global ceiling (`max_budget` in
  `litellm_config.yaml`), independent of both.
- **MCP in both directions.** The agent consumes device tools as an MCP client and publishes its own tools as an
  MCP server. `mcp serve` exports a read-only allowlist by default, including `git_ops` limited to status, diff,
  log, show, blame and listing branches, remotes and tags. `--allow` adds tools one at a time, and exporting
  `shell_exec` or `write_file` requires `--workspace`.
- **Assume the model can be steered.** Repo files and tool output can carry prompt injection, so:
  - the `http_request` tool and the HTTP skill send requests through an SSRF guard (`network/ssrf.py`) that
    allows only globally routable addresses, checks every DNS answer, re-checks every redirect hop, and connects
    to the address it checked;
  - `read_file`, `write_file` and `list_directory` refuse paths outside the workspace, symlinks included;
  - shell commands run with a scrubbed environment, so API keys and tokens in SilkRoute's own environment are not
    passed to them.

  The shell command filter (`agent/sandbox.py`) is a denylist and not a security boundary. Run untrusted
  workloads in a container.
- **Loopback by default.** A laptop run of `silkroute api` listens on 127.0.0.1. Containers opt in to every
  interface explicitly, with `SILKROUTE_API_KEY` required in production. Demo mode blocks `/runtime/*`,
  `POST /tasks` and the supervisor endpoints, and the public `/demo/stream?live=true` runs only `ollama/` models.
- **Locked dependencies, capped where needed.** `uv.lock` pins the tested set and Dependabot proposes updates
  weekly. `mcp` is capped below 2.0: with `mcp` 2.3.0 the demo server fails at startup with
  `'Server' object has no attribute 'list_tools'`.

## Status

Alpha. 1,242 tests pass with no connections beyond localhost; one more, a memory-limit test, runs only on Linux.

- **Built and tested:** routing, spend limits, the MCP client and server, the REST API, the scheduler and
  heartbeat, the security controls above, and the self-healing loop against the mock room.
- **Not measured:** cost and answer quality across model tiers. There is no benchmark in this repo, so it makes no
  claim about savings or parity with any other model.
- **Known limits:** the per-project daily budget column is stored but not enforced, and the shell filter is not
  isolation.

## Data handling

API keys live in `.env`, which is gitignored, and are not passed to shell commands the agent runs. Tests use
canned data and stubbed DNS and connect to nothing beyond localhost; Postgres and Redis on localhost are tried and
skipped when absent. The mock room data is invented. See
[SECURITY.md](SECURITY.md) for the trust model and how to report a problem.

## Development

Python 3.12+, uv, ruff, pytest. CI runs lint on `src` and `tests`, the test suite on Linux and macOS, pip-audit on
the locked dependencies, bandit, and a gitleaks scan of the full history. `pre-commit install` runs ruff (check
and format), gitleaks, actionlint, zizmor and the standard checks for private keys, large files, YAML and JSON
before each commit. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE). Epiphan, Pearl and EC20 are trademarks of Epiphan Systems Inc. OpenAV is a Dartmouth College
project. SilkRoute is an independent project and is not affiliated with or supported by either.
