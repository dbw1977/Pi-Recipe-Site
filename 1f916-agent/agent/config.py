"""Configuration — everything comes from the environment / a `.env` file.

Nothing here is hardcoded and no secrets are committed (see `.env.example`).
Load order: real process environment wins over `.env`, so a systemd unit or
cron line can override the file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Minimal `.env` loader (no third-party dependency).

    Sets a key only if it is not already present in the real environment, so
    the process environment always takes precedence over the file.
    """
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


@dataclass
class Config:
    # --- Forum endpoint --------------------------------------------------
    forum_base_url: str = "https://1f916.ai"
    mcp_path: str = "/mcp"           # full (read + write) endpoint
    mcp_read_path: str = "/mcp/read"  # read-only endpoint (used by `observe`)
    http_timeout: float = 30.0
    user_agent: str = "1f916-agent/0.1 (+https://github.com/1f916-ai/1f916)"

    # --- Agent identity (declared to the forum at registration) ----------
    handle: str = "pi-forager"
    declared_model: str = "claude-opus-5"

    # --- The "brain": Anthropic model that decides what to do ------------
    anthropic_api_key: str | None = None
    llm_model: str = "claude-opus-5"
    llm_effort: str = "high"          # low | medium | high | xhigh | max
    llm_max_tokens: int = 8000

    # --- Scarcity budgets (forum-enforced too; we mirror them locally) ---
    max_posts_per_day: int = 1
    max_comments_per_day: int = 20
    max_votes_per_day: int = 50

    # --- Local state (LOCAL DISK ONLY — never a network filesystem) ------
    state_dir: Path = field(default_factory=lambda: Path.home() / ".1f916-agent")

    # --- Behaviour -------------------------------------------------------
    # When true, the agent plans and logs but performs no write actions.
    # Handy for the first run; set FALSE for full autonomy.
    dry_run: bool = False
    # How many front-page posts to open fully and hand to the brain.
    threads_to_read: int = 6
    feed_limit: int = 25

    # --- Daily report email (SMTP; Gmail needs an App Password) ----------
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    report_to: str | None = None
    report_from: str | None = None

    # ---------------------------------------------------------------------
    @property
    def mcp_url(self) -> str:
        return self.forum_base_url.rstrip("/") + self.mcp_path

    @property
    def mcp_read_url(self) -> str:
        return self.forum_base_url.rstrip("/") + self.mcp_read_path

    @property
    def identity_file(self) -> Path:
        return self.state_dir / "identity.json"

    @property
    def db_file(self) -> Path:
        return self.state_dir / "ledger.db"

    @property
    def reports_dir(self) -> Path:
        return self.state_dir / "reports"

    @property
    def email_configured(self) -> bool:
        return bool(self.smtp_user and self.smtp_password and self.report_to)

    def ensure_dirs(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)


def load_config(dotenv_path: str | os.PathLike | None = None) -> Config:
    """Build a Config from the environment, loading `.env` first if present."""
    if dotenv_path is None:
        # Look next to the package (…/1f916-agent/.env) and in the cwd.
        here = Path(__file__).resolve().parent.parent
        for candidate in (here / ".env", Path.cwd() / ".env"):
            if candidate.is_file():
                dotenv_path = candidate
                break
    if dotenv_path is not None:
        _load_dotenv(Path(dotenv_path))

    state_dir = Path(os.environ.get("AGENT_STATE_DIR", str(Path.home() / ".1f916-agent")))

    return Config(
        forum_base_url=os.environ.get("FORUM_BASE_URL", "https://1f916.ai"),
        mcp_path=os.environ.get("FORUM_MCP_PATH", "/mcp"),
        mcp_read_path=os.environ.get("FORUM_MCP_READ_PATH", "/mcp/read"),
        http_timeout=float(os.environ.get("FORUM_HTTP_TIMEOUT", "30")),
        handle=os.environ.get("AGENT_HANDLE", "pi-forager"),
        declared_model=os.environ.get("AGENT_DECLARED_MODEL", "claude-opus-5"),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        llm_model=os.environ.get("AGENT_LLM_MODEL", "claude-opus-5"),
        llm_effort=os.environ.get("AGENT_LLM_EFFORT", "high"),
        llm_max_tokens=_int("AGENT_LLM_MAX_TOKENS", 8000),
        max_posts_per_day=_int("MAX_POSTS_PER_DAY", 1),
        max_comments_per_day=_int("MAX_COMMENTS_PER_DAY", 20),
        max_votes_per_day=_int("MAX_VOTES_PER_DAY", 50),
        state_dir=state_dir,
        dry_run=_bool("AGENT_DRY_RUN", False),
        threads_to_read=_int("AGENT_THREADS_TO_READ", 6),
        feed_limit=_int("AGENT_FEED_LIMIT", 25),
        smtp_host=os.environ.get("SMTP_HOST", "smtp.gmail.com"),
        smtp_port=_int("SMTP_PORT", 587),
        smtp_user=os.environ.get("SMTP_USER"),
        smtp_password=os.environ.get("SMTP_PASSWORD"),
        report_to=os.environ.get("REPORT_TO"),
        report_from=os.environ.get("REPORT_FROM") or os.environ.get("SMTP_USER"),
    )
