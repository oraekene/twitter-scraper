import sqlite3, json

c = sqlite3.connect(r'C:\Users\rotim\.fieldtheory\bookmarks\bookmarks.db')
tabs = [r[0] for r in c.execute("select name from sqlite_master where type in ('table','view')")]
print('TABLES:', tabs)
for t in tabs:
    cols = [r[1] for r in c.execute(f'PRAGMA table_info({t})')]
    n = c.execute(f'select count(*) from {t}').fetchone()[0]
    print(f'\n== {t} ({n} rows) ==')
    print('  ', cols)
row = c.execute('select * from bookmarks limit 1').fetchone()
print('\nSAMPLE:', json.dumps(dict(zip([d[0] for d in c.execute('select * from bookmarks limit 1').description], row)), default=str)[:2000])
