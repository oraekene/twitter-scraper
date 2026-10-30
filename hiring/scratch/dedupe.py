"""Deduplicate opportunities by program name and link, across runs.

The problem this solves: the same program arrives from several roundup tweets.
Meta VR appeared once from the Build3DAO roundup as an open 19 November row and
once from the same roundup as closed by Start-program membership. Two rows, one
program, disagreeing. A reader cannot tell they are the same thing, so a page
read gets spent twice.

This module does three jobs.

1. `dedupe(rows)` groups rows by a normalised program name and collapses each
   group to one winner. A row with a stated deadline beats a row without one,
   because a dated row is a date and an undated row is a wish. A settled status
   beats an unsettled one. An official account's tweet beats a roundup.

2. A registry at `out/dedupe_registry.json` remembers every program name ever
   seen, so the next run spots a duplicate against a row that is no longer in
   the current output. That is what makes it persistent rather than one edit.

3. `flag_markdown(path)` scans a triage table for the same program appearing in
   two sections and marks the later one as a duplicate.

    python hiring/scratch/dedupe.py --check out/opportunities-2026-10-29.json
    python hiring/scratch/dedupe.py --registry
"""
import argparse
import json
import pathlib
import re
import sys

# Words that carry no identity. "Nebius x NVIDIA Global AI Hackathon" and
# "Nebius NVIDIA Global AI" must collapse to the same key, so the event type and
# filler words go.
STOP = {
    "hackathon", "fellowship", "competition", "accelerator", "grant", "fund",
    "program", "programme", "the", "a", "an", "and", "of", "for", "at", "in",
    "on", "by", "x", "2026", "2027", "batch", "cohort",
}

REGISTRY = "out/dedupe_registry.json"


# Event words that must survive when they are the only thing distinguishing a
# programme from its organiser's name. "Thiel Fellowship" keeps "fellowship";
# "YC W2027" drops the year, because the year is not the identity.
EVENT_WORDS = {"fellowship", "hackathon", "competition", "accelerator", "grant",
               "prize", "scholarship", "challenge"}


def norm(name):
    """A stable key for a program name. Punctuation, case, handles, filler words
    and years are removed so two spellings of one program collapse together."""
    s = (name or "").lower()
    s = s.replace("@", "")
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)   # punctuation to space
    words = s.split()
    kept = [t for t in words if t and t not in STOP and not re.fullmatch(r"w?\d{4}", t)]
    if len(kept) == 1:
        keep_events = [t for t in words if t in EVENT_WORDS]
        if keep_events:
            return " ".join(kept + keep_events)
    return " ".join(kept)


def _same_tokens(a, b):
    """True when two keys name the same programme allowing for a handle that was
    written in full once (nebiusai) and shortened once (nebius), or for one key
    that only adds a season or a batch word (yc vs yc winter)."""
    ta, tb = a.split(), b.split()
    if not ta or not tb:
        return False
    short, long = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    left = list(long)
    for t in short:
        hit = next((u for u in left if u.startswith(t) or t.startswith(u)), None)
        if hit is None:
            return False
        left.remove(hit)
    return True


def _mergeable(group_a, group_b):
    """Two groups of the same name may still be different batches. If both carry
    a deadline and the deadlines differ, they are separate calls, not duplicates:
    a16z Speedrun alpha closed 11 October and a16z Speedrun closes 1 November."""
    da = {r.get("date") for r in group_a if r.get("date")}
    db = {r.get("date") for r in group_b if r.get("date")}
    if da and db and not (da & db):
        return False
    return True


def known(key, keys):
    """True when `key` matches any key in `keys`, allowing handle spelling
    differences. Used to drop a roundup row that restates a hand row."""
    if key in keys:
        return True
    return any(_same_tokens(key, k) for k in keys if k)


def _score(row):
    """Higher wins. Encodes the selection order stated in the module docstring."""
    score = 0
    status = (row.get("status") or "").lower()
    # A settled row outranks a dated one. The Meta VR case is the reason: the
    # open row carried a 19 November deadline, and the closed row carried none,
    # so counting the date first kept the wrong one.
    if status in ("closed", "dropped", "duplicate"):
        score += 200
    if row.get("date"):
        score += 100
    if row.get("official"):
        score += 10
    if row.get("source_kind") != "roundup":
        score += 5
    return score


