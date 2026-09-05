"""1f916-agent — an autonomous citizen for the AI-only forum at https://1f916.ai/.

This package is intentionally self-contained and *unrelated* to the recipe app
that lives in the rest of this repository. It runs on a machine with open
network access (e.g. the Raspberry Pi), talks to the forum's MCP (JSON-RPC 2.0)
endpoint, participates once per day within the forum's scarcity limits, records
everything it does in a local SQLite ledger, and emails a daily report.
"""

__version__ = "0.1.0"
