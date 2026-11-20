"""
mcp_server.py

An MCP (Model Context Protocol) server, so Claude Desktop or Claude Code can use
Home Help Desk in plain English: read today's digest, see family tickets, log a
new ticket from a forwarded message, and close one.

What it can't do: send, delete, or change email. Logging a ticket calls Claude
with the same scam guardrails as the app; every other tool only reads local files.

Claude Desktop starts it (see README). Quick manual start: python mcp_server.py
"""

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)  # Claude Desktop starts servers in another folder; .env and data/ live here
os.environ.setdefault("HHD_NONINTERACTIVE", "1")  # never open a Gmail sign-in window

from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.types import ToolAnnotations  # noqa: E402

import config  # noqa: E402
from digest import render_text  # noqa: E402
from helpdesk import CATEGORIES, add_ticket, load_tickets, patterns, reply_text, set_status, triage_ticket  # noqa: E402

TICKETS = Path(os.getenv("HHD_TICKETS_FILE", "data/tickets.json"))
LAST_RUN = Path("data/last_run.json")
READ_ONLY = ToolAnnotations(read_only_hint=True)

server = MCPServer(
    name="Home Help Desk",
    instructions=(
        "Home Help Desk: the morning email digest and the family tech-support tickets. "
        f"Family members who send questions: {', '.join(config.FAMILY)}."
    ),
)


@server.tool(annotations=READ_ONLY)
def get_digest() -> str:
    """Today's morning email digest: what needs attention today, likely scams, who still owes a
    reply (with drafted follow-ups), and the noise report with unsubscribe suggestions."""
    if not LAST_RUN.exists():
        return "No digest yet. The morning run hasn't happened; run digest.py once."
    result = json.loads(LAST_RUN.read_text(encoding="utf-8"))
    return f"Digest from {result['generated']}:\n\n{render_text(result)}"


@server.tool(annotations=READ_ONLY)
def list_tickets(status: str = "open") -> str:
    """List family help-desk tickets. status is "open", "resolved", or "all"."""
    tickets = load_tickets(TICKETS)
    if status != "all":
        tickets = [t for t in tickets if t["status"] == status]
    if not tickets:
        return f"No {status} tickets."
    return "\n".join(
        f"{t['id']} | {t['created']} | {t['person']} | {t['urgency']} | {CATEGORIES[t['category']]}"
        f"{' | likely scam' if t['scam_risk'] == 'likely_scam' else ''} | {t['status']}\n    {t['summary']}"
        for t in tickets
    )


@server.tool()
def log_ticket(person: str, message: str) -> str:
    """Log a family member's tech question as a ticket. Claude sorts it (category, urgency, scam check)
    and drafts a simple step-by-step reply in that person's language. `person` must be one of the
    family members; `message` is their message, pasted as-is. Returns the ticket and the reply."""
    if person not in config.FAMILY:
        return f"Unknown person '{person}'. Use one of: {', '.join(config.FAMILY)}."
    ticket = triage_ticket(person, message)
    add_ticket(ticket, TICKETS)
    flag = " (LIKELY SCAM)" if ticket["scam_risk"] == "likely_scam" else ""
    return (
        f"Ticket {ticket['id']} logged: {ticket['summary']}{flag}\n"
        f"Category: {CATEGORIES[ticket['category']]} | urgency: {ticket['urgency']}\n\n"
        f"Reply to send {person}:\n{reply_text(ticket)}"
    )


@server.tool()
def close_ticket(ticket_id: str) -> str:
    """Mark a family help-desk ticket as resolved."""
    if not any(t["id"] == ticket_id for t in load_tickets(TICKETS)):
        return f"No ticket with id {ticket_id}."
    set_status(ticket_id, "resolved", TICKETS)
    return f"Ticket {ticket_id} closed."


@server.tool(annotations=READ_ONLY)
def ticket_patterns() -> str:
    """What keeps coming back: family tickets by type and by person over the last 30 days."""
    stats = patterns(load_tickets(TICKETS))
    word = "ticket" if stats["total"] == 1 else "tickets"
    lines = [f"{stats['total']} {word} in 30 days, {stats['open']} open."]
    lines += [f"{name}: {count}" for name, count in stats["by_category"].items()]
    if stats["repeats"]:
        lines.append("Keeps coming back: " + "; ".join(stats["repeats"]))
    return "\n".join(lines)


if __name__ == "__main__":
    server.run()
