"""Agent-ready AV demo: a self-hosted, open-weight LLM answers a plain-English
AV question by calling epiphan-mcp-server's tools directly over MCP.

What this proves:
  - Open-weight model (Qwen2.5, served locally via Ollama — no cloud inference)
  - Self-hosted end to end: silkroute (orchestrator) -> MCP (standard protocol)
    -> epiphan-mcp-server (device control), all on localhost
  - MCP-standard tool calling: the same protocol Claude Desktop/Cursor use, so
    swapping the model or the client is a config change, not a rewrite
  - Zero vendor lock-in: model, orchestrator, and device server are all
    independently swappable

Usage:
    python demo/agent_ready_av_demo.py --mock-mcp     # fully self-contained (no external repo)
    python demo/agent_ready_av_demo.py --mock-pearl   # mock Pearl HTTP + real epiphan-mcp-server
    python demo/agent_ready_av_demo.py --mock-mcp --model ollama/qwen2.5:32b
    python demo/agent_ready_av_demo.py  # against the real, live Pearl fleet
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

DEFAULT_QUESTION = "did recording start in room 320-B"
DEFAULT_MODEL = "ollama/qwen2.5:14b"

# Sibling repo under tk_projects/ — override with --epiphan-python if your
# layout differs. Must be a Python interpreter with epiphan_mcp installed
# (that repo's own venv), not silkroute's — they're separate environments.
DEFAULT_EPIPHAN_PYTHON = str(
    Path(__file__).parent.parent.parent / "epiphan-mcp-server" / ".venv" / "bin" / "python"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mock-mcp",
        action="store_true",
        help="Fully self-contained: use the vendored mock epiphan MCP server "
        "(no external epiphan-mcp-server repo, no HTTP). Best for a first-touch demo.",
    )
    parser.add_argument(
        "--mock-pearl",
        action="store_true",
        help="Serve canned Pearl API responses instead of hitting a real fleet "
        "(still requires the external epiphan-mcp-server via --epiphan-python)",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"default: {DEFAULT_MODEL}")
    parser.add_argument(
        "--question", default=DEFAULT_QUESTION, help=f"default: {DEFAULT_QUESTION!r}"
    )
    parser.add_argument(
        "--epiphan-python",
        default=DEFAULT_EPIPHAN_PYTHON,
        help="Path to epiphan-mcp-server's venv Python interpreter",
    )
    parser.add_argument(
        "--pearl-devices",
        default="",
        help="Real PEARL_DEVICES value (ignored when --mock-pearl is set)",
    )
    parser.add_argument("--pearl-username", default=os.environ.get("PEARL_USERNAME", "admin"))
    parser.add_argument("--pearl-password", default=os.environ.get("PEARL_PASSWORD", ""))
    return parser.parse_args()


async def _amain(args: argparse.Namespace) -> None:
    import json

    from silkroute.agent.loop import run_agent

    mock_server = None
    os.environ.setdefault("SILKROUTE_OLLAMA_ENABLED", "true")

    if args.mock_mcp:
        # Fully self-contained: point the bridge at the vendored stub, run with
        # silkroute's own interpreter. No external repo, no HTTP, no creds.
        stub_path = str(Path(__file__).parent / "mock_epiphan_mcp.py")
        os.environ["SILKROUTE_MCP_EPIPHAN_ENABLED"] = "true"
        os.environ["SILKROUTE_MCP_EPIPHAN_COMMAND"] = sys.executable
        os.environ["SILKROUTE_MCP_EPIPHAN_ARGS"] = json.dumps([stub_path])
        print("[demo] using vendored mock epiphan MCP server (fully self-contained)")
    else:
        pearl_devices = args.pearl_devices
        if args.mock_pearl:
            from pearl_mock_server import start_mock_pearl_server

            mock_server, port = start_mock_pearl_server()
            pearl_devices = f"127.0.0.1:{port}"
            print(f"[demo] mock Pearl fleet listening on {pearl_devices}")
        elif not pearl_devices:
            print(
                "[demo] --pearl-devices not set and neither --mock-mcp nor --mock-pearl passed — "
                "falling back to whatever PEARL_DEVICES is already in the environment.",
            )

        os.environ["SILKROUTE_MCP_EPIPHAN_ENABLED"] = "true"
        os.environ["SILKROUTE_MCP_EPIPHAN_COMMAND"] = args.epiphan_python
        if pearl_devices:
            os.environ["SILKROUTE_MCP_EPIPHAN_PEARL_DEVICES"] = pearl_devices
        os.environ["SILKROUTE_MCP_EPIPHAN_PEARL_USERNAME"] = args.pearl_username
        os.environ["SILKROUTE_MCP_EPIPHAN_PEARL_PASSWORD"] = args.pearl_password

    try:
        session = await run_agent(task=args.question, model_override=args.model)
    finally:
        if mock_server is not None:
            mock_server.shutdown()

    print()
    print("=" * 72)
    if session.status.value == "completed":
        print("This demo proved:")
        print("  - Open-weight model, served locally via Ollama (no cloud inference)")
        print("  - Self-hosted end to end: silkroute -> MCP -> epiphan-mcp-server")
        print("  - MCP-standard tool calling (same protocol as Claude Desktop/Cursor)")
        print("  - Zero vendor lock-in: model, orchestrator, and server all swappable")
    else:
        print(f"Session did not complete (status: {session.status.value}) — nothing proved.")
        print("If the error above is a connection failure to localhost:11434,")
        print("start Ollama first: `ollama serve` and `ollama pull qwen2.5:14b`.")
    print("=" * 72)


def main() -> None:
    args = parse_args()
    asyncio.run(_amain(args))


if __name__ == "__main__":
    main()
