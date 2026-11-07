"""Build the opportunities list: grants, hackathons, funds and fellowships.

    python opportunities.py                  # bookmarks, dated today
    python opportunities.py --days 30        # wider discovery window
    python opportunities.py --live           # also search X itself
    python opportunities.py --candidates     # AI-researched sweep as a table
    python opportunities.py --selftest       # check the parser, touch nothing

Reads the bookmark database, so sync_bookmarks.py has to run first. Write
`run --due` from ctl.py and the two weekly scripts for the schedule.
"""
import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import roundup
import dedupe

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "out"
DB_PATH = os.path.expandvars(r"%USERPROFILE%\.fieldtheory\bookmarks\bookmarks.db")

# Single-program rows live in a data file, not in this script, so adding an
# opportunity never means editing code. Data is maintained in opportunities_manual.json.
MANUAL_PATH = HERE / "opportunities_manual.json"
CANDIDATES_PATH = OUT / "single-candidates.md"

# Roundup tweets are discovered from the database, not registered by hand. A
# roundup is a tweet listing three or more dated opportunities; `roundup.py`
# finds them and caches what it tested. These two are seeds, kept so a fresh
# cache or a replaced database still knows about them.
SEED_ROUNDUPS = [
    "2114326493811945679",  # Build3DAO 7-hackathon roundup
    "2114386554403897624",  # vercinyc deadlines list, november edition
]

# The live pass can only see what it asks for, so this query is the recall net.
# 340 characters, under X's 512 limit, so one request.
OPPORTUNITY_QUERY = (
    '"hackathon" OR "hackathons" OR "grant" OR "grants" OR "fellowship" OR '
    '"fellowships" OR "accelerator" OR "accelerators" OR "scholarship" OR '
    '"scholarships" OR "residency" OR "residencies" OR "applications open" OR '
    '"now accepting" OR "deadline" OR "submissions" OR "cohort"'
)


def _parse_args():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--days", type=int, default=45,
                    help="how far back a roundup or candidate may be posted")
    ap.add_argument("--db", default=DB_PATH, help="path to bookmarks.db")
    ap.add_argument("--live", action="store_true",
                    help="also search X for new roundups")
    ap.add_argument("--limit", type=int, default=200,
                    help="live only, max tweets per batch")
    ap.add_argument("--min-likes", type=int, default=20,
                    help="live only, drop posts below this many likes")
    ap.add_argument("--candidates", action="store_true",
                    help="render the AI-researched sweep as a table")
    ap.add_argument("--selftest", action="store_true",
                    help="check the parser, touch nothing else")
    return ap.parse_args()


def output_path(today, live=False):
    stem = "opportunities-live" if live else "opportunities"
    return OUT / f"{stem}-{today.isoformat()}.md"


def rows_from_live(tweets):
    """Turn live search rows into roundup rows.

    A live row carries the author handle in its url, which the database rows do
    not, so the url replaces the bare `x.com/<id>` the parser builds.
    """
    out = []
    for r in tweets:
        for row in roundup.parse_text(r.get("text", ""), r.get("id", ""),
                                      r.get("posted_at", "")):
            row["tweet"] = r.get("url") or row["tweet"]
            out.append(row)
    return out


def live_roundups(days, limit, min_likes):
    """Search X and keep only the tweets that list dated opportunities."""
    import search  # imported here so the bookmarks pass needs no credentials

    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows, notes = search.fetch_live_chunked(
        OPPORTUNITY_QUERY, limit=limit, since=since, min_likes=min_likes,
        exclude=("retweets",))
    return rows_from_live(rows), notes


