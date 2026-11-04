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

seen = {r["id"] for r in json.load(open("hiring/scratch/opps_raw.json", encoding="utf-8"))}
TOKENS = {
    "fellowship": r"fellow", "accelerator": r"accelerat", "prize": r"prize|award|purse",
    "competition": r"competit|contest", "hack": r"\bhack(s|ed|ing)?\b",
    "closes": r"clos(e|es|ing)", "submit": r"submi(t|ssion|ssions)", "register": r"regist|sign ?up",
    "opennow": r"now open|open now|applications? (are )?open", "tuition": r"tuition|fees",
    "admission": r"admission|enrol", "internship": r"internship", "program": r"program|programme",
    "challenge": r"challenge", "demo": r"demo day|pitch", "residency": r"residen",
    "capital": r"capital", "credits": r"credits", "perks": r"perks|benefits",
    "bounty": r"bount", "scholarship": r"scholarship|bursary",
}

rows_out = {}
for name, pat in TOKENS.items():
    rx = re.compile(pat, re.I)
    for r in recent:
        if r["tweet_id"] in seen:
            continue
        if rx.search(r["text"] or ""):
            rows_out.setdefault(r["tweet_id"], [r, []])[1].append(name)

out = open("hiring/scratch/opps_gap.txt", "w", encoding="utf-8")
for tid, (r, tags) in rows_out.items():
    t = " ".join((r["text"] or "").split())
    out.write(f"{tid} @{r['author_handle']} {r['posted_at'][:16]} [{','.join(tags)}]\n   {t[:260]}\n")
    if r["article_title"]:
        out.write("   A: " + r["article_title"] + "\n")
out.close()
print("union new hits", len(rows_out))

short = [r for r in recent if len((r["text"] or "").strip()) < 90 and (r["media_count"] or 0) > 0]
out = open("hiring/scratch/opps_images.txt", "w", encoding="utf-8")
for r in short:
    t = " ".join((r["text"] or "").split())
    out.write(f"{r['tweet_id']} @{r['author_handle']} {r['posted_at'][:16]}\n   {t}\n")
out.close()
print("short media", len(short))