def dedupe(rows):
    """Collapse duplicate programs. Returns (kept, duplicates).

    `rows` is a list of dicts with at least `program`. Optional keys that affect
    the winner: `date`, `status`, `official`, `source_kind`.
    """
    groups = {}
    for r in rows:
        groups.setdefault(norm(r.get("program", "")), []).append(r)

    # Fold a group into an existing one when the keys differ only by a handle
    # written long once and short once.
    keys = list(groups)
    for k in keys:
        if k not in groups:
            continue
        for other in keys:
            if other == k or other not in groups:
                continue
            if _same_tokens(k, other) and _mergeable(groups[k], groups[other]):
                groups[k].extend(groups.pop(other))

    kept, duplicates = [], []
    for key, group in groups.items():
        if len(group) == 1:
            kept.append(group[0])
            continue
        ranked = sorted(group, key=_score, reverse=True)
        winner = ranked[0]
        winner = dict(winner)
        winner["sources"] = sorted({r.get("tweet", "") for r in group if r.get("tweet")})
        kept.append(winner)
        for loser in ranked[1:]:
            duplicates.append({
                "program": loser.get("program"),
                "duplicate_of": winner.get("program"),
                "reason": "same normalised name",
                "kept_tweet": winner.get("tweet"),
                "dropped_tweet": loser.get("tweet"),
            })
    return kept, duplicates


def load_registry(path=REGISTRY):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_registry(registry, path=REGISTRY):
    pathlib.Path(path).write_text(json.dumps(registry, indent=1, sort_keys=True),
                                  encoding="utf-8")


def remember(rows, registry, today):
    """Add every program to the registry and report names seen before under a
    different tweet. This is the cross-run check: a row can be dropped from the
    weekly output and still be recognised next week."""
    seen = []
    for r in rows:
        key = norm(r.get("program", ""))
        if not key:
            continue
        entry = registry.get(key)
        tweet = r.get("tweet")
        # Same-run rows arrived under two tweets (a hand row and the roundup it
        # came from). That is a duplicate inside this run, already collapsed by
        # `dedupe`, not a cross-run sighting, so it does not belong in the report.
        if entry and tweet and tweet not in entry.get("tweets", []) \
                and entry.get("first_seen") != today:
            seen.append({
                "program": r.get("program"),
                "first_seen": entry.get("first_seen"),
                "new_tweet": tweet,
                "known_tweets": entry.get("tweets", []),
            })
        if entry:
            entry.setdefault("tweets", [])
            if tweet and tweet not in entry["tweets"]:
                entry["tweets"].append(tweet)
            entry["last_seen"] = today
        else:
            registry[key] = {
                "program": r.get("program"),
                "first_seen": today,
                "last_seen": today,
                "tweets": [tweet] if tweet else [],
            }
    return seen


def flag_markdown(path):
    """Mark a program that appears in more than one section of a triage table.

    The first appearance keeps its row. Every later appearance gets the text
    `duplicate of the row above` in its last cell, so a reader who scans the open
    table sees the pointer before spending a page read.
    """
    p = pathlib.Path(path)
    text = p.read_text(encoding="utf-8")
    seen = {}
    out = []
    flagged = 0
    for line in text.splitlines():
        if line.startswith("| ") and line.count("|") >= 4:
            cells = [c.strip() for c in line.strip("|").split("|")]
            # Only program rows: a numbered first cell or a known status cell.
            if cells and re.fullmatch(r"\d+", cells[0] or ""):
                key = norm(cells[2] if len(cells) > 2 else "")
                if key and key in seen:
                    if not cells[-1].lower().startswith("duplicate"):
                        cells[-1] = (cells[-1] + "; duplicate of row " + seen[key])\
                            if cells[-1] else f"duplicate of row {seen[key]}"
                        line = "| " + " | ".join(cells) + " |"
                        flagged += 1
                elif key:
                    seen[key] = cells[0]
        out.append(line)
    p.write_text("\n".join(out) + "\n", encoding="utf-8")
    return flagged


def _rows_from_opportunities(payload):
    """Flatten the opportunities.py JSON into dedupe rows."""
    out = []
    for row in payload.get("dated", []):
        out.append({"program": row[2], "date": row[0], "detail": row[3],
                    "tweet": row[4], "source_kind": "hand"})
    for row in payload.get("undated", []):
        out.append({"program": row[1], "detail": row[2], "tweet": row[3],
                    "source_kind": "hand"})
    for row in payload.get("parsed_roundups", []):
        out.append({"program": row.get("program"), "date": row.get("date_str"),
                    "detail": row.get("detail"), "tweet": row.get("tweet"),
                    "source_kind": "roundup"})
    return out


