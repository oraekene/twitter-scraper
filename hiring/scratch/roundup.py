"""Clean roundup parser for both numbered and bulleted tweets.

A roundup is one tweet that lists several dated opportunities. Two list styles
appear in the database and both must parse:

- Numbered lists (Build3DAO): items separated by blank lines, each with a t.co
  link.
- Bulleted lists (vercinyc): items on single newlines, no links at all, dates
  written as "nov 1".

The parser and the discovery pass share `parse_text`, so a tweet is judged by the
same rule whether it was configured by hand or found automatically. All markers
are written as escapes, so the file stays ASCII and cannot be re-mangled by an
editor.
"""
import json
import pathlib
import re
import sqlite3

# Split strategy depends on the list style. Try blank-line split first; if it
# yields fewer than 3 items, fall back to single-newline split on bullet markers.
_BULLET = "\u2022"
_ITEM_SPLIT_BLANK = re.compile(
    r"\n\n\s*(?=(?:\d+\.|" + _BULLET + r"|[\-*])\s)"
)
_ITEM_SPLIT_SINGLE = re.compile(
    r"\n\s*(?=(?:" + _BULLET + r"|[\-*])\s+(?:[@$]|[A-Za-z](?!ttp)))"
)
# Item marker at the start of a chunk
_ITEM_START = re.compile(r"^(?:\d+\.|" + _BULLET + r"|[\-*])\s+")
_LINK = re.compile(r"https?://t\.co/\S+")
_DATE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+"
    r"(\d{1,2})(?:st|nd|rd|th)?(?:\s*,?\s*(\d{4}))?\b",
    re.I,
)
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

# Discovery signals: a tweet that lists several dated opportunities. Links are
# not required, because the best roundups in the database (vercinyc) carry none.
_LIST_MARKER = re.compile(r"(?m)^\s*(?:\d+\.|" + _BULLET + r"|[\-*])\s")
_MONTH_RE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", re.I)
_OPPORTUNITY_WORD = re.compile(
    r"\b(hackathon|fellowship|accelerator|competition|residency|grant|prize|"
    r"scholarship|deadline|deadlines|apply|application|applications|cohort|fund)\b",
    re.I,
)


def _parse_date(text, default_year):
    m = _DATE.search(text)
    if not m:
        return None, None
    month = _MONTHS[m.group(1).lower()]
    day = int(m.group(2))
    year = int(m.group(3)) if m.group(3) else default_year
    try:
        import datetime
        return m.group(0), datetime.date(year, month, day)
    except ValueError:
        return m.group(0), None


def parse_text(text, tid, posted_at):
    """Return row dicts for one roundup tweet body. Pure function of the text, so
    discovery can reuse it without a second database read."""
    text = text or ""

    chunks = [c.strip() for c in _ITEM_SPLIT_BLANK.split(text)]
    items = [c for c in chunks if _ITEM_START.match(c)]

    if len(items) < 3:
        chunks = [c.strip() for c in _ITEM_SPLIT_SINGLE.split(text)]
        items = [c for c in chunks if _ITEM_START.match(c)]

    if len(items) < 3:
        return []

    rows = []
    default_year = 2026
    if posted_at:
        m = re.search(r"(\d{4})", posted_at)
        if m:
            default_year = int(m.group(1))
    for item in items:
        link = _LINK.search(item)
        clean = _ITEM_START.sub("", item).strip()
        date_str, date_obj = _parse_date(clean, default_year)
        first_line = clean.split("\n")[0]
        name = re.split(r"[" + _BULLET + r"\u2013\-]", first_line)[0].strip()
        name = re.sub(r"^\d+\.\s*", "", name).strip()
        # Some roundups write the whole entry on one line: "name, $prize, date,
        # mode". Three or more commas means the tail is metadata, not the name.
        if name.count(",") >= 2:
            name = name.split(",")[0].strip()
        rows.append({
            "program": name or clean[:40],
            "detail": clean.replace("\n", " "),
            "date_str": date_str,
            "date": date_obj,
            "tweet": f"https://x.com/{tid}",
            "link": link.group(0) if link else f"https://x.com/{tid}",
        })
    return rows


def parse_tweet(tid, db_path):
    """Return a list of row dicts for one roundup tweet."""
    con = sqlite3.connect(db_path)
    try:
        r = con.execute(
            "SELECT text, posted_at FROM bookmarks WHERE tweet_id=?", (tid,)
        ).fetchone()
    finally:
        con.close()
    if not r:
        return []
    return parse_text(r[0], tid, r[1])


def looks_like_roundup(text):
    """Cheap test before spending a parse: several list items and an opportunity
    word. The "two different months" test was dropped because a single-month
    edition ("november edition") is still a roundup; the real discriminator is
    that at least three parsed items each state a date."""
    text = text or ""
    if len(_LIST_MARKER.findall(text)) < 3:
        return False
    return bool(_OPPORTUNITY_WORD.search(text))


def _posted_dt(value):
    """Parse a Twitter-format posted_at ("Sun Oct 25 16:00:12 +0000 2026")."""
    import email.utils
    try:
        return email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


def discover_tweets(db_path, cache_path, years=("2026",), window_days=45):
    """Find every recent roundup tweet in the database, caching what was tested.

    Only tweets posted within `window_days` of the newest bookmark are tested.
    Old roundups list deadlines that have passed, and their odd formats inject
    rows nobody can use; the cache still remembers them if they were seen.

    Returns (ids, newly_found). The cache means a run only tests bookmarks it has
    never seen, so the cost stays flat as the database grows. Deleting the cache
    forces a full rescan.
    """
    cache_file = pathlib.Path(cache_path)
    try:
        cache = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {"tested": {}, "roundups": []}
    tested = cache.setdefault("tested", {})
    roundups = set(cache.setdefault("roundups", []))

    con = sqlite3.connect(db_path)
    try:
        like = " OR ".join("posted_at LIKE ?" for _ in years)
        params = [f"% {y}" for y in years]
        rows = con.execute(
            f"SELECT tweet_id, text, posted_at FROM bookmarks WHERE {like}", params
        ).fetchall()
    finally:
        con.close()

    posted = {tid: when or "" for tid, _text, when in rows}
    stamps = [d for d in (_posted_dt(w) for w in posted.values()) if d]
    cutoff = max(stamps) - __import__("datetime").timedelta(days=window_days) if stamps else None

    newly = []
    for tid, text, when in rows:
        if tid in tested:
            continue
        when_dt = _posted_dt(when)
        if cutoff and (when_dt is None or when_dt < cutoff):
            tested[tid] = 0
            continue
        parsed = parse_text(text, tid, when) if looks_like_roundup(text) else []
        tested[tid] = len(parsed)
        # A list of dated opportunities, not a list of anything. At least three
        # items must state a date, which is what separates a deadlined roundup
        # from a thread that merely uses bullets.
        if len(parsed) >= 3 and sum(1 for r in parsed if r["date_str"]) >= 3:
            roundups.add(tid)
            newly.append(tid)

    ordered = sorted(roundups, key=lambda t: posted.get(t, ""), reverse=True)
    cache["roundups"] = ordered
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(cache, indent=1, sort_keys=True), encoding="utf-8")
    return ordered, newly
