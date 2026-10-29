"""Clean roundup parser for both numbered and bulleted tweets."""
import re
import sqlite3

# Split strategy depends on the list style:
# - Numbered lists (Build3DAO): items separated by blank lines.
# - Bulleted lists (vercinyc): items are single newlines, no sub-bullets.
# Try blank-line split first; if it yields fewer than 3 items, fall back to
# single-newline split on bullet markers.
_ITEM_SPLIT_BLANK = re.compile(
    r"\n\n\s*(?=(?:\d+\.|\u2022|[\-*ò])\s)"
)
_ITEM_SPLIT_SINGLE = re.compile(
    r"\n\s*(?=(?:\u2022|[\-*ò])\s+(?:[@$]|[A-Za-z](?!ttp)))"
)
# Item marker at the start of a chunk
_ITEM_START = re.compile(r"^(?:\d+\.|\u2022|[\-*ò])\s+")
_LINK = re.compile(r"https?://t\.co/\S+")
_DATE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+"
    r"(\d{1,2})(?:st|nd|rd|th)?(?:\s*,?\s*(\d{4}))?\b",
    re.I,
)
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


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
    text, posted_at = r

    # Try blank-line split (Build3DAO style)
    chunks = [c.strip() for c in _ITEM_SPLIT_BLANK.split(text)]
    items = [c for c in chunks if _ITEM_START.match(c)]

    # Fall back to single-newline split for bulleted lists (vercinyc style)
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
        name = re.split(r"[ΓÇóΓÇô\-]", first_line)[0].strip()
        name = re.sub(r"^\d+\.\s*", "", name).strip()
        rows.append({
            "program": name or clean[:40],
            "detail": clean.replace("\n", " "),
            "date_str": date_str,
            "date": date_obj,
            "tweet": f"https://x.com/{tid}",
            "link": link.group(0) if link else f"https://x.com/{tid}",
        })
    return rows