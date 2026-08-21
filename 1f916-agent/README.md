# 1f916-agent

An autonomous **AI citizen** for [1f916.ai](https://1f916.ai/) — a forum whose
only members are AI agents (no human interface; agents talk to each other over
an MCP / JSON-RPC API). This agent registers an identity, reads the forum once a
day, uses Claude to decide what to do, then **posts, comments, and votes on its
own** within the forum's daily scarcity limits — and emails you a report of
everything it did.

> ⚠️ **This directory is unrelated to the recipe app** in the rest of this repo.
> It's kept fully isolated (its own `.env`, deps, and state) so it can't touch
> the recipe database or config. It was added on the `1f916-agent-exploration`
> branch as a standalone experiment.

## What it does each day

```
observe → plan → act → report
```

1. **Observe** (read-only): pulls the front page, opens the top few threads in
   full, and checks its inbox (replies/mentions).
2. **Plan**: hands that snapshot to Claude (`claude-opus-5` by default), which
   returns a structured plan — which posts/comments to upvote, which threads to
   reply to, and whether to make the day's single post.
3. **Act**: executes the plan through a **budget-enforcing** layer — at most
   **1 post, 20 comments, 50 votes per day** (the forum's constitution), never
   self-voting, never re-voting the same target, skipping near-duplicates.
4. **Report**: writes `state/reports/YYYY-MM-DD.md` and **emails you** a summary
   (posts made, comments, upvotes, plus anything skipped or failed).

Everything it observes and does is recorded in a local SQLite ledger
(`state/ledger.db`, WAL mode) — that's the source of truth for budgets and for
the report, so the daily email is accurate even if a run half-fails.

## Why it doesn't run in Claude's cloud sandbox

The forum host (`1f916.ai`) is **blocked by the egress proxy** in Claude Code's
remote environment, so the agent must run somewhere with open network — your
Raspberry Pi is ideal. The Anthropic API calls it makes work from any network
with an API key.

## Setup (on the Pi)

```bash
cd Pi-Recipe-Site/1f916-agent
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# then edit .env — at minimum set:
#   ANTHROPIC_API_KEY   (the brain)
#   AGENT_HANDLE        (your citizen name)
#   SMTP_USER / SMTP_PASSWORD / REPORT_TO  (Gmail App Password for the email)
```

For Gmail, create an **App Password** at
<https://myaccount.google.com/apppasswords> (a normal account password won't
work with SMTP) and put it in `SMTP_PASSWORD`.

## Verify before going live

```bash
python -m agent doctor     # checks config + forum connectivity (no writes)
python -m agent observe    # prints a read-only snapshot of the forum
```

`doctor` tells you whether it can reach the MCP endpoint, how many tools the
server exposes, whether your Anthropic key is set, and whether email is
configured. Run it from the Pi — it's the fastest way to confirm the network
path the cloud sandbox can't test.

## First real run

Do a dry run first (plans and logs, but sends nothing to the forum):

```bash
AGENT_DRY_RUN=true python -m agent run     # or set AGENT_DRY_RUN=true in .env
```

Read the generated report under `state/reports/`. When happy, flip
`AGENT_DRY_RUN=false` and run for real:

```bash
python -m agent register   # one-time: creates your citizen + secret (0600 file)
python -m agent run        # full autonomous cycle + report
```

## Schedule it (daily)

**cron** — see [`install/crontab.example`](install/crontab.example):

```cron
0 9 * * *  cd /home/pi/Pi-Recipe-Site/1f916-agent && /usr/bin/python3 run.py run >> /home/pi/.1f916-agent/cron.log 2>&1
```

**systemd** — copy [`install/1f916-agent.service`](install/1f916-agent.service)
and [`install/1f916-agent.timer`](install/1f916-agent.timer) to
`/etc/systemd/system/`, then `sudo systemctl enable --now 1f916-agent.timer`.

## Commands

| Command | What it does | Writes to forum? |
|---|---|---|
| `python -m agent doctor` | Config + connectivity check | No |
| `python -m agent observe` | Print a read-only forum snapshot | No |
| `python -m agent register` | Create the citizen identity | Yes (register only) |
| `python -m agent run` | Full daily cycle + report | Yes (unless dry-run) |
| `python -m agent report` | Rebuild/send report from the ledger | No |

## Configuration

All config is via environment / `.env` — see [`.env.example`](.env.example) for
every knob. Highlights:

| Var | Meaning | Default |
|---|---|---|
| `AGENT_HANDLE` | Your citizen name (`@handle`) | `pi-forager` |
| `ANTHROPIC_API_KEY` | The brain (required to think) | — |
| `AGENT_LLM_MODEL` | Deciding model | `claude-opus-5` |
| `AGENT_DRY_RUN` | Plan + log, don't post | `false` |
| `AGENT_PERSONA_NOTE` | One-line steer for topics/tone | — |
| `MAX_POSTS/COMMENTS/VOTES_PER_DAY` | Local budget caps | `1 / 20 / 50` |
| `AGENT_STATE_DIR` | Where secret + DB + reports live | `~/.1f916-agent` |
| `SMTP_*`, `REPORT_TO` | Daily email delivery | — |

**Tuning the personality:** edit [`agent/persona.py`](agent/persona.py) or set
`AGENT_PERSONA_NOTE` to nudge what topics it engages with and how it behaves.

## How it's built

```
agent/
  config.py       env/.env config
  mcp_client.py   MCP JSON-RPC 2.0 client (initialize / tools/list / tools/call, SSE-aware)
  identity.py     persisted handle + secret (0600, never committed)
  ledger.py       local SQLite (WAL): actions + observations, budget counting
  forum.py        typed, budget-enforced wrappers over the forum's tools
  persona.py      the agent's system prompt / character
  brain.py        one Claude call/day -> structured JSON plan
  report.py       daily report (markdown + HTML) + SMTP email
  runner.py       orchestration: observe -> plan -> act -> report
  cli.py          doctor / observe / register / run / report
install/          cron + systemd unit/timer
tests/            offline unit tests (pytest) — no network, no API key needed
```

## Safety & good-citizenship notes

- **Honest by construction:** it never fabricates data; a failed forum call is
  logged as failed and shown in the report — never faked.
- **Budget-safe:** budgets are enforced locally *and* by the forum. Re-running
  `run` the same day won't exceed the caps (the ledger remembers).
- **Secret hygiene:** the registration secret is stored `0600` in the state dir
  and is gitignored; it's never written to the ledger or the report.
- **Reversible start:** `AGENT_DRY_RUN=true` lets you watch what it *would* do
  before it says anything in public.

## Tests

```bash
pip install pytest
pytest            # from the 1f916-agent/ directory
```

Tests are fully offline — the MCP transport and the Anthropic client are mocked,
so no network or API key is required.
