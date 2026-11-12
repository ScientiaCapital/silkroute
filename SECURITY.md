# Security

## Reporting a vulnerability

Use GitHub's private vulnerability reporting: open the Security tab of this repository and choose "Report a
vulnerability". If that is not available to you, email tkipper@gmail.com. Please don't open a public issue.

You can expect a first reply within a few days. SilkRoute is an alpha project maintained by one person, so fixes
are best effort.

## Trust model

SilkRoute runs a language model that can call tools. Treat the model as steerable by anything it reads: repo
files, web pages, tool output and device names.

- **Network:** the `http_request` tool and the HTTP skill send requests through an SSRF guard
  (`src/silkroute/network/ssrf.py`). It allows only globally routable addresses, checks every DNS answer, refuses
  when resolution fails, re-checks each redirect hop (at most 5), drops the Authorization, Cookie and
  Proxy-Authorization headers when a redirect changes scheme or host, and connects to the address it checked.
  These tools connect directly and do not use `HTTP(S)_PROXY`. Model-provider calls through LiteLLM and other
  internal clients do not pass through the guard.
- **Files:** `read_file`, `write_file` and `list_directory` refuse paths outside the workspace, following
  symlinks. A symlink swapped in between the check and the open is not covered.
- **Shell:** commands run with a scrubbed environment (no variables containing KEY, TOKEN, SECRET or PASSWORD, and
  no `SILKROUTE_`, `OPENROUTER_` or `ANTHROPIC_` variables). The command filter is a denylist, not isolation: a
  command can still read files on disk such as `.env`. Run untrusted workloads in a container.
- **git:** `git_ops` allows read-only subcommands and refuses arguments that write files or run programs. A
  repository whose own `.git/config` is attacker-controlled can still make git run programs.
- **MCP server:** `silkroute mcp serve` exports a read-only allowlist; `shell_exec` and `write_file` need
  `--workspace`.
- **API:** binds to 127.0.0.1 by default. `SILKROUTE_ENVIRONMENT=production` refuses to start without
  `SILKROUTE_API_KEY`. `SILKROUTE_API_DEMO_MODE=true` blocks `/runtime/*`, `POST /tasks` and the supervisor
  endpoints. The public `/demo/*` endpoints stay open in every mode; `/demo/stream?live=true` accepts only
  `ollama/` models, so it never calls a paid provider.
- **Compose:** `docker-compose.yml` publishes LiteLLM, Postgres and Redis on 127.0.0.1 only. Set real passwords
  before using it beyond a laptop.

Keep provider keys in `.env` (gitignored), never in code, fixtures or logs. Only point the AV demo at devices you
own and are allowed to control.
