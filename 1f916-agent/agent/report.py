"""Build and deliver the daily interaction report.

The report is rendered purely from the ledger (so it is accurate even if a run
half-failed), written to `state/reports/YYYY-MM-DD.md`, and — when SMTP is
configured — emailed. If SMTP is not configured we degrade gracefully: the file
is still written and the path is returned (golden rule: never fake success).
"""

from __future__ import annotations

import html
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

from .config import Config
from .identity import load_identity
from .ledger import Ledger


def build_report(cfg: Config, ledger: Ledger, *, window_hours: int = 24) -> dict[str, str]:
    """Return {'subject', 'markdown', 'html', 'date'} for the last window."""
    now = datetime.now(timezone.utc)
    since = (now - timedelta(hours=window_hours)).isoformat()
    date_str = now.strftime("%Y-%m-%d")

    actions = ledger.actions_since(since)
    identity = load_identity(cfg.identity_file)
    handle = identity.handle if identity else cfg.handle

    posts = [a for a in actions if a["kind"] == "post" and a["success"]]
    comments = [a for a in actions if a["kind"] == "comment" and a["success"]]
    votes = [a for a in actions if a["kind"] == "vote" and a["success"]]
    skipped_or_failed = [a for a in actions if not a["success"] and a["kind"] in {"post", "comment", "vote"}]

    # Pull the most recent reflection / stats snapshots for colour.
    obs = ledger.observations_since(since, kinds=["stats", "identity", "reflection"])
    reflection = _last_obs_text(obs, "reflection")
    stats = _last_obs_json(obs, "stats")

    subject = (
        f"[1f916] @{handle} — {date_str}: "
        f"{len(posts)} post, {len(comments)} comments, {len(votes)} votes"
    )

    md = _render_markdown(
        handle, date_str, reflection, posts, comments, votes, skipped_or_failed, stats, cfg
    )
    html_body = _render_html(
        handle, date_str, reflection, posts, comments, votes, skipped_or_failed, stats, cfg
    )
    return {"subject": subject, "markdown": md, "html": html_body, "date": date_str}


def write_report_file(cfg: Config, report: dict[str, str]) -> Path:
    cfg.reports_dir.mkdir(parents=True, exist_ok=True)
    path = cfg.reports_dir / f"{report['date']}.md"
    path.write_text(report["markdown"], encoding="utf-8")
    return path


def send_email(cfg: Config, report: dict[str, str]) -> bool:
    """Send the report email. Returns True on success, False if not configured."""
    if not cfg.email_configured:
        return False
    msg = MIMEMultipart("alternative")
    msg["Subject"] = report["subject"]
    msg["From"] = cfg.report_from or cfg.smtp_user or ""
    msg["To"] = cfg.report_to or ""
    msg.attach(MIMEText(report["markdown"], "plain", "utf-8"))
    msg.attach(MIMEText(report["html"], "html", "utf-8"))

    with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=30) as server:
        server.ehlo()
        server.starttls()
        server.login(cfg.smtp_user, cfg.smtp_password)  # type: ignore[arg-type]
        server.send_message(msg)
    return True


# -- rendering -------------------------------------------------------------
def _render_markdown(handle, date_str, reflection, posts, comments, votes, failures, stats, cfg) -> str:
    out = [f"# 1f916 daily report — @{handle} — {date_str}", ""]
    if cfg.dry_run:
        out += ["> ⚠️ DRY-RUN mode: intended actions were logged but NOT sent to the forum.", ""]
    out += [
        "## Summary",
        f"- Posts made: **{len(posts)}** / {cfg.max_posts_per_day}",
        f"- Comments made: **{len(comments)}** / {cfg.max_comments_per_day}",
        f"- Votes cast: **{len(votes)}** / {cfg.max_votes_per_day}",
    ]
    if failures:
        out.append(f"- Skipped / failed writes: **{len(failures)}**")
    out.append("")

    if reflection:
        out += ["## What I made of the forum today", reflection, ""]

    if posts:
        out += ["## Post I published"]
        for a in posts:
            out += [f"### {a['summary']}", ""]
            body = _payload_field(a, "body")
            if body:
                out += [body, ""]
    if comments:
        out += ["## Comments I made"]
        for a in comments:
            tid = a["target_id"]
            out += [f"- **on post #{tid}** — {_short(_payload_field(a, 'body'))}"]
        out.append("")
    if votes:
        out += ["## Upvotes I cast"]
        for a in votes:
            out.append(f"- {a['target_type']} #{a['target_id']} — {_reason_from_summary(a['summary'])}")
        out.append("")
    if failures:
        out += ["## Skipped or failed"]
        for a in failures:
            out.append(f"- {a['kind']} {a.get('summary','')} — {a.get('error') or 'skipped'}")
        out.append("")
    if stats:
        out += ["## Forum stats snapshot", "```json", _short(str(stats), 1500), "```", ""]

    out += ["---", f"_Generated by 1f916-agent at {datetime.now(timezone.utc).isoformat()}._"]
    return "\n".join(out)


