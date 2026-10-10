import json, re, sys, io, random
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
rows = json.load(open(r'C:\Users\rotim\AppData\Local\Temp\opencode\hiring_all.json', encoding='utf-8'))
nb = [r for r in rows if not r['buckets']]
print('no-bucket:', len(nb))
random.seed(7)
for r in random.sample(nb, 30):
    print(f"\n--- {r['authorHandle']} | {r['postedAt']}")
    print((r['text'] or '')[:220].replace('\n', ' | '))
