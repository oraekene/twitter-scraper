import sqlite3, json, re
from datetime import datetime, timezone

DB = r"C:\Users\rotim\.fieldtheory\bookmarks\bookmarks.db"
SINCE = datetime(2026, 10, 15, tzinfo=timezone.utc)
c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row
rows = c.execute(
    "select tweet_id, text, author_handle, posted_at, media_count, link_count,"
    " quoted_tweet_json, article_title, article_text from bookmarks"
).fetchall()

recent = []
for r in rows:
    try:
        d = datetime.strptime(r["posted_at"], "%a %b %d %H:%M:%S %z %Y")
    except Exception:
        continue
    if d >= SINCE:
        recent.append(r)

TOKENS = {
    "hackathon": r"hackathon", "hack": r"\bhack(s|ed|ing)?\b", "buildathon": r"build.?athon",
    "scholarship": r"scholarship|bursary", "fellowship": r"fellow", "grant": r"grant",
    "fund": r"fund", "capital": r"capital", "stipend": r"stipend",
    "accelerator": r"accelerat", "incubator": r"incubat", "residency": r"residen",
    "cohort": r"cohort", "prize": r"prize|award|purse", "competition": r"competit|contest",
    "bounty": r"bount", "apply": r"appl(y|ication|ications|ying)", "deadline": r"deadline",
    "closes": r"clos(e|es|ing)", "register": r"regist|sign ?up", "submit": r"submi(t|ssion|ssions)",
    "program": r"program|programme", "opennow": r"now open|open now|applications? (are )?open",
    "credits": r"credits", "perks": r"perks|benefits", "tuition": r"tuition|fees",
    "money": r"[$£€₦]\s?\d|\d+\s?[kK]\b|million", "free": r"\bfree\b",
    "nominate": r"nominat", "challenge": r"challenge", "demo": r"demo day|pitch",
    "admission": r"admission|enrol", "internship": r"internship", "visa": r"visa|relocat",
}

used_before = set()
for r in json.load(open("hiring/scratch/opps_raw.json", encoding="utf-8")):
    used_before.add(r["id"])

print("recent", len(recent))
for name, pat in TOKENS.items():
    rx = re.compile(pat, re.I)
    hit = [r for r in recent if rx.search(r["text"] or "")]
    new = [r for r in hit if r["tweet_id"] not in used_before]
    print(f"{name:12s} all={len(hit):4d}  new={len(new):4d}")

short = [r for r in recent if len((r["text"] or "").strip()) < 90]
print("short text (<90 chars):", len(short))
short_media = [r for r in short if (r["media_count"] or 0) > 0]
print("short with image/video:", len(short_media))
