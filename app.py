"""
app.py

Streamlit app for Home Help Desk.

Demo mode shows a saved run on a made-up inbox and made-up family
requests: no Gmail, no API key, no cost. "My inbox" mode appears once
credentials.json and an ANTHROPIC_API_KEY are set up (see README).

Run:  streamlit run app.py
"""

import json
import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

import config
from helpdesk import CATEGORIES, add_ticket, load_tickets, patterns, reply_text, set_status, triage_ticket
from noise import noise_line, savings_line

load_dotenv()
st.set_page_config(page_title="Home Help Desk", page_icon="🛎️", layout="centered")

SAMPLE_RUN = Path("demo/sample_run.json")
LAST_RUN = Path("data/last_run.json")
LIVE_READY = Path("credentials.json").exists() and bool(os.getenv("ANTHROPIC_API_KEY"))


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


st.title("🛎️ Home Help Desk")
st.caption("I'm my family's unpaid IT department, so I built myself a help desk.")

mode = st.radio(
    "Mode", ["Demo (made-up inbox)", "My inbox"], horizontal=True,
    disabled=not LIVE_READY, label_visibility="collapsed",
)
demo = mode.startswith("Demo")
if not LIVE_READY:
    st.info("This is the demo: a saved run on a made-up inbox. Nothing here is real email.")

digest_tab, helpdesk_tab, how_tab = st.tabs(["Morning digest", "Family help desk", "How it works"])

# ==========================================
# MORNING DIGEST
# ==========================================
with digest_tab:
    result = load_json(SAMPLE_RUN) if demo else load_json(LAST_RUN)
    if not demo and st.button("Run now on my inbox", type="primary"):
        from digest import run
        with st.spinner("Reading and sorting your email..."):
            result = run()

    if not result:
        st.write("No run yet.")
    else:
        emails = result["emails"]
        today = [e for e in emails if e["bucket"] == "needs_you_today" and not e["looks_suspicious"]]
        suspicious = [e for e in emails if e["looks_suspicious"]]

        st.subheader(f"{len(today)} {'thing needs' if len(today) == 1 else 'things need'} you today")
        for e in today:
            due = f"  ·  **due {e['due']}**" if e.get("due") else ""
            st.markdown(f"- {e['summary']}{due}  \n  <small>{e['from']}</small>", unsafe_allow_html=True)

        if suspicious:
            st.error("Looks like a scam, don't click anything:\n\n" + "\n".join(
                f"- {e['subject']} (from {e['from']})" for e in suspicious))

        st.subheader("Still waiting on")
        if not result["waiting"]:
            st.write("Nobody. Everyone answered.")
        for w in result["waiting"]:
            with st.expander(f"{w['waiting_on']}: {w['days_waiting']} days ({w['subject']})"):
                st.write("Drafted follow-up (copy, edit, and send it yourself):")
                st.code(w["draft"], language=None, wrap_lines=True)

        counts = {b: sum(e["bucket"] == b and not e["looks_suspicious"] for e in emails) for b in ("can_wait", "noise")}
        st.write(f"**Can wait:** {counts['can_wait']} emails  ·  **Noise:** {counts['noise']} emails")

        if result["noise"]:
            st.subheader("Noise report")
            for row in result["noise"]:
                link = f" [Unsubscribe]({row['unsubscribe']})" if row.get("unsubscribe") else ""
                st.markdown(f"- {noise_line(row)}{link}")
            st.caption(savings_line(result["noise"]) + " Each link opens the sender's own unsubscribe page.")

        with st.expander("All sorted emails"):
            st.dataframe(
                [{"bucket": e["bucket"], "summary": e["summary"], "from": e["from"], "due": e.get("due") or ""}
                 for e in emails],
                hide_index=True, use_container_width=True,
            )
        st.caption(f"Run {result['generated']}  ·  models: {result['models']}  ·  {result['cost']}")

