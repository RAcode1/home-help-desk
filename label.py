"""
label.py

Label your own recent emails by hand, so evaluate.py can measure how often
the digest sorts them the way you would. Saves data/labeled.json, which
stays on your computer.

  python label.py 40     label your 40 most recent inbox emails
"""

import json
import sys
from pathlib import Path

import config
import gmail_client as gmail

KEYS = {"1": "needs_you_today", "2": "can_wait", "3": "noise"}
OUT = Path("data/labeled.json")


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    service = gmail.get_service()
    emails = gmail.fetch_inbox(service, "in:inbox newer_than:14d", limit, config.MAX_BODY_CHARS)

    labeled = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []
    done = {e["id"] for e in labeled}
    print("For each email type 1 = needs me today, 2 = can wait, 3 = noise, s = skip, q = quit.\n")

    for email in emails:
        if email["id"] in done:
            continue
        print(f"From:    {email['from']}\nSubject: {email['subject']}\n{email['body'][:200]}\n")
        answer = input("1/2/3/s/q: ").strip().lower()
        if answer == "q":
            break
        if answer in KEYS:
            labeled.append({**email, "label": KEYS[answer]})
        print("-" * 60)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(labeled, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved {len(labeled)} labeled emails to {OUT}")


if __name__ == "__main__":
    main()
