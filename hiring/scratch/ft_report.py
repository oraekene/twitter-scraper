import json, re, os, sys, io
from collections import Counter
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
SRC = r'C:\Users\rotim\.fieldtheory\bookmarks\bookmarks.jsonl'
IN = r'C:\Users\rotim\AppData\Local\Temp\opencode\hiring_final.json'
OUT = r'C:\Users\rotim\Documents\twitter scraper\out\hiring_bookmarks.md'
rows = json.load(open(IN, encoding='utf-8'))

NOW = datetime(2026, 10, 9, tzinfo=timezone.utc)
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

def pdt(s):
    if not s: return None
    try: return datetime.strptime(s, '%a %b %d %H:%M:%S %z %Y')
    except Exception: return None

def norm(s): return re.sub(r'\s+', ' ', s or '').strip()
def eng(r): return (r['likes'] or 0) + 2*(r['reposts'] or 0) + (r['replies'] or 0)

for r in rows:
    r['_dt'] = pdt(r['postedAt'])
    r['_eng'] = eng(r)

def age(r):
    return f"{(NOW - r['_dt'].astimezone(timezone.utc)).days}d" if r['_dt'] else '?'

def snip(t, n=280):
    t = norm(t)
    return t if len(t) <= n else t[:n-1].rstrip() + '...'

L = []
A = L.append
c = Counter(r['_p'] for r in rows)
openings = [r for r in rows if r['_p'] in ('opening', 'opening_weak')]

A('# Hiring and job openings in your bookmarks')
A('')
A('Source: `C:\\Users\\rotim\\.fieldtheory\\bookmarks\\bookmarks.jsonl`, all 94,415 bookmarks.')
A(f'Matched **{len(rows)}** tweets on hiring, job openings, job hunting, layoffs, or recruiting.')
A('')
A('| Group | Tweets |')
A('|---|---|')
A(f'| Someone posting an opening | {c["opening"] + c["opening_weak"]} |')
A(f'| How to apply, interview, and negotiate | {c["advice"]} |')
A(f'| Layoffs, reorgs, headcount cuts | {c["layoff"]} |')
A(f'| Roundups and job boards | {c["list"]} |')
A(f'| Hiring market and process craft | {c["craft"]} |')
A(f'| Other employment talk | {c["other"] + c["misc"]} |')
A('')

def block(rs, title, note=None, n=400):
    A(f'## {title}')
    A('')
    if note: A(note); A('')
    for r in rs[:n]:
        bits = []
        if r['roles']: bits.append('roles: ' + ', '.join(r['roles'][:4]))
        if r['comp']: bits.append('pay: ' + ' '.join(r['comp'][:3]))
        if r['locs']: bits.append('loc: ' + ', '.join(r['locs'][:3]))
        if r['apply']: bits.append('link: ' + r['apply'][:60])
        meta = ' | '.join(bits)
        head = f'- **@{r["authorHandle"]}** {age(r)}'
        if r['verified']: head += ' verified'
        if r['followers']: head += f' ({r["followers"]:,} followers)'
        A(head + (f' — {meta}' if meta else ''))
        A(f'  {snip(r["text"])}')
        A(f'  <{r["url"]}>')
    if len(rs) > n: A(f'- ... and {len(rs) - n} more')
    A('')

bydate = lambda r: (r['_dt'] or EPOCH)
recent = [r for r in sorted(openings, key=bydate, reverse=True) if r['_dt'] and (NOW - r['_dt'].astimezone(timezone.utc)).days <= 150]
older = [r for r in sorted(openings, key=bydate, reverse=True) if r not in recent]
block(recent, 'Openings posted in the last 5 months', f'{len(recent)} tweets, newest first.')
block(older, 'Older openings', f'{len(older)} tweets, newest first.')

block(sorted([r for r in rows if r['_p'] == 'list'], key=bydate, reverse=True), 'Roundups, job boards, hiring signals')
block(sorted([r for r in rows if r['_p'] == 'advice'], key=lambda r: -r['_eng']), 'How to apply, interview, and negotiate', 'Highest engagement first.')
block(sorted([r for r in rows if r['_p'] == 'craft'], key=lambda r: -r['_eng']), 'Hiring market and process craft', 'Highest engagement first.')
block(sorted([r for r in rows if r['_p'] == 'layoff'], key=bydate, reverse=True), 'Layoffs, reorgs, headcount cuts')
block(sorted([r for r in rows if r['_p'] in ('other', 'misc')], key=lambda r: -r['_eng']), 'Other employment talk', 'Highest engagement first.')

A('---')
A('')
A('## Accounts posting the most openings')
A('')
A(', '.join(f'@{k} ({v})' for k, v in Counter(r['authorHandle'] for r in openings).most_common(30)))
A('')
A('## Roles most often mentioned in openings')
A('')
A(', '.join(f'{k} ({v})' for k, v in Counter(x for r in openings for x in r['roles']).most_common(40)))
A('')
A('## Openings that state pay')
A('')
for r in sorted([r for r in openings if r['comp']], key=bydate, reverse=True):
    A(f'- @{r["authorHandle"]} {age(r)}: {" ".join(r["comp"][:3])} — {snip(r["text"], 140)}')
    A(f'  <{r["url"]}>')
A('')

os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, 'w', encoding='utf-8').write('\n'.join(L))
print('wrote', OUT)
print(dict(c))
print('openings recent/older:', len(recent), len(older))
