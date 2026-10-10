import json, re, sys, io
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
POOL = r'C:\Users\rotim\AppData\Local\Temp\opencode\hiring_pool.json'
rows = json.load(open(POOL, encoding='utf-8'))
none_rows = [r for r in rows if not r['_cats']]
print('none count:', len(none_rows))
for r in sorted(none_rows, key=lambda x: -x['_eng'])[:40]:
    print(f"\n--- {r['authorHandle']} | {r['postedAt']} | L{r['likes']} RT{r['reposts']}")
    print((r['text'] or '')[:350].replace('\n', ' | '))