def selftest():
    """Prove the three jobs on synthetic data. No DB, no network."""
    import tempfile
    bad = 0

    def check(label, got, want):
        nonlocal bad
        ok = got == want
        bad += 0 if ok else 1
        print(f"  {'ok ' if ok else 'BAD'} {label}: want {want}, got {got}")

    # 1. Two spellings of one programme collapse to one key.
    check("norm handle kept", norm("@nebiusai x @nvidia Global AI Hackathon"),
          "nebiusai nvidia global ai")
    check("norm handle tolerant",
          _same_tokens(norm("@nebiusai x @nvidia Global AI Hackathon"),
                       norm("Nebius x NVIDIA Global AI")), True)
    check("norm surname kept", norm("Thiel Fellowship"), "thiel fellowship")
    check("norm distinct", norm("Thiel Fellowship") != norm("Thiel Foundation"), True)
    check("norm year dropped", norm("YC W2027"), "yc")
    check("norm season kept", norm("YC Winter 2027"), "yc winter")
    check("norm season merges", _same_tokens(norm("YC W2027"), norm("YC Winter 2027")), True)

    # 2. A dated row beats an undated one; a settled row beats an open one.
    rows = [
        {"program": "a16z Speedrun", "date": "2026-11-01", "tweet": "t1", "source_kind": "hand"},
        {"program": "a16z speedrun", "date": "nov 1", "tweet": "t2", "source_kind": "roundup"},
        {"program": "Meta VR", "status": "open", "date": "2026-11-19", "tweet": "t3"},
        {"program": "Meta VR", "status": "closed", "tweet": "t4"},
    ]
    kept, dups = dedupe(rows)
    check("dedupe count", (len(kept), len(dups)), (2, 2))
    check("dated wins", [r for r in kept if "speedrun" in r["program"].lower()][0]["tweet"], "t1")
    check("settled wins", [r for r in kept if r["program"] == "Meta VR"][0]["tweet"], "t4")
    check("sources merged",
          [r for r in kept if r["program"] == "Meta VR"][0]["sources"], ["t3", "t4"])

    # Two dated batches of one accelerator are separate calls, not duplicates.
    batches = [
        {"program": "a16z Speedrun alpha", "date": "2026-10-11", "tweet": "b1"},
        {"program": "a16z Speedrun", "date": "2026-11-01", "tweet": "b2"},
    ]
    check("batches kept apart", len(dedupe(batches)[0]), 2)

    # 3. A second sighting in the same run is not reported as cross-run noise.
    reg = {}
    today = "2026-10-30"
    remember([{"program": "Alpha Program", "tweet": "t1"}], reg, today)
    check("same-run silent",
          remember([{"program": "Alpha Program", "tweet": "t2"}], reg, today), [])
    check("next-run reported",
          len(remember([{"program": "Alpha Program", "tweet": "t3"}], reg, "2026-11-06")), 1)

    # 4. The markdown flagger points a repeated programme at the first row.
    tmp = pathlib.Path(tempfile.mkdtemp()) / "triage.md"
    tmp.write_text("| # | Deadline | Program | Note |\n|---|---|---|---|\n"
                   "| 1 | Nov 19 | Meta VR | ok |\n"
                   "| 2 | Nov 20 | Other | ok |\n"
                   "| 3 | Nov 21 | Meta VR | second |\n", encoding="utf-8")
    check("flagged", flag_markdown(tmp), 1)
    check("pointer written", "duplicate of row 1" in tmp.read_text(encoding="utf-8"), True)

    print(f"selftest: {17 - bad}/17 passed")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", help="opportunities JSON to deduplicate")
    ap.add_argument("--markdown", help="triage markdown to flag in place")
    ap.add_argument("--registry", action="store_true", help="print the registry")
    ap.add_argument("--selftest", action="store_true", help="check the module")
    ap.add_argument("--today", default="2026-10-30")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    if args.registry:
        reg = load_registry()
        for key in sorted(reg):
            e = reg[key]
            print(f"{e['program']}  first={e['first_seen']}  tweets={len(e['tweets'])}")
        print(f"{len(reg)} program(s) in the registry")
        return 0

    if args.markdown:
        n = flag_markdown(args.markdown)
        print(f"flagged {n} duplicate row(s) in {args.markdown}")
        return 0

    if not args.check:
        ap.print_help()
        return 2

    payload = json.loads(pathlib.Path(args.check).read_text(encoding="utf-8"))
    rows = _rows_from_opportunities(payload)
    kept, dups = dedupe(rows)
    reg = load_registry()
    cross = remember(rows, reg, args.today)
    save_registry(reg)

    print(f"{len(rows)} row(s) in, {len(kept)} unique program(s), {len(dups)} duplicate(s) collapsed")
    for d in dups:
        print(f"  duplicate: {d['program']} (dropped {d['dropped_tweet']})")
    if cross:
        print(f"{len(cross)} program(s) seen before under a different tweet:")
        for c in cross:
            print(f"  {c['program']}  first seen {c['first_seen']}  new {c['new_tweet']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
