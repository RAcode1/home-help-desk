"""
config.py

Settings for Home Help Desk. Edit FAMILY and HELPER_NAME to match your family.
"""

# ==========================================
# CLAUDE MODELS
# ==========================================
# Sorting email runs every morning on dozens of messages, so it can use a
# cheaper model. Family tickets are few, and a missed scam costs more than a
# few cents, so they use the stronger model.
TRIAGE_MODEL = "claude-haiku-5-5"
HELPDESK_MODEL = "claude-opus-5-5"

# Price per million tokens (input, output), used to show what each run cost.
MODEL_PRICING = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}

# ==========================================
# GMAIL
# ==========================================
INBOX_QUERY = 'in:inbox newer_than:1d -subject:"Morning digest"'  # skip yesterday's digest itself
MAX_EMAILS = 150                              # most emails sorted per run (a busy inbox gets ~100 a day)
MAX_BODY_CHARS = 1500                         # only the start of each email goes to Claude (cost and privacy)
WAIT_DAYS = 3                                 # a sent email with no answer after this many days counts as "waiting"
WAIT_LOOKBACK = "newer_than:30d"              # how far back to look for unanswered emails
NOISE_QUERY = "category:promotions newer_than:30d"  # where the noise report counts senders

# ==========================================
# FAMILY HELP DESK
# ==========================================
# Who sends tech questions, and the language their replies should be written in.
FAMILY = {
    "Mom": "English",
    "Dad": "English",
    "Mother-in-law": "English",
    "Father-in-law": "English",
}

# How replies refer to you, e.g. "Check with me first."
HELPER_NAME = "me"
