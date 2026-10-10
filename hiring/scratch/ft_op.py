import json, re, sys, io
from collections import Counter, defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
rows = json.load(open(r'C:\Users\rotim\AppData\Local\Temp\opencode\hiring_core.json', encoding='utf-8'))
op = [r for r in rows if 'opening' in r['buckets']]
print('opening bucket:', len(op))
# quality check
strong_open = re.compile(r"""(
  \bhiring\b | \bwe(?:'re|’re| are)\s+(?:hiring|looking for|recruiting)\b | \bnow hiring\b
| \bjoin (?:our|the|my)\b.{0,25}\bteam\b | \bapply\b.{0,15}\b(?:here|now|today|below|via|dm)
| \bjob (?:opening|post|posting|listing)\b | \bopen(?:ing)?\s+(?:role|position|job)\b
| \bvacanc(?:y|ies)\b | \bseeking\b | \blooking for (?:a|an|someone|talent|engineers|builders|people)
| \bdrop your\b | \bDM me\b | \breply (?:with|below|if)\b | \bwe are (?:growing|building)\b.{0,20}\bteam\b
| \bjoin us\b | \bopen to (?:work|applicants|remote)\b | \bhiring partner(?:s)?\b | \bbackfill\b
)""", re.I | re.X)
s = [r for r in op if strong_open.search(r['text'] or '')]
print('strong openings:', len(s))
print('\nwith comp:', sum(1 for r in s if r['comp']), '| with apply link:', sum(1 for r in s if r['apply']))
print('with roles:', sum(1 for r in s if r['roles']), '| with locs:', sum(1 for r in s if r['locs']))
print('\ncompanies:', Counter(r['company'] for r in s if r['company']).most_common(30))
print('\n--- 12 samples ---')
for r in s[:12]:
    print(f"\n## {r['authorHandle']} | {r['postedAt']} | {r['company']} | roles={r['roles']} | comp={r['comp']} | loc={r['locs']}")
    print((r['text'] or '')[:300].replace('\n', ' | '))
    print('  apply:', r['apply'])
