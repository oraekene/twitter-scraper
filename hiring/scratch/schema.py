import sqlite3, sys

DB = r"C:\Users\rotim\.fieldtheory\bookmarks\bookmarks.db"
c = sqlite3.connect(DB)
print([r[0] for r in c.execute("select name from sqlite_master where type in ('table','view')")])
print([d[1] for d in c.execute("PRAGMA table_info(bookmarks)")])
print("rows", c.execute("select count(*) from bookmarks").fetchone())
print("newest", c.execute("select max(posted_at), max(bookmarked_at) from bookmarks").fetchone())
for q in sys.argv[1:]:
    print(q, c.execute(q).fetchall())
