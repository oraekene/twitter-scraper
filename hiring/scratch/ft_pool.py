import json, re, sys
from collections import Counter

SRC = r'C:\Users\rotim\.fieldtheory\bookmarks\bookmarks.jsonl'
OUT = r'C:\Users\rotim\AppData\Local\Temp\opencode\hiring_pool.json'

PAT = re.compile(r"""(
  \bhiring\b | \bhire\b | \bhires\b | \bhired\b | \bvacanc(?:y|ies)\b | \bjob (?:opening|post|listing|search|board)\b
| \bopen(?:ing)?\s+(?:role|position|job)s?\b | \brecruit(?:er|ing|ment)?\b | \bcandidate(?:s)?\b
| \bapplicant(?:s|ion)?\b | \binterview(?:s|ing|er)?\b | \bonboard(?:ing)?\b | \blayoffs?\b
| \blaid\s+off\b | \breorg(?:ing)?\b | \bheadcount\b | \breferral\b | \bjoin (?:our|the) team\b
| \bwe(?:'re| are) (?:hiring|looking for)\b | \bapply (?:now|here|today)\b | \bjob seeker(?:s)?\b
| \bfull[- ]time\b | \bpart[- ]time\b | \bcontract (?:role|position|work|job)\b | \bstaff engineer\b
| \binternships?\b | \bnow hiring\b | \bworkforce\b | \bhiring manager\b | \bnew hire(?:s)?\b
| \bopen source hiring\b | \bhiring update\b | \bjob fair\b | \bfirst day\b | \boffer letter\b
)""", re.I | re.X)

STRONG = re.compile(r"""(
  \bhiring\b | \bhiring (?:now|update|for)\b | \bwe(?:'re| are) hiring\b | \bnow hiring\b
| \bjob (?:opening|post|listing)\b | \bopen(?:ing)?\s+(?:role|position)s?\b | \bvacanc(?:y|ies)\b
| \bjoin (?:our|the) team\b | \bwe(?:'re| are) looking for\b | \bapply (?:now|here|today)\b
| \brecruit(?:er|ing)\b | \bnew hire(?:s)?\b | \bhiring manager\b | \binterview(?:ing|s|er)\b
| \bonboard(?:ing)?\b | \bjob seeker(?:s)?\b | \binternships?\b | \bfull[- ]time role\b
| \bopen positions?\b | \bhiring for\b | \bbackfill\b | \bheadcount\b | \blaid off\b | \blayoffs?\b
| \breorg\b | \bworkforce reduction\b | \bfirst day\b | \boffer letter\b | \breferral bonus\b
)""", re.I | re.X)

rows = []
total = 0
with open(SRC, encoding='utf-8') as f:
    for line in f:
        total += 1
        if not PAT.search(line):
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        text = d.get('text') or ''
        qt = (d.get('quotedTweet') or {}).get('text') or ''
        hay = text + ' ' + qt
        if not STRONG.search(hay):
            continue
        a = d.get('author') or {}
        rows.append({
            'id': d.get('tweetId') or d.get('id'),
            'url': d.get('url'),
            'text': text,
            'authorHandle': d.get('authorHandle'),
            'authorName': d.get('authorName'),
            'followers': a.get('followerCount'),
            'verified': a.get('isVerified'),
            'location': a.get('location'),
            'bio': (a.get('bio') or '')[:200],
            'postedAt': d.get('postedAt'),
            'bookmarkedAt': d.get('bookmarkedAt'),
            'syncedAt': d.get('syncedAt'),
            'conversationId': d.get('conversationId'),
            'likes': d.get('likeCount'), 'reposts': d.get('repostCount'),
            'replies': d.get('replyCount'), 'quotes': d.get('quoteCount'),
            'views': d.get('viewCount'),
            'lang': d.get('language'),
            'quotedText': qt,
            'quotedAuthor': (d.get('quotedTweet') or {}).get('authorHandle'),
        })

print('lines scanned:', total)
print('strong hits:', len(rows))
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(rows, f, ensure_ascii=False)
print('langs:', Counter(r['lang'] for r in rows).most_common(8))
