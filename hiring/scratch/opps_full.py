import sqlite3, json, sys

DB = r"C:\Users\rotim\.fieldtheory\bookmarks\bookmarks.db"
c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row
ids = sys.argv[1:]
out = open("hiring/scratch/opps_full.txt", "w", encoding="utf-8")
for tid in ids:
    r = c.execute(
        "select tweet_id, url, text, author_handle, posted_at, quoted_tweet_json,"
        " article_title, article_text, links_json from bookmarks where tweet_id=?",
        (tid,),
    ).fetchone()
    if not r:
        out.write(f"{tid} NOT FOUND\n")
        continue
    out.write(f"=== {r['tweet_id']} @{r['author_handle']} {r['posted_at']} {r['url']}\n")
    out.write((r["text"] or "") + "\n")
    if r["article_title"]:
        out.write(f"--- ARTICLE: {r['article_title']}\n{(r['article_text'] or '')[:1500]}\n")
    if r["quoted_tweet_json"]:
        q = json.loads(r["quoted_tweet_json"])
        if isinstance(q, dict) and q.get("text"):
            out.write("--- QUOTED @" + str(q.get("authorHandle")) + "\n" + q["text"] + "\n")
    if r["links_json"]:
        out.write("--- LINKS " + str(r["links_json"]) + "\n")
out.close()
print("wrote", len(ids))
