import os, re, sqlite3, json
from datetime import datetime, timezone

LIB = r"C:\Users\rotim\.fieldtheory\library\bookmarks"
DB = r"C:\Users\rotim\.fieldtheory\bookmarks\bookmarks.db"
CUTOFF = datetime(2026, 10, 29).timestamp()  # files created by the last sync's export

ids = []
for f in os.listdir(LIB):
    p = os.path.join(LIB, f)
    if os.stat(p).st_ctime < CUTOFF:
        continue
    with open(p, encoding="utf-8") as fh:
        head = fh.read(600)
    m = re.search(r'^tweet_id: "?(\d+)"?', head, re.M)
    if m:
        ids.append(m.group(1))

print("md files created on 29 Oct:", len(ids))

c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row
q = ",".join("?" * len(ids))
rows = c.execute(
    f"select tweet_id, text, author_handle, posted_at from bookmarks where tweet_id in ({q})", ids
).fetchall()
print("matched in db:", len(rows))

old = []
for r in rows:
    d = datetime.strptime(r["posted_at"], "%a %b %d %H:%M:%S %z %Y")
    if d < datetime(2026, 10, 15, tzinfo=timezone.utc):
        old.append(r)
print("posted before 15 Oct (extra pool):", len(old))

json.dump([dict(r) for r in old], open("hiring/scratch/recent_old.json", "w", encoding="utf-8"), indent=1)
