import sqlite3, json, re, sys
from collections import Counter

DB = r'C:\Users\rotim\.fieldtheory\bookmarks\bookmarks.db'
c = sqlite3.connect(DB)

# FTS5 bare terms only (no regex). Count each individually.
TERMS = ['hiring', 'hire', 'vacanc*', 'opening', 'recruit*', 'candidate', 'applicant*',
         'interview', 'onboard*', 'layoff', 'reorg', 'headcount', 'intern', 'internship',
         'referral', 'offer', 'salary', 'resume', 'relocat*', 'workforce', 'team',
         'role', 'position', 'apply', 'application', 'deadline', 'engineer', 'founder',
         'remote', 'visa', 'fellowship', 'bootcamp', 'talent', 'compensation']

print('== term counts (fts) ==')
for t in TERMS:
    try:
        n = c.execute("select count(*) from bookmarks_fts where bookmarks_fts match ?", (t,)).fetchone()[0]
    except Exception as e:
        n = f'ERR {e}'
    print(f'{t:15} {n}')

BROAD = 'hiring OR hire OR vacanc* OR recruit* OR candidate OR applicant* OR interview OR onboard* OR layoff OR reorg OR headcount OR referral OR "job opening" OR "open role" OR "we are hiring" OR "join our team"'
n = c.execute("select count(*) from bookmarks_fts where bookmarks_fts match ?", (BROAD,)).fetchone()[0]
print('\nBROAD candidate pool:', n)
