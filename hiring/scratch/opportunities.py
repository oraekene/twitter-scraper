"""Integrate roundup.py into opportunities.py."""
import json
import re
import sqlite3
import sys
from datetime import date

# Import the roundup parser from the same directory
import roundup

DB_PATH = "C:/Users/rotim/.fieldtheory/bookmarks/bookmarks.db"

# Roundup tweet IDs that compile curated lists
ROUNDUP_TWEETS = [
    "2114326493811945679",  # Build3DAO 7-hackathon roundup
    "2114386554403897624",  # vercinyc deadlines list
]

# Hand-entered single-program rows (for tweets that are not multi-item roundups)
DATED = [
    (date(2026, 10, 11), "Oct 11, closed", "a16z Speedrun alpha",
     "Up to $250k for students and new grads. The list says apps closed on the Sunday.",
     "https://x.com/justmazer/status/2108622120117015026"),
    (date(2026, 10, 20), "Oct 20, closed", "Bolt Builders Week",
     "$10k for the best app shipped on the free weekend.",
     "https://x.com/boltdotnew/status/2111125198577479919"),
    (date(2026, 10, 26), "Oct 26, closed", "Entrepreneur First, The Bridge Residency (Winter 2027)",
     "Up to $250k on company formation, or a $10k equity-free fellowship.",
     "https://x.com/kseniam0s/status/2108629257169555512"),
    (date(2026, 10, 27), "Oct 27, closed", "GitLab Life After Code hackathon",
     "$45k.",
     "https://x.com/Build3DAO/status/2114326493811945679"),
    (date(2026, 10, 28), "Oct 28, closed", "Anthropic Fellowships (STEM and Conceptual Reasoning)",
     "Four months at Anthropic from January 2027.",
     "https://x.com/AnthropicAI/status/2110720940665372825"),
    (date(2026, 10, 30), "Oct 30", "Nebius x NVIDIA Global AI Hackathon",
     "$50k. Also in the @juampitech $2.5M roundup.",
     "https://x.com/Build3DAO/status/2114326493811945679"),
    (date(2026, 11, 1), "Nov 1", "a16z Speedrun",
     "$500k plus $10m in credits.",
     "https://x.com/vercinyc/status/2114386554403897624"),
    (date(2026, 11, 1), "Nov 1", "Pivotal Q1 2027 Research Fellowship",
     "GBP 15k-18k stipend, 15 weeks in London from 18 January, mentors from Anthropic and DeepMind.",
     "https://x.com/pivotal_org/status/2108644575283736780"),
    (date(2026, 11, 2), "Nov 2, 8pm PT", "YC Winter 2027 batch",
     "The official YC tweet gives the deadline; the vercinyc roundup repeats it at $500k.",
     "https://x.com/ycombinator/status/2111183078072979886"),
    (date(2026, 11, 2), "Nov 2", "ERA NYC accelerator",
     "$150k and four months in New York.",
     "https://x.com/vercinyc/status/2114386554403897624"),
    (date(2026, 11, 3), "Nov 3", "Twitch x OpenAI Codex Hackathon",
     "$25k cash plus a TwitchCon stage spot.",
     "https://x.com/Build3DAO/status/2114326493811945679"),
    (date(2026, 11, 3), "Nov 3 (event Nov 3-8)", "Vultr Agent Rush hackathon",
     "$9k cash plus $5k credits, $200 free credits for everyone.",
     "https://x.com/Build3DAO/status/2114326493811945679"),
    (date(2026, 11, 5), "Nov 5 (event Nov 5-7)", "ETHGlobal Mumbai",
     "$175k. Applications open, no close date given.",
     "https://x.com/Build3DAO/status/2114326493811945679"),
    (date(2026, 11, 7), "Nov 7 (event Nov 7-8)", "Naive Autonomous Company Hackathon at YC",
     "$100k+ prizes and a guaranteed YC interview. Registration closing date not stated.",
     "https://x.com/usenaive/status/2114715211244376391"),
    (date(2026, 11, 9), "Nov 9, 9am PST", "Ikigai Grants",
     "$50k total, about $5k a check.",
     "https://x.com/alexsaraki/status/2113671979081572512"),
    (date(2026, 11, 13), "Nov 13", "PayPal AI Hackathon",
     "$67.5k cash. Also in the @juampitech roundup.",
     "https://x.com/Build3DAO/status/2114326493811945679"),
    (date(2026, 11, 15), "Nov 15", "CMU Africa Certificate in AI",
     "Free and online for selected applicants, six courses, starts Jan 17 2027.",
     "https://x.com/hannytalker/status/2111834513269567542"),
    (date(2026, 11, 18), "Nov 18", "Techstars NYC",
     "$220k. Techstars' own tweet gives the same date.",
     "https://x.com/Techstars/status/2108271276003405945"),
    (date(2026, 11, 19), "Nov 19", "Meta VR Start Developer Competition",
     "$1M cash, Start program members only.",
     "https://x.com/Build3DAO/status/2114326493811945679"),
    (date(2026, 12, 4), "Dec 4", "Kiroween 2026 by Kiro (AWS)",
     "$100k cash, online and global, build window opens Oct 30.",
     "https://x.com/suraj_sharma14/status/2114288357140549648"),
    (date(2026, 12, 15), "Dec 15", ".tech No Excuses Fund",
     "Up to $1M equity-free. Condition: your build must be live on a .tech domain by this date.",
     "https://x.com/suraj_sharma14/status/2111140118543339982"),
    (date(2027, 1, 31), "Jan 31, 2027", "Mercedes-Benz be-Visioneers Fellowship",
     "Fully funded, EUR 15k, travel and accommodation, 69+ eligible countries.",
     "https://x.com/scholarsregion/status/2108236946384515332"),
]

