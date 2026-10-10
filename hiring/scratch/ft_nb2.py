import json, re, sys, io
from collections import Counter, defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
rows = json.load(open(r'C:\Users\rotim\AppData\Local\Temp\opencode\hiring_core.json', encoding='utf-8'))
nb = [r for r in rows if not r['buckets']]
print('no-bucket:', len(nb))
for r in nb:
    print(f"\n--- {r['authorHandle']} | {r['postedAt']}")
    print((r['text'] or '')[:260].replace('\n', ' | '))
