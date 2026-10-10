import json, re
from collections import Counter, defaultdict

POOL = r'C:\Users\rotim\AppData\Local\Temp\opencode\hiring_pool.json'
rows = json.load(open(POOL, encoding='utf-8'))

def eng(r):
    return (r['likes'] or 0) + 2*(r['reposts'] or 0) + (r['replies'] or 0)

# ---------- category signals ----------
CATS = {
 'open_role': re.compile(r"\b(job opening|job post|job listing|open role|open position|we(?:'re| are) hiring|now hiring|we(?:'re| are) looking for|join (?:our|the) team|hiring for|apply (?:now|here|today)|vacanc(?:y|ies)|new hire|first day|backfill|headcount|referral bonus|open to (?:work|applicants)|seeking (?:a|an|talent)|looking for (?:a|an|someone|talent)|paying|comp range|salary range|base salary)\b", re.I),
 'layoff': re.compile(r"\b(layoffs?|laid off|laying off|reorg|workforce reduction|job cuts|downsizing|fired|termination|end of contract)\b", re.I),
 'hiring_talk': re.compile(r"\b(interview|hiring manager|recruit(?:er|ing)|candidate|resume|cv\b|portfolio|referral|screening|assessment|offer letter|salary|compensation|equity|onboarding|hiring process|ghosted|rejection)\b", re.I),
 'founder_hiring': re.compile(r"\b(founder|cofounder|co-founder|we(?:'re| are) a (?:startup|team|one-person)|building a team|our team is|startup)\b", re.I),
}

# ---------- company / role extraction ----------
ROLE = re.compile(r"\b(hiring|seeking|looking for|need)\s+(?:an?\s+)?([A-Za-z][A-Za-z/+#.\- ]{2,45}?)\s*(?:\(|$|[.,;!?\n]|—|–|->|\bat\b|\bfor\b|\bto\b)", re.I)
TITLE = re.compile(r"\b(?:senior|sr\.?|staff|principal|junior|jr\.?|lead|head of|intern|contract|freelance|entry[- ]level|mid[- ]level)?\s*"
                   r"(software|frontend|front[- ]end|backend|back[- ]end|full[- ]stack|fullstack|mobile|ios|android|devops|sre|"
                   r"platform|infra|infrastructure|data|machine learning|ml|ai|llm|product|design|designer|ux|ui|"
                   r"marketing|growth|sales|account executive|customer success|support|operations|ops|finance|legal|"
                   r"content|community|research|scientist|qa|test|security|compliance|research engineer|"
                   r"engineering manager|em\b|cto|ceo|vp|program manager|product manager)\b", re.I)

# job-board domains
JOBBOARD = re.compile(r"(lever\.co|greenhouse\.io|ashbyhq|workable\.com|breezy\.hr|smartrecruiters|jobvite|"
                      r"jobs\.|apply\.|\bjob id\b|jobboard|workatastartup|wellfound|otta|linkedin\.com/jobs|"
                      r"indeed\.com|ziprecruiter|dice\.com|wellfound\.com)", re.I)

for r in rows:
    hay = (r['text'] or '') + ' ' + (r['quotedText'] or '')
    hits = [k for k, p in CATS.items() if p.search(hay)]
    r['_cats'] = hits
    r['_eng'] = eng(r)
    m = ROLE.search(r['text'] or '')
    r['_role_ctx'] = (m.group(2).strip() if m else '')
    t = TITLE.search(hay)
    r['_title'] = t.group(0).strip().lower() if t else ''
    r['_joblink'] = bool(JOBBOARD.search(hay)) or bool(JOBBOARD.search(r['url'] or ''))

print('pool:', len(rows))
print('cats:', Counter(c for r in rows for c in r['_cats']).most_common())
print('primary:', Counter((r['_cats'] or ['none'])[0] for r in rows).most_common())
print('joblinks:', sum(r['_joblink'] for r in rows))
print('\ntop titles:', Counter(r['_title'] for r in rows if r['_title']).most_common(30))
print('\ntop authors:', Counter(r['authorHandle'] for r in rows).most_common(25))
print('\nno cat:', sum(1 for r in rows if not r['_cats']))
json.dump(rows, open(POOL, 'w', encoding='utf-8'), ensure_ascii=False)
