import json, re, sys, io
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

IN = r'C:\Users\rotim\AppData\Local\Temp\opencode\hiring_core.json'
OUT = r'C:\Users\rotim\AppData\Local\Temp\opencode\hiring_final.json'
rows = json.load(open(IN, encoding='utf-8'))

def rx(*alts, flags=re.I):
    """Build a regex from literal-phrase alternatives. No re.X, so spaces are real."""
    return re.compile('|'.join(f'(?:{a})' for a in alts), flags)

TW = ["software", "frontend", "front-end", "backend", "back-end", "full[- ]?stack", "mobile", "ios",
      "android", "web", "devops", "sre", "platform", "infra(?:structure)?", "data", "ml",
      "machine learning", "ai", "llm", "agentic", "product", "design", "designer", "ux", "ui",
      "marketing", "growth", "sales", "account executive", "customer success", "customer support",
      "support", "operations", "ops", "finance", "financial", "accounting", "legal", "content",
      "community", "research", "scientist", "qa", "test", "security", "compliance", "engineering",
      "engineer", "program manager", "product manager", "project manager", "recruiter", "people",
      "apprentice", "intern", "teacher", "teaching", "nursing", "nurse", "driver", "executive",
      "analyst", "writer", "editor", "video", "audio", "hr", "accountant", "founder", "cofounder",
      "cto", "ceo", "vp", "head of", "general manager", "store manager", "chef", "barista",
      "developer", "architect", "coo", "cfo", "counsel", "counsellor", "therapist"]
ROLE = rx(rf"\b(?:(?:senior|sr\.?|staff|principal|junior|jr\.?|lead|associate|contract|freelance|"
          rf"entry[- ]level|mid[- ]level|graduate|new grad|first[- ]time|head of|chief|global|regional)\s+){{0,2}}"
          rf"(?:{'|'.join(TW)})"
          rf"(?:\s+(?:engineer|engineering|developer|designer|scientist|manager|recruiter|lead|architect|"
          rf"specialist|analyst|marketer|writer|officer|teacher|accountant|consultant))?\b")

HIRING_VERB = rx(r"\bhiring\b", r"\bhiring!", r"\bhire\b", r"\bseeking\b", r"\brecruiting\b",
                 r"\brecruit\b", r"\blooking\s+for\b",
                 r"\bneed(?:s|ed|ing)?\s+\w{0,20}?(?:people|someone|engineers?|developers?|builders?)")

OFFER = rx(
    r"\bwe(?:'re|’re|\s+are)\s+(?:hiring|looking\s+for|recruiting)\b",
    r"\bnow\s+hiring\b", r"\bhiring!", r"\bhire!", r"\bwe\s+hire\b",
    r"\bhiring\s+(?:\d+|a|an|two|three|four|five|several|multiple|more)?\s*(?:[A-Za-z]+\s*){0,3}?"
    r"(?:engineers?|developers?|designers?|managers?|researchers?|scientists?|specialists?|operators?|"
    r"interns?|founders?|sales|marketing|growth|support|operations|people|builders?|techs?|"
    r"roles?|positions?|heads?|leads?)",
    r"\bjoin\s+(?:our|the|my)\b[^.?!]{0,25}\bteam\b", r"\bjoin\s+us\b", r"\bcome\s+join\b",
    r"\bapply\s+(?:now|here|today|below|via|at)\b", r"\bapply\b[^.?!]{0,15}\b(?:here|now|today|below|via|dm|email)",
    r"\bdrop\s+your\b[^.?!]{0,20}\b(?:work|below|here|portfolio)",
    r"\bDM\s+me\b[^.?!]{0,40}\b(?:apply|interest|hiring|role|opportunity|impressive|built)",
    r"\breply\s+(?:with|below|if|to)\b[^.?!]{0,30}\b(?:interest|apply|portfolio|experience|work|interested)",
    r"\bwe\s+are\s+(?:growing|building|looking)\b[^.?!]{0,25}\bteam\b",
    r"\bopen(?:ing)?\s+(?:role|roles|position|positions|job|jobs)\b", r"\bopen\s+position(?:s)?\b",
    r"\bjob\s+(?:opening|post|posting|listing|listings)\b", r"\bvacanc(?:y|ies)\b",
    r"\blooking\s+for\s+(?:a|an|someone|talent|engineers?|builders?|people|one|someone\s+who)\b",
    r"\bseeking\b[^.?!]{0,25}\b(?:engineer|developer|designer|hiring|talent|applicant)",
    r"\bhiring\s+partner(?:s)?\b", r"\bbackfill\b", r"\bnew\s+hire(?:s)?\b", r"\bfirst\s+day\b",
    r"\bopen\s+to\s+(?:work|applicants|remote)\b",
    r"\bI(?:'m|’m|\s+am)\s+(?:hiring|looking\s+for)\b",
    r"\bhiring\s+(?:someone|for\s+the\s+role|for\s+a\s+role|for\s+roles)\b",
    r"(?<!\bno\sone\s)(?<!\bnobody\s)(?<!\beveryone\s)(?<!\bnothing\s)\bis\s+hiring\b",
    r"(?<!\bno\sone\s)(?<!\bnobody\s)\bare\s+hiring\b", r"\bis\s+looking\s+for\b",
)

