import json, re, sys, io, os
from collections import Counter, defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
SRC = r'C:\Users\rotim\.fieldtheory\bookmarks\bookmarks.jsonl'
OUT_JSON = r'C:\Users\rotim\AppData\Local\Temp\opencode\hiring_all.json'
OUT_MD = r'C:\Users\rotim\AppData\Local\Temp\opencode\hiring_report.md'

# ---------- RECALL: anything that could plausibly be about hiring or openings ----------
RECALL = re.compile(r"""(
  \bhiring\b | \bhire\b | \bhires\b | \bhired\b | \bhiring\b | \bvacanc(?:y|ies)\b
| \bjob[s]?\s+(?:opening|post|posting|listing|listings|search|board|fair|market)\b
| \bopen(?:ing)?\s+(?:role|roles|position|positions|job|jobs)\b
| \bwe(?:'re|’re| are| r)\s+(?:hiring|looking for|recruiting)\b
| \bnow hiring\b | \bwe are (?:looking|hiring)\b | \bjoin (?:our|the|my)\b.{0,20}\bteam\b
| \bapply (?:now|here|today|below|via)\b | \brecruit(?:er|ers|ing|ment)\b
| \bcandidate(?:s)?\b | \bapplicant(?:s|ion|ions)?\b | \binterview(?:s|ing|er|ers)?\b
| \bonboard(?:ing|ed)?\b | \blayoffs?\b | \blaid off\b | \blaying off\b | \blay off\b
| \bre-?org(?:ing|anisation|anization)?\b | \bheadcount\b | \bworkforce\b
| \bnew hire(?:s)?\b | \bfirst day\b | \boffer letter\b | \breferral\b
| \bjob seeker(?:s)?\b | \bjob hunt(?:ing|er)?\b | \bjob hunting\b | \bunemploy(?:ed|ment)\b
| \bcareer(?:s)?\b | \bful[- ]?time\b | \bpart[- ]time\b | \bfreelance\b
| \binternships?\b | \bintern\b | \bwork visa\b | \bblue card\b | \bH-?1B\b
| \bcomp(?:ensation)?\b.{0,20}\b(?:range|band|benchmark)\b | \bsalary\b | \bpay range\b
| \btalent\b | \bbootcamp\b | \bfellowships?\b | \bresume(?:s)?\b | \bcurriculum vitae\b
| \bLinkedIn\b.{0,40}\b(?:job|role|hiring)\b | \bghcr\b.{0,10}\bhire\b
| \bwho(?:'s| is) hiring\b | \btalent team\b | \bpeople team\b | \bHR team\b
| \bghost(?:ed|ing)\b | \brejection\b | \bjob description\b | \bJD\b.{0,10}\brole\b
)""", re.I | re.X)

# ---------- PRECISION signals ----------
OPEN_CTA = re.compile(r"""(
  \bhiring\b | \bwe(?:'re|’re| are)\s+(?:hiring|looking for|recruiting)\b | \bnow hiring\b
| \bjoin (?:our|the|my)\b.{0,20}\bteam\b | \bapply\b.{0,15}\b(?:here|now|today|below|via|dm)
| \bjob (?:opening|post|posting|listing)\b | \bopen(?:ing)?\s+(?:role|position|job)\b
| \bvacanc(?:y|ies)\b | \bseeking\b | \blooking for (?:a|an|someone|talent|someone who|engineers|builders)
| \bdrop your\b | \bDM me\b.{0,30}\b(?:apply|interest|hiring|role) | \breply (?:with|below|if)\b
| \bwe are (?:growing|looking|building)\b.{0,20}\bteam\b | \bjoin us\b
| \bbackfill\b | \bopen to (?:work|applicants|remote)\b | \bseats?\b.{0,10}\b(?:open|limited)\b
)""", re.I | re.X)

