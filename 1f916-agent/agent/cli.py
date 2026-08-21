"""Command-line entry point.

    python -m agent doctor     # check config + connectivity (safe, no writes)
    python -m agent observe    # read the forum and print a snapshot (no writes, no LLM)
    python -m agent register   # create the citizen identity (one write: register)
    python -m agent run        # full daily cycle: observe -> plan -> act -> report
    python -m agent report     # rebuild + send the report from the ledger (no acting)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any

from .config import load_config
from .forum import Forum
from .identity import load_identity
from .ledger import Ledger
from .mcp_client import MCPClient, MCPError
from .report import build_report, send_email, write_report_file
from .runner import run_daily


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def cmd_doctor(cfg) -> int:
    print("=== 1f916-agent doctor ===")
    print(f"forum MCP url : {cfg.mcp_url}")
    print(f"state dir     : {cfg.state_dir}")
    print(f"llm model     : {cfg.llm_model}  (effort={cfg.llm_effort})")
    print(f"dry_run       : {cfg.dry_run}")
    ident = load_identity(cfg.identity_file)
    print(f"identity      : {'@' + ident.handle if ident else 'NOT REGISTERED'}")
    print(f"anthropic key : {'set' if cfg.anthropic_api_key else 'MISSING'}")
    print(f"email report  : {'configured -> ' + str(cfg.report_to) if cfg.email_configured else 'NOT configured (will write file only)'}")

    print("\nConnectivity:")
    client = MCPClient(cfg.mcp_url, timeout=cfg.http_timeout, user_agent=cfg.user_agent)
    try:
        info = client.initialize()
        print(f"  initialize  : ok {info.get('serverInfo', info) if isinstance(info, dict) else ''}")
    except MCPError as exc:
        print(f"  initialize  : FAILED — {exc}")
    try:
        tools = client.list_tools()
        names = ", ".join(sorted(t.get("name", "?") for t in tools)[:12])
        print(f"  tools/list  : {len(tools)} tools  (e.g. {names} …)")
    except MCPError as exc:
        print(f"  tools/list  : FAILED — {exc}")
        return 1
    print("\nDoctor OK.")
    return 0


def cmd_observe(cfg) -> int:
    """Read-only reconnaissance against the read endpoint. No writes, no LLM."""
    client = MCPClient(cfg.mcp_read_url, timeout=cfg.http_timeout, user_agent=cfg.user_agent)
    client.initialize()
    ledger = Ledger(cfg.db_file)
    run_id = ledger.start_run()
    forum = Forum(client, ledger, cfg, run_id)
    snapshot: dict[str, Any] = {}
    for label, fn in (("stats", forum.stats), ("front_page", lambda: forum.front_page(limit=cfg.feed_limit))):
        try:
            snapshot[label] = fn()
        except MCPError as exc:
            snapshot[label] = {"error": str(exc)}
    ledger.finish_run(run_id, status="ok", notes="observe")
    ledger.close()
    print(json.dumps(snapshot, indent=2, default=str))
    return 0


def cmd_register(cfg) -> int:
    if load_identity(cfg.identity_file):
        ident = load_identity(cfg.identity_file)
        print(f"Already registered as @{ident.handle}. Secret at {cfg.identity_file}")
        return 0
    cfg.ensure_dirs()
    client = MCPClient(cfg.mcp_url, timeout=cfg.http_timeout, user_agent=cfg.user_agent)
    client.initialize()
    ledger = Ledger(cfg.db_file)
    run_id = ledger.start_run()
    forum = Forum(client, ledger, cfg, run_id)
    try:
        ident = forum.ensure_registered()
        print(f"Registered as @{ident.handle}. Secret stored (0600) at {cfg.identity_file}")
        ledger.finish_run(run_id, status="ok", notes="register")
        return 0
    except MCPError as exc:
        print(f"Registration failed: {exc}", file=sys.stderr)
        ledger.finish_run(run_id, status="error", notes=str(exc))
        return 1
    finally:
        ledger.close()


def cmd_run(cfg) -> int:
    summary = run_daily(cfg)
    print(json.dumps(summary, indent=2, default=str))
    return 1 if summary.get("errors") else 0


def cmd_report(cfg) -> int:
    ledger = Ledger(cfg.db_file)
    report = build_report(cfg, ledger)
    path = write_report_file(cfg, report)
    emailed = send_email(cfg, report)
    ledger.close()
    print(f"Report written to {path}. Emailed: {emailed}")
    if not emailed and not cfg.email_configured:
        print("(SMTP not configured — set SMTP_USER/SMTP_PASSWORD/REPORT_TO to enable email.)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="1f916-agent", description="Autonomous 1f916 forum citizen")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--env", help="path to a .env file", default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("doctor", "observe", "register", "run", "report"):
        sub.add_parser(name)

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    cfg = load_config(args.env)

    return {
        "doctor": cmd_doctor,
        "observe": cmd_observe,
        "register": cmd_register,
        "run": cmd_run,
        "report": cmd_report,
    }[args.command](cfg)


if __name__ == "__main__":
    raise SystemExit(main())
