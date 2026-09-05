#!/usr/bin/env python3
"""Convenience entry point so cron/systemd can call one file by absolute path.

Equivalent to `python -m agent`, but runnable from anywhere:

    /usr/bin/python3 /home/pi/1f916-agent/run.py run
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