COMPANY = re.compile(r"(?:@[A-Za-z0-9_]{2,20})")
LEVER = re.compile(r"\b([A-Z][\w&.\- ]{1,24})\b\s*(?:is\s*)?(?:#hiring|is\s+hiring)\b")
TITLE_WORDS = r"""(?:software|frontend|front-end|backend|back-end|full[- ]?stack|fullstack|mobile|ios|android|
web|devops|sre|platform|infra(?:structure)?|data|ml|machine learning|ai|llm|agentic|product|design|designer|ux|ui|
marketing|growth|sales|account executive|ae|customer success|customer support|support|operations|ops|finance|
financial|accounting|legal|content|community|research|scientist|research engineer|qa|test|security|compliance|
engineering|engineer|program manager|product manager|project manager|recruiter|people|apprentice|intern)"""
ROLE = re.compile(rf"\b((?:senior|sr\.?|staff|principal|junior|jr\.?|lead|head of|principal|associate|contract|freelance|entry[- ]level|mid[- ]level|graduate|new grad|first[- ]time)?\s*{TITLE_WORDS}(?:\s+(?:engineer|engineering|developer|designer|scientist|manager|recruiter|lead|architect|specialist|analyst|marketer|writer))?)\b", re.I)
COMP = re.compile(r"[$€£]\s?[\d][\d,\.]*\s?(?:k|K|m|M)?(?:\s*[-–to]+\s*[$€£]?\s?[\d][\d,\.]*\s?(?:k|K|m|M)?)?(?:\s*(?:\+\s*)?(?:per|\/)\s*(?:a\s*)?(?:year|yr|mo|month|week|day|hour|hr))?")
PERIOD = re.compile(r"(?:[$€£]\s?[\d][\d,\.]*\s?[kKmM]?\s*(?:/|per|a)\s*(?:year|yr|month|mo|week|day|hour|hr))", re.I)
LOC = re.compile(r"\b(remote[- ]?(?:first|only)?|hybrid|on[- ]?site|in[- ]?person|SF|San Francisco|NYC|New York|Los Angeles|Austin|Boston|Seattle|Chicago|London|Dublin|Berlin|Paris|Toronto|Vancouver|Amsterdam|Lisbon|Nigeria|Lagos)\b")
APPLY = re.compile(r"(?:https?://)?(?:[a-z0-9.\-]+\.)*(?:lever\.co|greenhouse\.io|ashbyhq\.com|workable\.com|breezy\.hr|smartrecruiters\.com|jobvite\.com|hotfix\.jobs|jobs\.lever|apply\.com|wellfound\.com|workatastartup\.com|linkedin\.com/jobs|indeed\.com|ziprecruiter\.com|notion\.so|careers?)[^\s<>\"')]*", re.I)
JOBLINK = re.compile(r"(?:lever\.co|greenhouse\.io|ashbyhq\.com|workable\.com|breezy\.hr|smartrecruiters|jobvite|hotfix\.jobs|careers?/|/jobs?/|jobs\.[a-z]|\bjobs\b|apply now|\bapply\b|greenhouse)", re.I)

LAYOFF = re.compile(r"\b(layoffs?|laid off|laying off|lay off|workforce reduction|job cuts?|downsizing|re-?org(?:ing)?|headcount reduction|redundan(?:cy|cies)|mass layoff)\b", re.I)
TALK = re.compile(r"\b(interview|hiring manager|candidate|resume|cv\b|portfolio|referral|screening|assessment|offer letter|salary|compensation|equity|onboarding|hiring process|ghosted|rejection|job hunt|job search|networking|referrals|ats\b|recruiter|talent acquisition|how to (?:get|land)|tips? for (?:hiring|getting)|hiring (?:process|tips|trends|boom|freeze|wave))\b", re.I)
RESOURCES = re.compile(r"\b(job board|job boards|where to (?:find|look)|resources to find|list of (?:hiring|jobs|companies)|hn \"who'?s hiring\"|lenny'?s jobs|breakout list|fonzi\.ai|find startups hiring|ditch linkedin)\b", re.I)

