# Read-only backup of roundup.py at 02eaa62, before find_single_tweets() was
# deleted. Kept for reference; nothing imports this file.
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
from datetime import date

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
    r"\b(grants?|hackathons?|fellowships?|accelerators?|competitions?|"
    r"residencies?|scholarships?|prizes?)\b",
    re.I,
)

# A tweet that announces an application window, as opposed to one that merely
# mentions a fund. This is the difference between "applications close Nov 3" and
# "Norway's wealth fund is losing billions".
_APPLY_PHRASE = re.compile(
    r"\b(apply|applying|applications?|deadline|closes?|closing|now accepting|"
    r"register|registration|submissions?|submit|cohort|batch)\b", re.I)
_MONEY = re.compile(r"[$€£]\s?\d[\d,.]*")


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


def _clean_name(name):
    """Turn a roundup entry into a program name.

    Entries are written by the poster, not by the program, so the same event
    arrives as "@neatlogs neathack, up to $10k, oct 10 to 11, online" and as
    "Soros Fellowship". Handle marks are dropped but the organiser word is kept,
    because "neathack" alone names nothing.
    """
    name = (name or "").strip()
    name = name.split("|")[0].strip()          # event | organiser
    name = name.replace("@", "").strip()
    name = re.sub(r"\s+", " ", name)
    name = name.strip(" ,.;:-")
    # A name the poster wrote in lower case reads as a name once it is cased.
    # Names with digits are left alone, because title-casing mangles brands
    # like a16z and hack47.
    if name and name == name.lower() and not any(c.isdigit() for c in name):
        name = name.title()
        # "x" is the connector between two organisers, not a word.
        name = re.sub(r"\bX\b", "x", name)
    return name


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
    default_year = date.today().year
    if posted_at:
        # The year is written last ("... +0000 2026"). The first four digits in
        # the string are the UTC offset ("+0000"), so anchoring on 20xx and a
        # word boundary is what stops every parsed date becoming null.
        m = re.search(r"\b(20\d{2})\b", posted_at)
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
        name = _clean_name(name)
        rows.append({
            "program": name or clean[:40],
            "detail": clean.replace("\n", " "),
            "date_str": date_str,
            "date": date_obj,
            "tweet": f"https://x.com/{tid}",
            "link": link.group(0) if link else f"https://x.com/{tid}",
        })
    return rows


def find_single_tweets(db_path, known_tweets=(), window_days=45):
    """Tweets that announce one opportunity rather than a list of them.

    A single-program tweet is the one part of the radar that still needs a
    person, because naming the program is a judgement: "Applications for the YC
    Winter 2027 batch are now open" names it, "We are hosting the world's first
    Autonomous Company Hackathon" names it only once you know the account. So
    this returns the evidence a reader needs, and leaves `program` empty.

    Filter: posted inside the window, an application phrase, a stated date, and
    not a roundup. Precision is roughly one in three on live data, which is
    small enough to review in a minute and wide enough not to miss a call.
    """
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute(
            "SELECT tweet_id, text, posted_at FROM bookmarks WHERE posted_at LIKE ?",
            ("% 2026",),
        ).fetchall()
    finally:
        con.close()

    stamps = [d for d in (_posted_dt(w) for _t, _x, w in rows) if d]
    if not stamps:
        return []
    cutoff = max(stamps).toordinal() - window_days
    # Stored tweets carry a handle ("x.com/ycombinator/status/123") and new ones
    # are bare ("x.com/123"), so compare the id, not the URL.
    known = set()
    for t in known_tweets:
        m = re.search(r"(\d{6,})\s*$", t or "")
        if m:
            known.add(m.group(1))

    out = []
    for tid, text, when in rows:
        if not text or len(text) < 40:
            continue
        if tid in known:
            continue
        url = f"https://x.com/{tid}"
        posted = _posted_dt(when)
        if not posted or posted.toordinal() < cutoff:
            continue
        if not _APPLY_PHRASE.search(text):
            continue
        if not _OPPORTUNITY_WORD.search(text):
            continue
        if not _DATE.search(text):
            continue
        if len(parse_text(text, tid, when)) >= 3:
            continue  # a roundup, handled by discover_tweets
        out.append({
            "tweet": url,
            "posted": posted.date().isoformat(),
            "text": text,
            "dates": sorted({m.group(0).strip() for m in _DATE.finditer(text)}),
            "money": sorted({m.group(0) for m in _MONEY.finditer(text)})[:4],
            "program": "",
        })
    out.sort(key=lambda r: r["posted"], reverse=True)
    return out


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
