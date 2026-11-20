"""
scheduled_run.py

Windows Task Scheduler runs this every 30 minutes from 7 AM, and when you
sign in (set up by setup_schedule.ps1). It delivers the morning digest once
a day:

- never before 7 AM
- at 7 AM if the laptop is on, otherwise at the first check after it's on
- if a run fails (no internet, Gmail sign-in expired), the next check tries again
- once today's digest is delivered, every later check does nothing

It runs with pythonw.exe, so no window pops up. Results go to data/digest.log.
"""

import os
import traceback
from datetime import date, datetime
from pathlib import Path

os.chdir(Path(__file__).resolve().parent)
os.environ["HHD_NONINTERACTIVE"] = "1"  # never wait on a sign-in window nobody will see

START_HOUR = 7
MARKER = Path("data/last_delivered.txt")
LOG = Path("data/digest.log")


def log(message):
    LOG.parent.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as file:
        file.write(f"{datetime.now():%Y-%m-%d %H:%M}  {message}\n")


def main():
    today = date.today().isoformat()
    if datetime.now().hour < START_HOUR:
        return
    if MARKER.exists() and MARKER.read_text().strip() == today:
        return  # already delivered today

    try:
        from digest import run, subject_line
        result = run(deliver=True)
    except Exception:
        log("Failed; the next check will try again.\n" + traceback.format_exc())
        return

    MARKER.write_text(today)
    log(f"Delivered: {subject_line(result)}  ({result['cost']})")


if __name__ == "__main__":
    main()
