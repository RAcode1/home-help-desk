"""
gmail_client.py

Everything that talks to Gmail.

Permissions (OAuth scopes) are kept to the minimum:
- gmail.readonly: read messages
- gmail.insert:   add the morning digest to your own inbox

With these, the app cannot send email to anyone, reply, delete, archive,
change labels, or unsubscribe. Unsubscribe links are only suggested.
"""

import base64
import html
import os
import re
import time
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.utils import parseaddr, parsedate_to_datetime

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.insert",
]
CREDENTIALS_FILE = "credentials.json"  # downloaded from Google Cloud; never commit
TOKEN_FILE = "token.json"              # created after you sign in; never commit
BATCH_SIZE = 25      # Gmail allows about 250 quota units a second; each read costs 5
BATCH_PAUSE = 0.6    # seconds between batches, to stay under that limit
RETRIES = 7          # Gmail rate limits: wait and retry (the client backs off exponentially)


# ==========================================
# SIGN-IN
# ==========================================

def get_service():
    """Sign in (a browser window opens the first time) and return a Gmail client."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:
            creds = None  # token revoked or expired: sign in again

    if not creds or not creds.valid:
        if os.getenv("HHD_NONINTERACTIVE") == "1":
            # Scheduled run: never wait on a browser window nobody will see.
            raise RuntimeError(
                "Gmail sign-in expired (Google does this every 7 days for apps in testing). "
                "Run 'python digest.py' once to sign in again."
            )
        if not os.path.exists(CREDENTIALS_FILE):
            raise FileNotFoundError(
                "credentials.json not found. See 'Connect Gmail' in the README."
            )
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
        creds = flow.run_local_server(port=0)

    with open(TOKEN_FILE, "w") as file:
        file.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def my_address(service):
    return service.users().getProfile(userId="me").execute(num_retries=RETRIES)["emailAddress"]


# ==========================================
# READING MESSAGES
# ==========================================

def _list_ids(service, query, limit):
    ids, page_token = [], None
    while len(ids) < limit:
        response = service.users().messages().list(
            userId="me", q=query, maxResults=min(500, limit - len(ids)), pageToken=page_token
        ).execute(num_retries=RETRIES)
        ids += [m["id"] for m in response.get("messages", [])]
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return ids


def _batch_get(service, make_request, keys):
    """Run many GET requests in small batches; retry failures up to 3 times."""
    results, failed = {}, []

    def callback(request_id, response, exception):
        if exception is None:
            results[request_id] = response
        else:
            failed.append(request_id)

    pending = list(keys)
    for attempt in range(4):
        for start in range(0, len(pending), BATCH_SIZE):
            batch = service.new_batch_http_request(callback=callback)
            for key in pending[start:start + BATCH_SIZE]:
                batch.add(make_request(key), request_id=key)
            batch.execute()
            time.sleep(BATCH_PAUSE)
        if not failed:
            break
        pending, failed = failed, []
        time.sleep(20)  # usually a per-minute rate limit; wait, then retry what failed

    return [results[key] for key in keys if key in results]


def _headers(payload):
    return {h["name"].lower(): h["value"] for h in payload.get("headers", [])}


def _decode(data):
    return base64.urlsafe_b64decode(data.encode()).decode("utf-8", errors="replace")


def _strip_html(text):
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return html.unescape(text)


def _body_text(payload):
    """Plain text of a message: the text/plain part if there is one, else the HTML with tags removed."""
    plain, rich = [], []

    def walk(part):
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if data and mime == "text/plain":
            plain.append(_decode(data))
        elif data and mime == "text/html":
            rich.append(_strip_html(_decode(data)))
        for child in part.get("parts", []) or []:
            walk(child)

    walk(payload)
    text = "\n".join(plain) if plain else "\n".join(rich)
    return re.sub(r"\s+", " ", text).strip()


def _sender_name(from_header):
    name, address = parseaddr(from_header)
    return name or address


def _age_days(date_header):
    try:
        sent = parsedate_to_datetime(date_header)
    except (TypeError, ValueError):
        return 0
    if sent.tzinfo is None:
        sent = sent.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - sent).days


def fetch_inbox(service, query, limit, max_body_chars):
    """Recent inbox emails as simple dicts (only the start of each body)."""
    ids = _list_ids(service, query, limit)
    messages = _batch_get(
        service,
        lambda mid: service.users().messages().get(userId="me", id=mid, format="full"),
        ids,
    )
    emails = []
    for msg in messages:
        head = _headers(msg["payload"])
        emails.append({
            "id": msg["id"],
            "from": head.get("from", ""),
            "subject": head.get("subject", "(no subject)"),
            "date": head.get("date", ""),
            "unread": "UNREAD" in msg.get("labelIds", []),
            "body": _body_text(msg["payload"])[:max_body_chars] or msg.get("snippet", ""),
        })
    return emails


def fetch_waiting(service, me, lookback, wait_days, limit=200):
    """Threads where you sent the last message and nobody has answered for wait_days or more."""
    sent_ids = _list_ids(service, f"in:sent {lookback}", limit)
    sent = _batch_get(
        service,
        lambda mid: service.users().messages().get(
            userId="me", id=mid, format="metadata", metadataHeaders=["Date"]
        ),
        sent_ids,
    )
    thread_ids = list(dict.fromkeys(m["threadId"] for m in sent))
    threads = _batch_get(
        service,
        lambda tid: service.users().threads().get(userId="me", id=tid, format="full"),
        thread_ids,
    )

    waiting = []
    for thread in threads:
        last = thread["messages"][-1]
        head = _headers(last["payload"])
        to = head.get("to", "")
        if "SENT" not in last.get("labelIds", []):
            continue  # someone already answered
        if re.search(r"no-?reply", to, re.I) or me.lower() in to.lower():
            continue  # automated address, or a note to yourself
        days = _age_days(head.get("date", ""))
        if days < wait_days:
            continue
        waiting.append({
            "thread_id": thread["id"],
            "to": to,
            "subject": head.get("subject", "(no subject)"),
            "days_waiting": days,
            "body": _body_text(last["payload"])[:1000],
        })
    return waiting


def fetch_sender_stats(service, query, limit=500):
    """How many emails each sender sent in the query window, and how many are still unread."""
    ids = _list_ids(service, query, limit)
    messages = _batch_get(
        service,
        lambda mid: service.users().messages().get(
            userId="me", id=mid, format="metadata", metadataHeaders=["From", "List-Unsubscribe"]
        ),
        ids,
    )
    stats = {}
    for msg in messages:
        head = _headers(msg["payload"])
        sender = _sender_name(head.get("from", "unknown"))
        row = stats.setdefault(sender, {"sender": sender, "count": 0, "unread": 0, "unsubscribe": ""})
        row["count"] += 1
        row["unread"] += "UNREAD" in msg.get("labelIds", [])
        link = re.search(r"<(https?://[^>]+)>", head.get("list-unsubscribe", ""))
        if link and not row["unsubscribe"]:
            row["unsubscribe"] = link.group(1)
    return sorted(stats.values(), key=lambda row: row["count"], reverse=True)


# ==========================================
# DELIVERING THE DIGEST
# ==========================================

def insert_digest(service, me, subject, html_body):
    """Add the digest to your own inbox. This is not sending: it can only reach your mailbox."""
    message = MIMEText(html_body, "html")
    message["To"] = me
    message["From"] = me
    message["Subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().insert(
        userId="me", body={"raw": raw, "labelIds": ["INBOX", "UNREAD"]}
    ).execute(num_retries=RETRIES)
