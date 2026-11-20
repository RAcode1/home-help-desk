"""
digest.py

Builds the morning digest:
  1. Needs you today    Claude sorts the inbox like a support queue
  2. Still waiting on   emails you sent that nobody answered, with a follow-up drafted
  3. Can wait / noise   counts only
  4. Noise report       the senders you never open
  5. Family help desk   open tickets

Usage:
  python digest.py --demo       made-up inbox and family requests; saves demo/sample_run.json
  python digest.py              your Gmail; prints the digest and saves digest.html
  python digest.py --deliver    also adds the digest to your own Gmail inbox
"""

import argparse
import json
from datetime import datetime
from html import escape
from pathlib import Path

import config
from helpdesk import CATEGORIES, load_tickets, patterns, triage_ticket
from llm import CostTracker
from noise import noise_line, noise_report
from triage import find_waiting, triage

DEMO_DIR = Path("demo")
SAMPLE_RUN = DEMO_DIR / "sample_run.json"
LAST_RUN = Path("data/last_run.json")


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run(demo=False, deliver=False):
    tracker = CostTracker()

    if demo:
        emails = _load(DEMO_DIR / "inbox.json")
        candidates = [c for c in _load(DEMO_DIR / "sent.json") if c["days_waiting"] >= config.WAIT_DAYS]
        stats = _load(DEMO_DIR / "sender_stats.json")
        tickets = [
            triage_ticket(r["person"], r["text"], tracker=tracker)
            for r in _load(DEMO_DIR / "family_requests.json")
        ]
    else:
        import gmail_client as gmail
        service = gmail.get_service()
        me = gmail.my_address(service)
        emails = gmail.fetch_inbox(service, config.INBOX_QUERY, config.MAX_EMAILS, config.MAX_BODY_CHARS)
        candidates = gmail.fetch_waiting(service, me, config.WAIT_LOOKBACK, config.WAIT_DAYS)
        stats = gmail.fetch_sender_stats(service, config.NOISE_QUERY)
        tickets = load_tickets()

    result = {
        "generated": datetime.now().isoformat(timespec="minutes"),
        "demo": demo,
        "emails": triage(emails, tracker),
        "waiting": find_waiting(candidates[:15], tracker),
        "noise": noise_report(stats),
        "tickets": tickets,
        "ticket_patterns": patterns(tickets),
        "models": {"triage": config.TRIAGE_MODEL, "helpdesk": config.HELPDESK_MODEL},
        "cost": tracker.summary(),
    }

    out = SAMPLE_RUN if demo else LAST_RUN
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    if not demo:
        Path("digest.html").write_text(render_html(result), encoding="utf-8")
        if deliver:
            gmail.insert_digest(service, me, subject_line(result), render_html(result))

    return result


# ==========================================
# RENDERING
# ==========================================

def _sections(result):
    emails = result["emails"]
    return {
        "today": [e for e in emails if e["bucket"] == "needs_you_today" and not e["looks_suspicious"]],
        "suspicious": [e for e in emails if e["looks_suspicious"]],
        "can_wait": sum(e["bucket"] == "can_wait" and not e["looks_suspicious"] for e in emails),
        "noise": sum(e["bucket"] == "noise" and not e["looks_suspicious"] for e in emails),
        "open_tickets": [t for t in result["tickets"] if t["status"] == "open"],
    }


def _things(count):
    return f"{count} thing needs" if count == 1 else f"{count} things need"


def subject_line(result):
    return f"Morning digest: {_things(len(_sections(result)['today']))} you today"


def _ticket_line(ticket):
    flag = " (likely scam)" if ticket["scam_risk"] == "likely_scam" else ""
    return f"[{ticket['urgency']}] {ticket['person']}: {ticket['summary']}{flag}"


def render_text(result):
    s = _sections(result)
    lines = [f"Good morning. {_things(len(s['today']))} you today:"]
    for e in s["today"]:
        due = f" (due: {e['due']})" if e.get("due") else ""
        lines.append(f"  - {e['summary']}{due}")
    if s["suspicious"]:
        lines.append("\nLooks like a scam, don't click anything:")
        lines += [f"  - {e['subject']} (from {e['from']})" for e in s["suspicious"]]
    if result["waiting"]:
        lines.append("\nStill waiting on:")
        lines += [f"  - {w['waiting_on']} ({w['days_waiting']} days): {w['subject']}" for w in result["waiting"]]
    lines.append(f"\nCan wait: {s['can_wait']} emails. Noise: {s['noise']} emails.")
    if result["noise"]:
        lines.append("\nNoise report:")
        lines += [f"  - {noise_line(row)}" for row in result["noise"]]
    if s["open_tickets"]:
        lines.append(f"\nFamily help desk: {len(s['open_tickets'])} open tickets")
        lines += [f"  - {_ticket_line(t)}" for t in s["open_tickets"]]
    lines.append(f"\nThis run: {result['cost']}")
    return "\n".join(lines)


def render_html(result):
    s = _sections(result)

    def items(rows):
        return "<ul>" + "".join(f"<li>{row}</li>" for row in rows) + "</ul>"

    parts = [f"<h2>Good morning. {_things(len(s['today']))} you today</h2>"]
    parts.append(items(
        escape(e["summary"]) + (f" <b>(due: {escape(e['due'])})</b>" if e.get("due") else "")
        for e in s["today"]
    ))
    if s["suspicious"]:
        parts.append("<h3 style='color:#b42318'>Looks like a scam, don't click anything</h3>")
        parts.append(items(f"{escape(e['subject'])} (from {escape(e['from'])})" for e in s["suspicious"]))
    if result["waiting"]:
        parts.append("<h3>Still waiting on</h3>")
        parts.append(items(
            f"{escape(w['waiting_on'])} ({w['days_waiting']} days): {escape(w['subject'])}"
            f"<br><i>Draft follow-up:</i> {escape(w['draft'])}"
            for w in result["waiting"]
        ))
    parts.append(f"<p>Can wait: {s['can_wait']} emails. Noise: {s['noise']} emails.</p>")
    if result["noise"]:
        parts.append("<h3>Noise report</h3>")
        parts.append(items(
            escape(noise_line(row)) + (f" <a href='{escape(row['unsubscribe'])}'>Unsubscribe</a>" if row.get("unsubscribe") else "")
            for row in result["noise"]
        ))
    if s["open_tickets"]:
        parts.append(f"<h3>Family help desk: {len(s['open_tickets'])} open tickets</h3>")
        parts.append(items(escape(_ticket_line(t)) for t in s["open_tickets"]))
    parts.append(f"<p style='color:#667085;font-size:12px'>This run: {escape(result['cost'])}</p>")
    return "<div style='font-family:Arial,sans-serif;max-width:640px'>" + "".join(parts) + "</div>"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the morning digest.")
    parser.add_argument("--demo", action="store_true", help="use the made-up inbox in demo/")
    parser.add_argument("--deliver", action="store_true", help="add the digest to your Gmail inbox")
    args = parser.parse_args()
    print(render_text(run(demo=args.demo, deliver=args.deliver)))