def selftest():
    """Prove the date, the parser and the live mapping without a network."""
    bad = 0

    def check(label, got, want):
        nonlocal bad
        ok = got == want
        bad += 0 if ok else 1
        print(f"  {'ok ' if ok else 'BAD'} {label}: want {want!r}, got {got!r}")

    check("output name", output_path(date(2026, 11, 4)).name,
          "opportunities-2026-11-04.md")
    check("live name", output_path(date(2026, 11, 4), live=True).name,
          "opportunities-live-2026-11-04.md")

    sample = ("Three things this month:\n\n"
              "1. Alpha Grant, $5k, oct 20, online https://t.co/aaa\n\n"
              "2. Beta Hackathon, $10k, nov 3, NYC https://t.co/bbb\n\n"
              "3. Gamma Fellowship, nov 15 https://t.co/ccc\n")
    rows = roundup.parse_text(sample, "123", "Sun Oct 25 16:00:12 +0000 2026")
    check("parse count", len(rows), 3)
    check("parse date", rows[1]["date_str"], "nov 3")
    # The year lives at the end of a Twitter timestamp; the first four digits
    # are the "+0000" offset. Reading the offset as the year made every date
    # null, which is why this is asserted and not just printed.
    check("parse date object", rows[1]["date"], date(2026, 11, 3))

    live = rows_from_live([{"id": "999", "url": "https://x.com/a/status/999",
                            "text": sample,
                            "posted_at": "Sun Oct 25 16:00:12 +0000 2026"}])
    check("live keeps handle", live[0]["tweet"], "https://x.com/a/status/999")
    check("manual rows exist", MANUAL_PATH.exists(), True)

    print(f"selftest: {7 - bad}/7 passed")
    return 1 if bad else 0


args = _parse_args()
if args.selftest:
    sys.exit(selftest())

_discovered, _new_roundups = roundup.discover_tweets(
    args.db, OUT / "roundup_cache.json", years=("2026",), window_days=args.days)
ROUNDUP_TWEETS = _discovered + [t for t in SEED_ROUNDUPS if t not in _discovered]
if _new_roundups:
    print(f"roundup: {len(_new_roundups)} newly discovered roundup tweet(s): "
          + ", ".join(_new_roundups))

# Single-program rows are read from opportunities_manual.json by _load_manual().
# Adding an opportunity means editing JSON, not Python code.
EXTRA = {}  # enriched facts per tweet url: apply_url, website, status, ...


def _load_manual():
    """Read single-program rows from the data file.

    Dated rows come back as (date, label, program, detail, tweet) and undated as
    (timing, program, detail, tweet), which is the shape the rest of the script
    already expects. A row added to the JSON needs no code change.
    """
    global EXTRA
    EXTRA = {}
    if not os.path.exists(MANUAL_PATH):
        # No JSON yet, create empty file with empty structure
        data = {"dated": [], "undated": []}
        with open(MANUAL_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1, ensure_ascii=False)
        print(f"created empty {MANUAL_PATH}")
        return [], []
    with open(MANUAL_PATH, encoding="utf-8") as fh:
        data = json.load(fh)
    for r in data.get("dated", []) + data.get("undated", []):
        if r.get("tweet"):
            EXTRA[r["tweet"]] = {k: r[k] for k in
                                 ("apply_url", "website", "status",
                                  "verified_deadline", "verified_at")
                                 if r.get(k)}
    dated = [(datetime.strptime(r["deadline"], "%Y-%m-%d").date(),
              r["label"], r["program"], r["detail"], r["tweet"])
             for r in data.get("dated", [])]
    undated = [(r["timing"], r["program"], r["detail"], r["tweet"])
               for r in data.get("undated", [])]
    return dated, undated


DATED, UNDATED = _load_manual()