MONEY = re.compile(r"[$€£]\s?[\d]")

rows, seen = [], set()
nlines = 0
with open(SRC, encoding='utf-8') as f:
    for line in f:
        nlines += 1
        if not RECALL.search(line):
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        tid = d.get('tweetId') or d.get('id')
        if tid in seen:
            continue
        seen.add(tid)
        text = (d.get('text') or '').strip()
        q = d.get('quotedTweet') or {}
        qtext = (q.get('text') or '').strip()
        hay = text + '\n' + qtext
        a = d.get('author') or {}
        url = d.get('url') or ''

        buckets = []
        if OPEN_CTA.search(text) or (OPEN_CTA.search(qtext) and q.get('authorHandle')):
            buckets.append('opening')
        if LAYOFF.search(hay):
            buckets.append('layoff')
        if RESOURCES.search(hay):
            buckets.append('resources')
        if TALK.search(hay):
            buckets.append('talk')

        roles = []
        for m in ROLE.finditer(text):
            v = re.sub(r'\s+', ' ', m.group(1)).strip()
            if 4 <= len(v) <= 40 and v.lower() not in roles:
                roles.append(v.lower())
        # "hiring N <role>" and "hiring <role>"
        h = re.search(rf"\bhiring\s+(?:(\d+|a|an|two|three|several)\s+)?((?:[A-Za-z]+\s+){{0,3}}?{TITLE_WORDS}(?:\s+(?:engineer|engineering|developer|designer|scientist|manager|recruiter))?)", text, re.I)
        if h:
            v = re.sub(r'\s+', ' ', h.group(2)).strip().lower()
            if v and v not in roles:
                roles.insert(0, v)
        comps = [m.group(0).strip() for m in COMP.finditer(text) if MONEY.search(m.group(0))]
        comps = comps[:4]
        locs = sorted({m.group(1).lower() for m in LOC.finditer(text)})
        appl = APPLY.search(text)
        comp = (LEVER.search(text).group(1).strip() if LEVER.search(text) else None)
        if not comp:
            hs = [c.strip('@') for c in COMPANY.findall(text) if c.strip('@').lower() != (d.get('authorHandle') or '').lower()]
            comp = hs[0] if hs else (a.get('name') or None)
        rows.append({
            'id': tid, 'url': url, 'text': text, 'quotedText': qtext, 'quotedAuthor': q.get('authorHandle'),
            'authorHandle': d.get('authorHandle'), 'authorName': d.get('authorName'),
            'followers': a.get('followerCount'), 'verified': a.get('isVerified'), 'location': a.get('location'),
            'bio': re.sub(r'\s+', ' ', a.get('bio') or '')[:180],
            'postedAt': d.get('postedAt'), 'bookmarkedAt': d.get('bookmarkedAt'), 'syncedAt': d.get('syncedAt'),
            'convId': d.get('conversationId'),
            'likes': d.get('likeCount') or 0, 'reposts': d.get('repostCount') or 0,
            'replies': d.get('replyCount') or 0, 'quotes': d.get('quoteCount') or 0, 'views': d.get('viewCount'),
            'lang': d.get('language'),
            'buckets': buckets, 'company': comp, 'roles': roles[:6], 'comp': comps,
            'locs': locs[:5], 'apply': appl.group(0) if appl else None,
            'joblink': bool(JOBLINK.search(hay) or JOBLINK.search(url)),
        })

json.dump(rows, open(OUT_JSON, 'w', encoding='utf-8'), ensure_ascii=False)
print('lines:', nlines, 'hits:', len(rows))
print('buckets:', Counter(b for r in rows for b in r['buckets']).most_common())
print('has apply link:', sum(1 for r in rows if r['apply']))
print('has comp:', sum(1 for r in rows if r['comp']))
print('no bucket:', sum(1 for r in rows if not r['buckets']))