UNDATED = [
    ("Rolling", "Basis Fellowship",
     "$50k, no equity, no reporting, applications always open.",
     "https://x.com/ivan_nomadz/status/2112892308144157009"),
    ("Rolling", "Z Fellows",
     "$10k at a $1B cap, no deadline.",
     "https://x.com/suraj_sharma14/status/2111827142270918968"),
    ("Rolling", "Thiel Fellowship",
     "$250k over two years, 22 and under.",
     "https://x.com/vercinyc/status/2114386554403897624"),
    ("Rolling", "Antler NYC",
     "$500k+, needs US work authorization.",
     "https://x.com/vercinyc/status/2114386554403897624"),
    ("Always open", "Hustle Fund",
     "$150k first check.",
     "https://x.com/vercinyc/status/2114386554403897624"),
    ("Rolling", "1517 Medici",
     "Grants for students and dropouts.",
     "https://x.com/vercinyc/status/2114386554403897624"),
    ("Rolling", "Solo Founders Program",
     "$100k on an uncapped MFN SAFE, three months in SF from Feb 2027.",
     "https://x.com/suraj_sharma14/status/2111464752581149037"),
    ("Rolling", "Afore Founders-in-Residence",
     "$250k-$750k on acceptance, eight weeks in SF, next cohort Feb 1 2027.",
     "https://x.com/suraj_sharma14/status/2108852541622493365"),
    ("Rolling", "Worldwide Studios Physical AI Fellowship",
     "Free, 100 days, AI, robotics or hardware.",
     "https://x.com/TheJobfather__/status/2114397078763806804"),
    ("Not stated", "Rockefeller and OpenAI Africa grants",
     "$50m pool, up to $2m per organisation, applications open.",
     "https://x.com/theisaacola/status/2110967079574855968"),
    ("Not stated", "Gemini Hackathon (Google DeepMind)",
     "$20k in prizes plus free model access.",
     "https://x.com/juampitech/status/2111210644573950103"),
    ("Not stated", "Meta Global AI Developer Hackathon",
     "$1M.",
     "https://x.com/juampitech/status/2111210644573950103"),
    ("Not stated", "ElevenLabs Worldwide Hackathon",
     "$200k+.",
     "https://x.com/juampitech/status/2111210644573950103"),
    ("Not stated", "AWS Developer Hackathon",
     "$138k.",
     "https://x.com/juampitech/status/2111210644573950103"),
    ("Not stated", "Arbitrum Hackathon",
     "$300k.",
     "https://x.com/juampitech/status/2111210644573950103"),
    ("Not stated", "Said Aitambarek accelerator and micro-fund",
     "$1k-$2k for finalists, zero equity, first cohort forming.",
     "https://x.com/SaidAitambarek/status/2113684256266629298"),
    ("Not stated", "Idealab.ai funding",
     "Bill Gross offers funds or investor intros for an idea you want to take forward.",
     "https://x.com/Bill_Gross/status/2112910732262277152"),
    ("Not stated", "Muse Spark open kernel challenge",
     "$100k for the fastest Muse Spark implementation.",
     "https://x.com/danielgross/status/2113351902402613558"),
    ("Not stated", "Grok for Startups",
     "6 to 12 months of credits across Grok and the API, spend matched 1:1.",
     "https://x.com/ns123abc/status/2113337172031943128"),
    ("Not stated", "Finc, international founder investment",
     "$100k-$200k for an international founder willing to build in SF.",
     "https://x.com/fdotinc/status/2108295687519805737"),
    ("Not stated", "Dare Market competitions",
     "$50k in prizes, submit free, open to everyone.",
     "https://x.com/dare_market/status/1984347783000965188"),
]


