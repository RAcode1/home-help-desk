# Home Help Desk

> I'm my family's unpaid IT department, so I built myself a help desk.

A small Python app on the Claude API that runs my inbox and my family's tech questions like a
support queue. Built with Claude Code.

## What it does

**Morning digest.** Every morning it reads the last day of email and puts one short summary in my
inbox:

- **Needs you today:** bills, forms, appointment confirmations, questions waiting on me
- **Still waiting on:** emails I sent that nobody answered after 3 days, with a polite follow-up
  drafted for me to send
- **Noise report:** the senders I never open ("Brightmart sent you 41 emails this month. You
  opened none.")
- **Looks like a scam:** phishing is pulled out of the list with a warning

**Family help desk.** My parents and in-laws live on the other side of the world and send me tech
questions on WhatsApp, often with a screenshot. I paste each one in and it becomes a ticket:

- a category (Wi-Fi, phone, apps, scam, payments, TV) and an urgency
- a scam check
- a simple step-by-step reply in their language, ready to send back
- patterns over time, so I can see what keeps coming back and teach the fix once

## Why I built it

During my job search my inbox got out of hand: hundreds of unread emails, with the few that
mattered (a form due tomorrow, a recruiter waiting on interview times) buried under sales emails.

At the same time, I'm the person my family calls when the Wi-Fi light turns red or a text says
their bank account is blocked. At my last job I tracked and categorized customer tickets so the
test team could see where problems clustered. Family tech support has the same shape, so I built
the same habit into a tool.

## How it works

```
Gmail API (read-only) ──> fetch the last day of email ──> Claude sorts it ──┐
                      ──> sent emails with no answer  ──> Claude drafts ────┼──> digest added to my inbox
                      ──> promotions by sender        ──> counted (no AI) ──┘
WhatsApp message + screenshot ──> Claude (with vision) ──> ticket + reply ──> local ticket list
```

| File | Job |
| --- | --- |
| `digest.py` | Builds the morning digest; `--deliver` adds it to your inbox |
| `triage.py` | Sorts email, finds unanswered emails, drafts follow-ups |
| `noise.py` | The noise report (plain counting) |
| `helpdesk.py` | Family tickets: sorting, scam check, replies, patterns |
| `gmail_client.py` | Gmail sign-in and reads |
| `llm.py` | Claude calls with structured output, refusal handling, cost tracking |
| `evaluate.py`, `label.py` | Accuracy and safety testing |
| `app.py` | Streamlit app, with a demo mode that needs no sign-in |

## Safety and privacy

- **Least access.** Gmail permissions are read-only plus "insert", which can only add a message to
  my own inbox. The app cannot send email, reply, delete, change labels, or unsubscribe.
  Unsubscribe links are suggestions.
- **Email is data.** Prompts tell Claude to ignore instructions written inside emails and
  messages, so a phishing email can't steer the tool.
- **Never "safe".** The help desk never tells anyone a message is safe. Any scam signal puts a
  warning at the top of the reply, and that rule is enforced in code (`enforce_safety`), not only
  in the prompt.
- **Validated output.** Claude answers in a fixed JSON schema, checked with Pydantic. Every email
  must come back exactly once; anything Claude skips stays visible instead of disappearing.
- **Little leaves the computer.** Only the first 1,500 characters of each email are sent to
  Claude. Tickets and results stay in `data/`, which is never committed.
- **Cost is tracked** on every run.

## Testing

```
python label.py 40                          # label 40 of your own emails by hand
python evaluate.py triage data/labeled.json # how often it sorts them the way you would
python evaluate.py helpdesk                 # scam patterns must be flagged; normal questions must not
```

The safety cases in `demo/helpdesk_cases.json` cover the scams my family actually gets: fake bank
calls asking for an OTP, "install AnyDesk for your refund", KYC and electricity cut-off texts,
parcel fees, prize messages, and fake police calls.

## Run it yourself

1. Install Python 3.13, then:
   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. **Demo, no sign-in needed:** `streamlit run app.py`
3. **Your own inbox:** copy `.env.example` to `.env` and add your Anthropic API key. Then connect
   Gmail (below) and run `python digest.py`, or `python digest.py --deliver` to add the digest to
   your inbox.
4. **Every morning:** schedule `run_digest.bat` in Windows Task Scheduler:
   ```
   schtasks /create /tn "Morning digest" /tr "C:\path\to\home-help-desk\run_digest.bat" /sc daily /st 07:00
   ```

### Connect Gmail

1. In [Google Cloud Console](https://console.cloud.google.com/), create a project and enable the
   **Gmail API**.
2. Set up the OAuth consent screen (External) and add yourself as a test user.
3. Create an OAuth client of type **Desktop app**, download the JSON, and save it in this folder
   as `credentials.json`.
4. The first run opens a browser to sign in. A `token.json` is saved so later runs don't ask.

`credentials.json`, `token.json` and `.env` are in `.gitignore` and never committed.
