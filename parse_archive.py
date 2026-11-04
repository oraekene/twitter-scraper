"""Turn an X data archive into the same JSONL the crawler writes.

X stops the profile timeline at about 1,000 entries, and search only indexes a
fraction of an account's tweets, so a multi-year history is only complete in the
archive X builds for you: Settings -> Your account -> Download an archive of
your data. The zip arrives by email in about a day.

  python parse_archive.py twitter-2026-10-29-abc123.zip
  python parse_archive.py path\\to\\extracted\\archive --since 2023-10-28 --include-retweets

Reads every data/tweets*.js, drops the `window.YTD.tweets.part0 = ` prefix,
filters by date, and merges into out/history-<handle>.jsonl, skipping ids
already there. Big archives split into tweets-part0.js, tweets-part1.js, ...
"""

import argparse
import json
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).parent
OUT = HERE / "out"


_TWEETS_JS = re.compile(r"^tweets(-part\d+)?\.js$")


def archive_texts(path: Path) -> list[str]:
    """Return every data/tweets*.js, because big archives split into parts."""
    if path.is_dir():
        files = sorted(p for p in path.rglob("tweets*.js")
                       if p.parent.name == "data" and _TWEETS_JS.match(p.name))
        if not files:
            raise SystemExit(f"no data/tweets.js under {path}")
        return [p.read_text(encoding="utf-8") for p in files]
    with zipfile.ZipFile(path) as zf:
        names = sorted(n for n in zf.namelist()
                       if _TWEETS_JS.match(n.rsplit("/", 1)[-1])
                       and n.rsplit("/", 1)[0].endswith("data"))
        if not names:
            raise SystemExit(f"no data/tweets.js in {path}")
        return [zf.read(n).decode("utf-8") for n in names]


def parse(path: Path) -> list[dict]:
    items: dict[str, dict] = {}
    for raw in archive_texts(path):
        # Each file is JSONP: `window.YTD.tweets.part0 = [ ... ]`
        for item in json.loads(raw[raw.index("["):]):
            items[item["tweet"]["id_str"]] = item
    return list(items.values())


def iso(created_at: str) -> str:
    return datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y").astimezone(
        timezone.utc).isoformat()


def to_row(tweet: dict, handle: str) -> dict:
    created = iso(tweet["created_at"])
    entities = tweet.get("entities") or {}
    return {
        "id": tweet["id_str"],
        "author": {"screenName": handle},
        "createdAt": tweet["created_at"],
        "createdAtISO": created,
        "text": tweet.get("full_text") or tweet.get("text", ""),
        "lang": tweet.get("lang", ""),
        "isRetweet": bool(tweet.get("retweeted"))
        or (tweet.get("full_text") or "").startswith("RT @"),
        "metrics": {
            "likes": int(tweet.get("favorite_count") or 0),
            "retweets": int(tweet.get("retweet_count") or 0),
        },
        "urls": [u.get("expanded_url") for u in entities.get("urls", []) if u.get("expanded_url")],
        "media": [m.get("media_url_https") for m in entities.get("media", [])
                  if m.get("media_url_https")],
        "source": "archive",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("archive", help="the .zip X sent you, or the folder it extracts to")
    ap.add_argument("--handle", default="AScully789")
    ap.add_argument("--since", default=None, help="keep tweets on or after YYYY-MM-DD")
    ap.add_argument("--include-retweets", action="store_true")
    args = ap.parse_args()

    cutoff = (datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
              if args.since else None)
    rows = [to_row(item["tweet"], args.handle) for item in parse(Path(args.archive))]
    print(f"{len(rows)} tweets in the archive, oldest {min(r['createdAtISO'] for r in rows)[:10]}")

    keep = [r for r in rows
            if (cutoff is None or datetime.fromisoformat(r["createdAtISO"]) >= cutoff)
            and (args.include_retweets or not r["isRetweet"])]

    OUT.mkdir(exist_ok=True)
    target = OUT / f"history-{args.handle.lower()}.jsonl"
    merged = {r["id"]: r for r in keep}
    if target.exists():
        for line in target.read_text(encoding="utf-8").split("\n"):  # not splitlines, see crawler
            if line.strip():
                old = json.loads(line)
                merged.setdefault(old["id"], old)
        # what the live crawl found is fresher than the archive snapshot
        merged.update({r["id"]: r for r in keep})

    ordered = sorted(merged.values(), key=lambda r: r["createdAtISO"], reverse=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in ordered),
                   encoding="utf-8")
    tmp.replace(target)
    print(f"{len(keep)} kept, {len(ordered)} total -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