# ==========================================
# FAMILY HELP DESK
# ==========================================
with helpdesk_tab:
    if demo:
        sample = load_json(SAMPLE_RUN)
        tickets = sample["tickets"] if sample else []
        st.caption("Made-up requests from the demo run. In live mode, new tickets are saved on your computer.")
    else:
        with st.form("new_ticket", clear_on_submit=True):
            st.subheader("New ticket")
            person = st.selectbox("Who is asking?", list(config.FAMILY))
            text = st.text_area("Paste their message", placeholder="e.g. Got an SMS saying my bank account is blocked...")
            image = st.file_uploader("Screenshot or photo (optional)", type=["png", "jpg", "jpeg", "webp"])
            submitted = st.form_submit_button("Create ticket", type="primary")
        if submitted and text.strip():
            with st.spinner("Sorting the request and drafting a reply..."):
                image_type = {"jpg": "image/jpeg"}.get(image.name.rsplit(".", 1)[-1].lower()) if image else None
                ticket = triage_ticket(
                    person, text,
                    image_bytes=image.getvalue() if image else None,
                    image_type=image_type or (image.type if image else None),
                )
                add_ticket(ticket)
            st.success("Ticket created. Reply to send back:")
            st.code(reply_text(ticket), language=None, wrap_lines=True)
        tickets = load_tickets()

    stats = patterns(tickets)
    col1, col2, col3 = st.columns(3)
    col1.metric("Open tickets", stats["open"])
    col2.metric("Tickets, last 30 days", stats["total"])
    col3.metric("Likely scams caught", sum(t["scam_risk"] == "likely_scam" for t in tickets))

    if stats["repeats"]:
        st.warning("Keeps coming back: " + "; ".join(stats["repeats"]))
    if stats["by_category"]:
        st.bar_chart(stats["by_category"], horizontal=True)

    urgency_order = {"urgent": 0, "normal": 1, "low": 2}
    for ticket in sorted(tickets, key=lambda t: (t["status"] != "open", urgency_order[t["urgency"]])):
        scam = "  ·  ⚠️ likely scam" if ticket["scam_risk"] == "likely_scam" else ""
        label = f"[{ticket['urgency']}] {ticket['person']}: {ticket['summary']}{scam}  ·  {ticket['status']}"
        with st.expander(label):
            st.write(f"**Category:** {CATEGORIES[ticket['category']]}")
            st.write("**Their message:**")
            st.write(ticket["request"])
            st.write("**Reply to send back:**")
            st.code(reply_text(ticket), language=None, wrap_lines=True)
            if not demo and ticket["status"] == "open":
                if st.button("Mark resolved", key=f"resolve_{ticket['id']}"):
                    set_status(ticket["id"], "resolved")
                    st.rerun()

# ==========================================
# HOW IT WORKS
# ==========================================
with how_tab:
    st.markdown(
        """
**Morning digest.** Every morning it reads the last day of email and sorts it like a support
queue: what needs me today, what can wait, and what's noise. It also finds emails I sent that
nobody answered and drafts a follow-up, and it counts which senders I never open.

**Family help desk.** My parents and in-laws send tech questions, often with a screenshot. Each
one becomes a ticket with a category, an urgency, a scam check, and simple step-by-step reply
in their language. The ticket list shows which problems keep coming back.

**Safety.**
- Gmail access is read-only, plus permission to add the digest to my own inbox. It cannot send,
  delete, reply, or unsubscribe.
- Email text is treated as data. Instructions inside an email are ignored.
- The help desk never calls a message safe. Any scam signal puts a warning at the top of the
  reply, and that rule is enforced in code as well as in the prompt.
- Claude's answers are validated against a fixed schema. Emails it skips stay visible.

**Testing.** `evaluate.py` measures sorting accuracy against emails I labeled by hand, and runs
safety cases: real scam patterns must be flagged, normal questions must not be.
"""
    )