def _render_html(handle, date_str, reflection, posts, comments, votes, failures, stats, cfg) -> str:
    def esc(s: Any) -> str:
        return html.escape(str(s))

    parts = [
        "<div style=\"font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:640px;margin:auto;color:#1a1a1a\">",
        f"<h1 style=\"font-size:20px\">🤖 1f916 daily report — @{esc(handle)}</h1>",
        f"<p style=\"color:#666\">{esc(date_str)}</p>",
    ]
    if cfg.dry_run:
        parts.append("<p style=\"background:#fff3cd;padding:8px;border-radius:6px\">⚠️ DRY-RUN: actions logged but not sent.</p>")
    parts.append(
        "<div style=\"display:flex;gap:12px;margin:12px 0\">"
        f"{_stat_pill('Posts', len(posts), cfg.max_posts_per_day)}"
        f"{_stat_pill('Comments', len(comments), cfg.max_comments_per_day)}"
        f"{_stat_pill('Votes', len(votes), cfg.max_votes_per_day)}"
        "</div>"
    )
    if reflection:
        parts.append(f"<h2 style=\"font-size:15px\">Today's read</h2><p>{esc(reflection)}</p>")
    if posts:
        parts.append("<h2 style=\"font-size:15px\">Post I published</h2>")
        for a in posts:
            parts.append(f"<h3 style=\"font-size:14px\">{esc(a['summary'])}</h3>")
            body = _payload_field(a, "body")
            if body:
                parts.append(f"<p style=\"white-space:pre-wrap\">{esc(body)}</p>")
    if comments:
        parts.append("<h2 style=\"font-size:15px\">Comments</h2><ul>")
        for a in comments:
            parts.append(f"<li><b>post #{esc(a['target_id'])}</b>: {esc(_short(_payload_field(a, 'body')))}</li>")
        parts.append("</ul>")
    if votes:
        parts.append("<h2 style=\"font-size:15px\">Upvotes</h2><ul>")
        for a in votes:
            parts.append(f"<li>{esc(a['target_type'])} #{esc(a['target_id'])} — {esc(_reason_from_summary(a['summary']))}</li>")
        parts.append("</ul>")
    if failures:
        parts.append("<h2 style=\"font-size:15px;color:#a00\">Skipped / failed</h2><ul>")
        for a in failures:
            parts.append(f"<li>{esc(a['kind'])} — {esc(a.get('error') or 'skipped')}</li>")
        parts.append("</ul>")
    parts.append("<hr><p style=\"color:#999;font-size:12px\">Generated by 1f916-agent.</p></div>")
    return "".join(parts)


def _stat_pill(label: str, value: int, cap: int) -> str:
    return (
        "<div style=\"flex:1;text-align:center;background:#f4f4f5;border-radius:8px;padding:10px\">"
        f"<div style=\"font-size:22px;font-weight:700\">{value}</div>"
        f"<div style=\"font-size:11px;color:#666\">{html.escape(label)} / {cap}</div></div>"
    )


# -- small helpers ---------------------------------------------------------
def _payload_field(action: dict, field: str) -> str:
    import json
    raw = action.get("payload")
    if not raw:
        return ""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return ""
    return str(data.get(field, "")) if isinstance(data, dict) else ""


def _short(text: str, limit: int = 200) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _reason_from_summary(summary: str) -> str:
    return summary.split("—", 1)[1].strip() if "—" in (summary or "") else ""


def _last_obs_text(observations: list[dict], kind: str) -> str:
    import json
    for obs in reversed(observations):
        if obs["kind"] == kind:
            try:
                data = json.loads(obs["data"])
                return data if isinstance(data, str) else str(data)
            except (json.JSONDecodeError, TypeError):
                return obs["data"] or ""
    return ""


def _last_obs_json(observations: list[dict], kind: str) -> Any:
    import json
    for obs in reversed(observations):
        if obs["kind"] == kind:
            try:
                return json.loads(obs["data"])
            except (json.JSONDecodeError, TypeError):
                return None
    return None
