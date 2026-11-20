"""
noise.py

The noise report: senders who email you the most and get opened the least.
Plain counting, no AI needed.
"""

MIN_EMAILS = 5  # ignore senders with only a few emails


def noise_report(sender_stats, top=3):
    """Pick the loudest senders you (almost) never open."""
    rows = []
    for row in sender_stats:
        opened = row["count"] - row["unread"]
        if row["count"] >= MIN_EMAILS and opened / row["count"] <= 0.1:
            rows.append({**row, "opened": opened})
    rows.sort(key=lambda r: r["count"], reverse=True)
    return rows[:top]


def noise_line(row):
    opened = "none" if row["opened"] == 0 else str(row["opened"])
    return f"{row['sender']} sent you {row['count']} emails this month. You opened {opened}."