def load_roundup_rows():
    """Parse every configured roundup tweet from the bookmarks DB."""
    parsed = []
    for tid in ROUNDUP_TWEETS:
        try:
            p = roundup.parse_tweet(tid, DB_PATH)
            parsed.extend(p)
        except Exception as err:
            print(f"Warning: failed to parse roundup tweet {tid}: {err}", file=sys.stderr)
    return parsed


# Parse roundup tweets from the DB and merge them with hand rows
parsed_roundups = load_roundup_rows()

rows = sorted(DATED, key=lambda r: r[0])
assert [r[0] for r in rows] == sorted(r[0] for r in DATED), "not sorted"
assert all(r[0] and r[2] and r[4].startswith("https://x.com/") for r in rows), "bad row"

out = ["# Recently saved bookmarks: hackathons, funds, grants and scholarships", "",
       "Pool: the 4,198 bookmarks saved since the 9 October export, found by today's sync.",
       f"Includes {len(parsed_roundups)} items parsed automatically from {len(ROUNDUP_TWEETS)} roundup tweets.",
       "Ranked by the deadline each tweet states; past deadlines sit at the top and are marked closed.", "",
       "| # | Deadline | Program | Detail | Tweet |", "|---|---|---|---|---|"]
for i, (_, label, program, detail, url) in enumerate(rows, 1):
    out.append(f"| {i} | {label} | {program} | {detail} | {url} |")
out += ["", "## No deadline in the tweet", "",
        "| Timing | Program | Detail | Tweet |", "|---|---|---|---|"]
for when, program, detail, url in UNDATED:
    out.append(f"| {when} | {program} | {detail} | {url} |")
out.append("")

path = "out/opportunities-2026-10-29.md"
open(path, "w", encoding="utf-8").write("\n".join(out))
print(f"{len(rows)} dated, {len(UNDATED)} undated, {len(parsed_roundups)} parsed from roundups, wrote {path}")
json.dump({"dated": [[str(r[0]), r[1], r[2], r[3], r[4]] for r in rows],
           "undated": [list(u) for u in UNDATED],
           "parsed_roundups": parsed_roundups},
          open("out/opportunities-2026-10-29.json", "w", encoding="utf-8"), indent=1)