APPLY_CTA = rx(
    r"\bapply\b[^.?!]{0,20}\b(?:here|now|today|below|via|at\b|dm|→|->)",
    r"\bsend\s+(?:me|us|your)\b[^.?!]{0,30}\b(?:resume|cv|portfolio|work|email|dm|message)",
    r"\bdrop\s+your\b[^.?!]{0,20}\b(?:work|below|here|portfolio|cv|resume)",
    r"\bDM\s+me\b[^.?!]{0,40}\b(?:apply|interest|hiring|role|opportunity|impressive|built|resume)",
    r"\breply\s+(?:with|below|if|to)\b[^.?!]{0,30}\b(?:interest|apply|portfolio|experience|work|interested)",
    r"\bemail\s+(?:me|us)\b[^.?!]{0,20}\b(?:at\b|[\w.]+@)",
    r"\b[\w.+-]+@[\w.-]+\.\w{2,}",
    r"\bhttps?://\S*(?:lever\.co|greenhouse\.io|ashbyhq|workable|breezy|smartrecruiters|jobvite|hotfix\.jobs|careers|/jobs?)[^\s]*",
    r"\bghcr\b[^.?!]{0,12}\bhire\b",
)

MONEY = rx(r"[$€£₦]\s?[\d][\d,\.]*\s?[kKmM]?\b")
PERIOD = rx(r"[$€£₦]\s?[\d][\d,\.]*\s?[kKmM]?\s*(?:/|\ba\b|per)\s*(?:year|yr|month|mo|week|day|hour|hr)")
COMPANY_HINT = rx(r"#hiring\b", r"\bcareers\b", r"\bjob\s+id\b", r"\bopen\s+positions\b")

LAYOFFMARK = rx(r"\blayoffs?\b", r"\blaid\s+off\b", r"\blaying\s+off\b", r"\blay\s+off\b",
                r"\bworkforce\s+reduction\b", r"\bjob\s+cuts?\b", r"\bdownsizing\b",
                r"\bre-?org(?:ing)?\b", r"\bheadcount\s+reduction\b", r"\bredundan(?:cy|cies)\b")

MISC = rx(r"\boffice\s+vacancy\b", r"\bvacancy\s+rate\b",
          r"\bhiring\s+(?:for\s+an?\s+)?(?:the\s+)?(?:military|army|navy|air\s+force|police)\b",
          r"\bterror(?:ist)?\s+recruitment\b", r"\brecruiting\s+budget\b",
          r"\bmilitary\s+recruiting\b", r"\brecruit(?:ing|ment)\b[^.?!]{0,20}\b(?:dating|phase|students|youths|insurgent)")

LISTY = rx(r"\b\d{1,4}\+?\s+(?:companies|startups|roles|jobs|openings|positions|remote\s+jobs)\b",
           r"\bcompanies\s+hiring\b", r"\bwho(?:'s|\s+is)\s+hiring\b", r"\bstartups?\s+hiring\b",
           r"\bcurrently\s+hiring\b", r"\bactively\s+hiring\b", r"\bjob\s+boards?\b",
           r"\bjob\s+(?:newsletter|alert|aggregator)\b", r"\bhiring\s+list\b",
           r"\blist\s+of\s+(?:hiring|jobs|companies)\b", r"\bHN\b[^.?!]{0,10}\bwho\b",
           r"\b14\s+sites\b[^.?!]{0,20}\b(?:remote\s+jobs|jobs|work)",
           r"\bsites?\s+that\s+offer\s+remote\s+jobs\b")

