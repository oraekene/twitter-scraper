import sqlite3, json, re
from datetime import datetime, timezone

DB = r"C:\Users\rotim\.fieldtheory\bookmarks\bookmarks.db"
SINCE = datetime(2026, 10, 15, tzinfo=timezone.utc)
KW = re.compile(
    r"(hackathon|scholarship|fellowship|grant|accelerator|incubat|residency|"
    r"apply by|applications (are )?(now )?open|deadline)",
    re.I,
)
c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row
found = set()
try:
    for r in json.load(open("hiring/scratch/opps_raw.json", encoding="utf-8")):
        found.add(r["id"])
except FileNotFoundError:
    pass

hits = []
for r in c.execute(
    "select tweet_id, text, author_handle, posted_at, quoted_tweet_json, article_title from bookmarks"
):
    try:
        d = datetime.strptime(r["posted_at"], "%a %b %d %H:%M:%S %z %Y")
    except Exception:
        continue
    if d < SINCE or r["tweet_id"] in found:
        continue
    blob = (r["article_title"] or "") + " "
    if r["quoted_tweet_json"]:
        try:
            q = json.loads(r["quoted_tweet_json"])
            if isinstance(q, dict):
                blob += q.get("text") or ""
        except Exception:
            pass
    if KW.search(blob):
        hits.append(r)

print("hits", len(hits))
out = open("hiring/scratch/opps_quoted.txt", "w", encoding="utf-8")
for r in hits:
    out.write(f"{r['tweet_id']} @{r['author_handle']} {r['posted_at']}\n")
    out.write("  T: " + " ".join((r["text"] or "").split())[:200] + "\n")
    if r["article_title"]:
        out.write("  A: " + r["article_title"] + "\n")
    out.write("  Q: " + " ".join((json.loads(r["quoted_tweet_json"]).get("text") or "").split())[:300] + "\n")
out.close()
