import sqlite3, json, re
from datetime import datetime, timezone

DB = r"C:\Users\rotim\.fieldtheory\bookmarks\bookmarks.db"
SINCE = datetime(2026, 10, 15, tzinfo=timezone.utc)

c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row
rows = c.execute(
    "select tweet_id, url, text, author_handle, posted_at, quoted_tweet_json,"
    " article_title, article_text, links_json from bookmarks"
).fetchall()

WIDE = re.compile(
    r"(hackathons?|scholarships?|fellowships?|grants?|funding round|accelerators?|"
    r"incubators?|residency|open calls?|prizes?|contests?|competitions?|cohorts?|"
    r"applications? (are |is )?(now )?open|applications? close|apply by|deadline|"
    r"awards?|build week|demo day|equity[- ]free|no equity|stipend)",
    re.I,
)

old = {r["id"] for r in json.load(open("hiring/scratch/opps_raw.json", encoding="utf-8"))}
extra = []
for r in rows:
    try:
        d = datetime.strptime(r["posted_at"], "%a %b %d %H:%M:%S %z %Y")
    except Exception:
        continue
    if d < SINCE or r["tweet_id"] in old:
        continue
    if WIDE.search(r["text"] or ""):
        extra.append(r)

print("extra", len(extra))
out = open("hiring/scratch/opps_extra.txt", "w", encoding="utf-8")
for r in extra:
    t = " ".join((r["text"] or "").split())
    out.write(f"{r['tweet_id']} {r['author_handle']} {r['posted_at']}\n    {t[:500]}\n")
    if r["article_title"]:
        out.write("   A: " + r["article_title"] + "\n")
    if r["quoted_tweet_json"]:
        q = json.loads(r["quoted_tweet_json"])
        if isinstance(q, dict) and q.get("text"):
            out.write("   Q: " + " ".join(q["text"].split())[:300] + "\n")
out.close()
print("wrote hiring/scratch/opps_extra.txt")