ADVICE = rx(
    r"\bhow\s+to\s+(?:find|get|land|pass|win|prepare|crush|nail|tackle|source|reach)\b[^.?!]{0,45}\b(?:job|role|hiring|interview|recruit|resume|cv|offer|engineer)",
    r"\btips?\b[^.?!]{0,20}\b(?:for|on|to)\b[^.?!]{0,30}\b(?:hiring|interview|resume|job|recruit|offer|candidate)",
    r"\bhiring\s+(?:process|tips?|mistakes?|signals?|manager|tactics?|funnel|loops?|bar|boom|freeze|wave|slump|pipeline|season)",
    r"\binterview\s+(?:question|questions|loop|process|red\s+flag|tip|tips|story|answer|test)",
    r"\brecruit(?:er|ers)\b[^.?!]{0,25}\b(?:said|told|call|email|reach|message|spoke|asked)",
    r"\bghost(?:ed|ing)\b", r"\brejection(?:s)?\b[^.?!]{0,25}\b(?:email|letter|after)",
    r"\bhow\s+(?:i|we|they)\s+(?:got|landed|hired)",
    r"\bcareer\s+(?:advice|tip|coach|transition)",
    r"\b(?:job|hiring)\s+market\b", r"\bmarket\s+(?:is|has\s+been)\s+(?:slower|tight|frozen|bad|rough|up|hot|crazy)",
    r"\bnetwork(?:ing)?\b[^.?!]{0,35}\b(?:job|role|hiring|referral)",
    r"\breferral\b[^.?!]{0,35}\b(?:job|role|hired|how)",
    r"\bemail\s+(?:startups?|founders?|founder|ctos?|ceos?)\b[^.?!]{0,35}\b(?:apply|instead|rather)",
    r"\bfind\s+the\s+hiring\s+manager\b", r"\bhiring\s+manager(?:'s)?\b[^.?!]{0,25}\b(?:email|linkedin|find|reach)",
    r"\bstop\s+hiring\s+interviews\b", r"\bminimum\s+viable\s+iq\s+testing\b",
    r"\bonboarding\b", r"\boffer\s+letter\b", r"\bats\b[^.?!]{0,20}\b(?:hiring|candidate)",
    r"\bjob\s+(?:application|applications)\b[^.?!]{0,35}\b(?:sent|rejection|ignored|ghosted|tracking)",
    r"\bmy\s+(?:resume|cv)\b", r"\bportfolios?\b[^.?!]{0,25}\b(?:matter|help|for)",
    r"\bcontact\s+hiring\s+teams?\b", r"\bhow\s+to\s+contact\b[^.?!]{0,30}\bhiring\b",
    r"\bapply\s+for\s+a\s+job\b", r"\bwhen\s+(?:you|the\s+candidate)\s+appl(?:y|ies|ied)\b",
    r"\bnobody'?s\s+hiring\b", r"\bhiring\s+real\b", r"\bhiring\s+is\s+so\s+broken\b",
    r"\bhiring\s+from\s+the\s+inside\b",
)

CRAFT = rx(
    r"\b\d+\s+(?:good\s+|strong\s+)?candidates?\b", r"\bpool\s+of\s+\d+\b[^.?!]{0,20}\bapplicants?",
    r"\bapplicants?\b[^.?!]{0,30}\b(?:down|up|flood|volume|drop|surge)",
    r"\beye\s?tracker\b[^.?!]{0,30}\bresume", r"\bresume\b[^.?!]{0,30}\bbefore\s+making",
    r"\bno\s+one\s+is\s+hiring\b", r"\bnot\s+hiring\b[^.?!]{0,25}\b(?:juniors?|graduates?|anyone)",
    r"\bentry[- ]level\b[^.?!]{0,30}\b(?:talent|roles?|jobs?|not\s+ready)",
    r"\bcompanies\s+aren'?t\s+(?:ready|willing)\b", r"\bneed\s+(?:is|for)\s+a\s+talent\s+pipeline\b",
    r"\bswe\s+interviews?\b", r"\bsystem\s+design\s+interview\b", r"\bleet(?:code)?\b",
    r"\bunemployment\s+(?:rate|arcs?)\b", r"\byouth\s+unemployment\b",
    r"\bentry\s+level\b[^.?!]{0,30}\b(?:jobs?|roles?|gatekeep)",
    r"\bapply(?:ing)?\s+(?:widely|everywhere|to\s+everything)\b",
    r"\b\d{3,4}\s+(?:jobs?|applications|cold\s?(?:mails?|emails?))\b",
    r"\bwork\s+visa\b", r"\bblue\s+card\b", r"\bH-?1B\b[^.?!]{0,30}\b(?:job|role|hiring|employ)",
    r"\bno\s+one\s+will\s+(?:hire|respond)\b",
)

PAST = re.compile(r"(?:after|by|since|when|who|and|because|because\s+of|thanks\s+to|hard|difficult)\s+$", re.I)

def verb_near_start(t):
    m = HIRING_VERB.search(t)
    return bool(m and m.start() < 150 and not PAST.search(t[max(0, m.start() - 14):m.start()]))

stats = Counter()
for r in rows:
    t = r['text'] or ''
    if MISC.search(t):
        r['_p'] = 'misc'
    elif LAYOFFMARK.search(t) and not OFFER.search(t):
        r['_p'] = 'layoff'
    elif LISTY.search(t) and not OFFER.search(t):
        r['_p'] = 'list'
    elif OFFER.search(t):
        r['_p'] = 'opening'
    elif verb_near_start(t) and (ROLE.search(t) or MONEY.search(t) or PERIOD.search(t)):
        r['_p'] = 'opening_weak'
    elif ADVICE.search(t):
        r['_p'] = 'advice'
    elif CRAFT.search(t):
        r['_p'] = 'craft'
    else:
        r['_p'] = 'other'
    stats[r['_p']] += 1

json.dump(rows, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
print(stats)
for k in ('opening_weak', 'advice', 'craft', 'layoff'):
    sel = [x for x in rows if x['_p'] == k]
    print(f'\n== {k} ({len(sel)}) ==')
    for r in sel[:8]:
        print(f'  @{r["authorHandle"]}: ' + re.sub(r'\s+', ' ', r['text'] or '')[:135])
