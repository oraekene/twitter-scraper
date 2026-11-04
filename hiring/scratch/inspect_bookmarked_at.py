import sqlite3

DB = r"C:\Users\rotim\.fieldtheory\bookmarks\bookmarks.db"
c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row

print(c.execute("select sql from sqlite_master where type='table' and name='bookmarks'").fetchone()["sql"])
print()
for r in c.execute("select count(*) total, count(bookmarked_at) with_bookmarked_at, count(synced_at) with_synced_at, max(synced_at) max_synced, min(synced_at) min_synced from bookmarks"):
    print(dict(r))
print()
for r in c.execute("select ingested_via, count(*) from bookmarks group by ingested_via"):
    print(dict(r))
print()
for r in c.execute("select ingested_via, count(*) from bookmarks where bookmarked_at is not null group by ingested_via"):
    print(dict(r))
print()
print("sample rows:")
for r in c.execute("select tweet_id, posted_at, bookmarked_at, synced_at, ingested_via from bookmarks limit 5"):
    print(dict(r))