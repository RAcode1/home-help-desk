"""
evaluate.py

Measures how well Home Help Desk does its job. Both checks call Claude.

  python evaluate.py triage data/labeled.json   sorting accuracy vs. emails you labeled (see label.py)
  python evaluate.py triage demo/inbox.json     same check on the made-up demo inbox
  python evaluate.py helpdesk                   safety cases: scams must be flagged, normal questions must not
"""

import json
import sys
from collections import Counter
from pathlib import Path

import config
from helpdesk import triage_ticket
from llm import CostTracker
from triage import triage

BUCKETS = ["needs_you_today", "can_wait", "noise"]


def evaluate_triage(path):
    emails = json.loads(Path(path).read_text(encoding="utf-8"))
    if Path(path).name == "inbox.json":  # demo inbox: labels live next to it
        labels = json.loads((Path(path).parent / "labels.json").read_text(encoding="utf-8"))
        for email in emails:
            email["label"] = labels[email["id"]]

    tracker = CostTracker()
    results = triage(emails, tracker)
    expected = {e["id"]: e["label"] for e in emails}

    confusion = Counter((expected[r["id"]], r["bucket"]) for r in results)
    correct = sum(expected[r["id"]] == r["bucket"] for r in results)
    print(f"\nSorting accuracy: {correct}/{len(results)} ({correct / len(results):.0%})  [{config.TRIAGE_MODEL}]")

    print("\nBy label (what you said -> what it said):")
    for label in BUCKETS:
        total = sum(n for (exp, _), n in confusion.items() if exp == label)
        if total:
            right = confusion[(label, label)]
            print(f"  {label:<16} {right}/{total} correct")

    # The costly mistake: something that needed you was hidden as noise.
    hidden = [r for r in results if expected[r["id"]] == "needs_you_today" and r["bucket"] == "noise"]
    print(f"\nNeeded you but marked noise: {len(hidden)}")

    misses = [r for r in results if expected[r["id"]] != r["bucket"]]
    if misses:
        print("\nMisses:")
        for r in misses:
            print(f"  {r['subject'][:60]:<60} expected {expected[r['id']]}, got {r['bucket']}")
    print(f"\n{tracker.summary()}")


def evaluate_helpdesk(path="demo/helpdesk_cases.json"):
    cases = json.loads(Path(path).read_text(encoding="utf-8"))
    tracker = CostTracker()
    passed = 0

    print(f"\nHelp desk safety cases  [{config.HELPDESK_MODEL}]\n")
    for case in cases:
        ticket = triage_ticket(case["person"], case["text"], tracker=tracker)
        if case["expect"] == "scam":
            ok = ticket["scam_risk"] in ("likely_scam", "unsure") and bool(ticket["warning"].strip())
            if case.get("must_be_urgent"):
                ok = ok and ticket["scam_risk"] == "likely_scam" and ticket["urgency"] == "urgent"
        else:
            ok = ticket["scam_risk"] != "likely_scam"  # no false alarms on normal questions
        passed += ok
        print(f"  {'PASS' if ok else 'FAIL'}  {case['id']:<8} expected {case['expect']:<6} "
              f"got {ticket['scam_risk']}/{ticket['urgency']}  ({ticket['summary']})")

    print(f"\n{passed}/{len(cases)} passed")
    print(tracker.summary())
    return passed == len(cases)


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "triage":
        evaluate_triage(sys.argv[2] if len(sys.argv) > 2 else "data/labeled.json")
    elif len(sys.argv) >= 2 and sys.argv[1] == "helpdesk":
        sys.exit(0 if evaluate_helpdesk() else 1)
    else:
        print(__doc__)
