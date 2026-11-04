import sqlite3, json, re
from datetime import datetime, timezone

DB = r"C:\Users\rotim\.fieldtheory\bookmarks\bookmarks.db"
SINCE = datetime(2026, 10, 15, tzinfo=timezone.utc)

c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row
rows = c.execute(
    "select tweet_id, url, text, author_handle, posted_at, like_count, repost_count,"
    " quoted_tweet_json, article_title, article_text, links_json"
    " from bookmarks"
).fetchall()

def ts(s):
    return datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y")

recent = []
for r in rows:
    try:
        d = ts(r["posted_at"])
    except Exception:
        continue
    if d >= SINCE:
        recent.append((d, r))

print("total", len(rows), "since 15 Oct", len(recent))

TOPIC = re.compile(
    r"(hackathons?|hack ?sprints?|build ?athons?|scholarships?|fellowships?|grants?|"
    r"funding|fund(ed|s)?|accelerators?|incubators?|residency|cohort|prizes?|"
    r"competitions?|bount(y|ies)|stipends?|tuition|applications?|apply|deadline|"
    r"submissions?|demo day)",
    re.I,
)
hits = [(d, r, {m.group(0).lower() for m in TOPIC.finditer((r["text"] or ""))}) for d, r in recent]
hits = [h for h in hits if h[2]]
print("topic hits", len(hits))
json.dump(
    [
        {
            "date": str(d.date()),
            "handle": r["author_handle"],
            "id": r["tweet_id"],
            "url": r["url"],
            "text": r["text"],
            "hits": sorted(h),
            "links": json.loads(r["links_json"] or "[]"),
            "article_title": r["article_title"],
            "quoted": (json.loads(r["quoted_tweet_json"] or "{}") or {}).get("text") if r["quoted_tweet_json"] else None,
        }
        for d, r, h in hits
    ],
    open("hiring/scratch/opps_raw.json", "w", encoding="utf-8"),
    indent=1,
    ensure_ascii=False,
)
print("wrote hiring/scratch/opps_raw.json")