if args.candidates:
    # Read the AI research sweep instead of the old regex gate. The model names
    # the program, so there is nothing left for a person to fill in here.
    _src = OUT / "research_opportunities.json"
    _rows = []
    _when = "never"
    if _src.exists():
        try:
            _rows = json.loads(_src.read_text(encoding="utf-8"))
            _when = datetime.fromtimestamp(_src.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        except ValueError as err:
            print(f"cannot read {_src.name}: {err}")
    _rows.sort(key=lambda o: -(o.get("confidence") or 0))
    _lines = [
        "# AI-researched opportunity tweets",
        "",
        f"{len(_rows)} opportunity object(s) from `{_src.name}`, written {_when}.",
        "One tweet can produce several rows when it lists several programs.",
        "",
        f"Run `research.py merge --stage` to refresh this table; add only the rows "
        f"you approve to `{MANUAL_PATH.name}`.",
        "",
        "| Confidence | Source | Program | Kind | Deadline | Money | Status | Tweet | Apply |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    def _cell(v):
        return str(v or "-").replace("|", "/").replace("\n", " ")[:120]

    for o in _rows:
        _tid = o.get("tweet_id") or ""
        _c = o.get("confidence")
        _conf = f"{_c:.2f}" if isinstance(_c, (int, float)) else "-"
        _lines.append(
            f"| {_conf} | {'manual' if o.get('manual') else 'scan'} | "
            f"{_cell(o.get('program'))} | "
            f"{_cell(o.get('kind'))} | {_cell(o.get('deadline_iso') or o.get('deadline_text'))} | "
            f"{_cell(o.get('money'))} | {_cell(o.get('status'))} | "
            f"{'https://x.com/i/status/' + _tid if _tid else '-'} | "
            f"{_cell(o.get('apply_url') or o.get('website'))} |")
    OUT.mkdir(exist_ok=True)
    CANDIDATES_PATH.write_text("\n".join(_lines) + "\n", encoding="utf-8")
    print(f"wrote {CANDIDATES_PATH}: {len(_rows)} researched object(s)")
    sys.exit(0)


def load_roundup_rows():
    """Parse every configured roundup tweet from the bookmarks DB."""
    parsed = []
    for tid in ROUNDUP_TWEETS:
        try:
            p = roundup.parse_tweet(tid, args.db)
            parsed.extend(p)
        except Exception as err:
            print(f"Warning: failed to parse roundup tweet {tid}: {err}", file=sys.stderr)
    return parsed


# Parse roundup tweets from the DB and merge them with hand rows
parsed_roundups = load_roundup_rows()

# A live run adds whatever it found on X. The parser is a pure function of the
# text, so a searched tweet goes through the same rule as a bookmarked one.
_live_notes = []
if args.live:
    _live_rows, _live_notes = live_roundups(args.days, args.limit, args.min_likes)
    parsed_roundups.extend(_live_rows)
    print(f"live: {len(_live_rows)} roundup row(s) from X")
    for _note in _live_notes:
        print(f"  {_note}")

# Drop roundup rows the AI cleanup named junk (benefit or requirement bullets
# that the regex split into fake programs). The blocklist is written by
# `python hiring/research.py clean` and keyed by dedupe.norm.
_block = set()
_bp = OUT / "registry_blocklist.json"
if _bp.exists():
    try:
        _block = set(json.loads(_bp.read_text(encoding="utf-8")))
    except ValueError:
        pass
if _block:
    _pre = len(parsed_roundups)
    parsed_roundups = [r for r in parsed_roundups
                       if dedupe.norm(r["program"]) not in _block]
    if len(parsed_roundups) != _pre:
        print(f"blocklist: dropped {_pre - len(parsed_roundups)} junk roundup row(s)")

# Collapse a roundup row that restates a programme already in the hand list.
# The hand list is curated and ordered, so it is never the side that gets
# dropped. The roundup row is dropped from the tables but kept in the JSON under
# `duplicates`, because it often carries the resolved t.co link.
_hand_keys = {dedupe.norm(r[2]) for r in DATED} | {dedupe.norm(u[1]) for u in UNDATED}
_kept_roundups, _dropped = [], []
for _row in parsed_roundups:
    if dedupe.known(dedupe.norm(_row["program"]), _hand_keys):
        _dropped.append({"program": _row["program"], "tweet": _row.get("tweet"),
                         "link": _row.get("link"),
                         "reason": "same programme already in the hand list"})
    else:
        _kept_roundups.append(_row)
_total_roundup_rows = len(parsed_roundups)
parsed_roundups = _kept_roundups
if _dropped:
    print(f"dedupe: dropped {len(_dropped)} roundup row(s) already in the hand list: "
          + ", ".join(d["program"] for d in _dropped))

# Remember every programme ever seen, so next week's run recognises one that is
# no longer in this week's output.
_registry = dedupe.load_registry()
_dedupe_today = date.today().isoformat()
_cross = dedupe.remember(
    [{"program": r[2], "date": r[0], "tweet": r[4]} for r in DATED]
    + [{"program": u[1], "tweet": u[3]} for u in UNDATED]
    + [{"program": p.get("program"), "date": p.get("date_str"), "tweet": p.get("tweet")}
       for p in parsed_roundups],
    _registry, _dedupe_today)
dedupe.save_registry(_registry)
if _cross:
    print(f"dedupe: {len(_cross)} programme(s) seen in an earlier run:")
    for _c in _cross:
        print(f"  {_c['program']}  first seen {_c['first_seen']}  now {_c['new_tweet']}")

rows = sorted(DATED, key=lambda r: r[0])
assert [r[0] for r in rows] == sorted(r[0] for r in DATED), "not sorted"
assert all(r[0] and r[2] and r[4].startswith("https://x.com/") for r in rows), "bad row"

# The parsed roundup rows are the automated half of this report, so they go in
# the tables, not only in the JSON. A pipe in the tweet would break the row.
_auto_undated = []
for _p in parsed_roundups:
    _url = _p.get("tweet") or _p.get("link") or ""
    _detail = (_p.get("detail") or "").replace("|", "/")[:220]
    _date = _p.get("date")
    if _date:
        rows.append((_date, _p.get("date_str") or _date.isoformat(),
                     _p["program"], _detail, _url))
    else:
        _auto_undated.append((_p.get("date_str") or "Not stated", _p["program"],
                              _detail, _url))
rows.sort(key=lambda r: r[0])
assert all(r[2] and r[4].startswith("https://x.com/") for r in rows), "bad roundup row"

_title = ("Live X search: hackathons, funds, grants and scholarships" if args.live
          else "Recently saved bookmarks: hackathons, funds, grants and scholarships")
out = [f"# {_title}", "",
       f"Pool: {len(ROUNDUP_TWEETS)} roundup tweet(s) posted in the last {args.days} days, "
       "plus the curated rows in opportunities_manual.json.",
       f"Includes {_total_roundup_rows} items parsed automatically from {len(ROUNDUP_TWEETS)} roundup tweets; "
       f"{len(_dropped)} of those restated a programme already listed and are recorded as duplicates.",
       "Ranked by the deadline each tweet states; past deadlines sit at the top and are marked closed.", ""]
if _live_notes:
    out.append(f"Live search coverage, {len(_live_notes)} batch(es):")
    out += [f"- {n}" for n in _live_notes]
    out.append("")
out += ["| # | Deadline | Status | Program | Detail | Apply | Tweet |",
        "|---|---|---|---|---|---|---|"]
for i, (_, label, program, detail, url) in enumerate(rows, 1):
    x = EXTRA.get(url, {})
    out.append(f"| {i} | {x.get('verified_deadline') or label} | "
               f"{x.get('status') or ('closed' if 'closed' in label.lower() else '')} | "
               f"{program} | {detail} | {x.get('apply_url') or x.get('website') or ''} | "
               f"{url} |")
out += ["", "## No deadline in the tweet", "",
        "| Timing | Status | Program | Detail | Apply | Tweet |",
        "|---|---|---|---|---|---|"]
for when, program, detail, url in UNDATED + _auto_undated:
    x = EXTRA.get(url, {})
    out.append(f"| {when} | {x.get('status') or ''} | {program} | {detail} | "
               f"{x.get('apply_url') or x.get('website') or ''} | {url} |")
out += ["", f"AI-researched opportunities are listed in "
        f"`{CANDIDATES_PATH.name}` after `--candidates` runs.", ""]

md_path = output_path(date.today(), args.live)
json_path = md_path.with_suffix(".json")
OUT.mkdir(exist_ok=True)
md_path.write_text("\n".join(out), encoding="utf-8")
print(f"{len(rows)} dated, {len(UNDATED)} undated, {len(parsed_roundups)} parsed from roundups, wrote {md_path}")
with open(json_path, "w", encoding="utf-8") as fh:
    json.dump({"dated": [[str(r[0]), r[1], r[2], r[3], r[4]] for r in rows],
               "undated": [list(u) for u in UNDATED],
               "parsed_roundups": parsed_roundups,
               "duplicates": _dropped,
               "extras": EXTRA},
              fh, indent=1, default=str)