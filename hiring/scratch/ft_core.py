import json, re, sys, io
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
rows = json.load(open(r'C:\Users\rotim\AppData\Local\Temp\opencode\hiring_all.json', encoding='utf-8'))
src = r'C:\Users\rotim\.fieldtheory\bookmarks\bookmarks.jsonl'

# core = unambiguous hiring/employment vocabulary
CORE = re.compile(r"""(
  \bhiring\b | \bwe(?:'re|’re| are)\s+(?:hiring|looking for|recruiting)\b | \bnow hiring\b
| \bvacanc(?:y|ies)\b | \bjob (?:opening|post|posting|listing|listings|board|fair|search)\b
| \bopen(?:ing)?\s+(?:role|roles|position|positions|job|jobs|positions?)\b
| \bjoin (?:our|the|my)\b.{0,25}\bteam\b | \bapply (?:now|here|today|below|via)\b
| \brecruit(?:er|ers|ing|ment)\b | \bnew hire(?:s)?\b | \bheadcount\b | \bfirst day\b
| \bjob seeker(?:s)?\b | \bjob hunt(?:er|ing)?\b | \bjob search(?:ing)?\b | \blooking for work\b
| \blayoffs?\b | \blaid off\b | \blaying off\b | \bworkforce reduction\b | \bjob cuts?\b
| \bunemploy(?:ed|ment)\b | \boffer letter\b | \breferral bonus\b | \bghost(?:ed|ing)\b
| \bhiring (?:process|manager|freeze|wave|boom|trend|tip|season)\b | \bwho(?:'s| is) hiring\b
| \bhiring partner(?:s)?\b | \bopen to (?:work|applicants|remote)\b | \bbackfill\b
| \binterview(?:ed|ing|s)?\s+(?:at|with|for)\b | \bwork visa\b | \bblue card\b | \bH-?1B\b
| \bsalary (?:range|band|negotiation|transparency)\b | \bcomp (?:range|band|benchmark)\b
| \binterview (?:loop|process|red flag|question|tip)\b | \brecruiter (?:said|told|call)\b
| \bjob application(?:s)?\b | \bjob description\b | \bjds?\b.{0,12}\brole\b
)""", re.I | re.X)

keep = []
for line in open(src, encoding='utf-8'):
    if not CORE.search(line):
        continue
    try:
        d = json.loads(line)
    except Exception:
        continue
    t = d.get('text') or ''
    if CORE.search(t):
        keep.append(d.get('tweetId') or d.get('id'))

ids = set(keep)
rows = [r for r in rows if r['id'] in ids]
# rows we lost by the earlier line-level gate but that match core on text
print('core-matching ids:', len(ids), '| in loaded pool:', len(rows))

# keep only rows whose OWN text matches core (quoted-only matches are quote-tweets)
final = [r for r in rows if CORE.search(r['text'] or '')]
lost = len(rows) - len(final)
print('own-text core:', len(final), '| quote-only dropped:', lost)
print('buckets:', Counter(b for r in final for b in r['buckets']).most_common())
print('no bucket:', sum(1 for r in final if not r['buckets']))
json.dump(final, open(r'C:\Users\rotim\AppData\Local\Temp\opencode\hiring_core.json', 'w', encoding='utf-8'), ensure_ascii=False)
