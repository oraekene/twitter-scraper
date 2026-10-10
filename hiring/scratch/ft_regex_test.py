import re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

OFFER = re.compile(r"""(
  \bwe(?:'re|’re| are)\s+(?:hiring|looking for|recruiting)\b
| \bnow hiring\b | \bhiring\s+(?:\d+|a|an|two|three|four|five|several|multiple|more)?\s*(?:[A-Za-z]+[\s/-]{0,3}){0,3}?(?:engineers?|developers?|designers?|managers?|researchers?|scientists?|sales|marketing|growth|support|operations|people|builders?|operators?|interns?|roles|positions|heads?|leads?|founders?)
| \bjoin (?:our|the|my)\b.{0,25}\bteam\b | \bjoin us\b | \bcome join\b
| \bapply (?:now|here|today|below|via|at)\b | \bapply\b.{0,15}\b(?:here|now|today|below|via|dm|—|email)
| \bdrop your\b.{0,20}\b(?:work|below|here|portfolio)
| \bDM me\b.{0,40}\b(?:apply|interest|hiring|role|opportunity|impressive|built)
| \breply (?:with|below|if)\b.{0,25}\b(?:interest|apply|portfolio|experience|work)
| \bwe are (?:growing|building|looking)\b.{0,25}\bteam\b
| \bopen(?:ing)?\s+(?:role|roles|position|positions|job|jobs)\b | \bopen position(?:s)?\b
| \bjob (?:opening|post|posting|listing)\b | \bvacanc(?:y|ies)\b
| \blooking for (?:a|an|someone|talent|engineers?|builders?|people|someone who)\b
| \bseeking\b.{0,25}\b(?:engineer|developer|designer|hiring|talent|applicant)
| \bhiring partner(?:s)?\b | \bbackfill\b | \bnew hire(?:s)?\b | \bfirst day\b
| \bopen to (?:work|applicants|remote)\b | \bwe(?:'re|’re) hiring\b
)""", re.I | re.X)

tests = ["privy's hiring! we're looking for someone with a research background",
         "hiring MCP developers. need people who understand",
         "Chainguard is #Hiring a software engineer with only 2+ years",
         "a friend is hiring for an app studio. needs an ai-first operator.",
         "We're hiring a Founding Infrastructure Engineer to build alongside me",
         "I’m hiring AI operators. Looking for people who know how to use AI tools"]
for t in tests:
    m = OFFER.search(t)
    print(bool(m), '|', (m.group(0) if m else '')[:45], '|', t[:40])
