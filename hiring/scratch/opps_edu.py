import sqlite3, json, re
from datetime import datetime, timezone

DB = r"C:\Users\rotim\.fieldtheory\bookmarks\bookmarks.db"
SINCE = datetime(2026, 10, 15, tzinfo=timezone.utc)
c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row
recent = []
for r in c.execute("select tweet_id, text, author_handle, posted_at from bookmarks"):
    try:
        d = datetime.strptime(r["posted_at"], "%a %b %d %H:%M:%S %z %Y")
    except Exception:
        continue
    if d >= SINCE:
        recent.append(r)

seen = {r["id"] for r in json.load(open("hiring/scratch/opps_raw.json", encoding="utf-8"))}
PAT = re.compile(
    r"(bootcamp|boot camp|fully funded|fully-funded|training programme|training program|"
    r"free course|scholarship|tuition|mentorship program|mentorship programme|"
    r"certificate program|certificate programme|graduate trainee|graduate program|"
    r"postgraduate|undergraduate|admissions? (are )?open|intake)",
    re.I,
)
hits = [r for r in recent if r["tweet_id"] not in seen and PAT.search(r["text"] or "")]
print("hits", len(hits))
out = open("hiring/scratch/opps_edu.txt", "w", encoding="utf-8")
for r in hits:
    t = " ".join((r["text"] or "").split())
    out.write(f"{r['tweet_id']} @{r['author_handle']} {r['posted_at'][:16]}\n   {t[:300]}\n")
out.close()
