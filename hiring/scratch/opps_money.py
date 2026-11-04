import sqlite3, json, re
from datetime import datetime, timezone

DB = r"C:\Users\rotim\.fieldtheory\bookmarks\bookmarks.db"
SINCE = datetime(2026, 10, 15, tzinfo=timezone.utc)
c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row
rows = c.execute("select tweet_id, text, author_handle, posted_at from bookmarks").fetchall()
recent = []
for r in rows:
    try:
        d = datetime.strptime(r["posted_at"], "%a %b %d %H:%M:%S %z %Y")
    except Exception:
        continue
    if d >= SINCE:
        recent.append(r)

seen = {r["id"] for r in json.load(open("hiring/scratch/opps_raw.json", encoding="utf-8"))}
seen |= {r["tweet_id"] for r in []}

MONEY = re.compile(r"[$£€₦]\s?\d|\d+\s?[kK]\b")
CALL = re.compile(r"\b(apply|applies|submit|enter|open to|deadline|closes|ends|giving away|giveaway|"
                  r"launching a|we will pay|we pay|up to \$|first check|cohort|bounty)\b", re.I)
FOREIGN = re.compile(r"(bourse|beca\b|convocatoria|candidature|appel [aà]|concours|bourses)", re.I)

hits = []
for r in recent:
    t = r["text"] or ""
    if r["tweet_id"] in seen:
        continue
    if (MONEY.search(t) and CALL.search(t)) or FOREIGN.search(t):
        hits.append(r)

print("candidates", len(hits))
out = open("hiring/scratch/opps_money.txt", "w", encoding="utf-8")
for r in hits:
    t = " ".join((r["text"] or "").split())
    out.write(f"{r['tweet_id']} @{r['author_handle']} {r['posted_at'][:16]}\n   {t[:300]}\n")
out.close()
