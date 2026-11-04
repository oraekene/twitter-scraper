"""Build a last30days-x-posts/1 envelope from the local X sources.

Feed the file to the last30days engine as its X lane:

    python to_envelope.py --topic "AI agents" --live --min-likes 100
    python to_envelope.py --topic "AI agents" --query agents --bookmarks
    python to_envelope.py --selfcheck

Live mode searches X with the patched twitter CLI, cookies read from .env.
Bookmarks mode reads your saved corpus, engagement included.
The engine validates the file, rebuilds every citation URL from the post id,
and calls no X backend for that run. Window and topic must match the run:

    python C:\\Users\\rotim\\.agents\\skills\\last30days\\scripts\\last30days.py "AI agents" --x-posts out\\x-posts.json
"""

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
ENV_FILE = BASE / ".env"
BOOKMARKS = Path.home() / ".fieldtheory" / "bookmarks" / "bookmarks.jsonl"
SNOWFLAKE_EPOCH_MS = 1288834974657
MAX_ROWS = 1000
ROWS_PER_CALL = 500
SKILL_SCRIPTS = Path(
    os.environ.get("LAST30DAYS_SKILL_DIR", r"C:\Users\rotim\.agents\skills\last30days")
) / "scripts"


def load_cookies():
    cookies = {}
    if not ENV_FILE.exists():
        return cookies
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            cookies[key.strip()] = value.strip()
    return cookies


def iso_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def window(days, as_of=None):
    end = date.fromisoformat(as_of) if as_of else datetime.now(timezone.utc).date()
    return (end - timedelta(days=days)).isoformat(), end.isoformat()


def parse_twitter_time(value):
    return datetime.strptime(value, "%a %b %d %H:%M:%S %z %Y").isoformat()


def synthetic_id(when):
    ms = int(when.timestamp() * 1000)
    return str(((ms - SNOWFLAKE_EPOCH_MS) << 22) | random.getrandbits(22))


def row(post_id, handle, created_iso, text, likes=0, reposts=0, replies=0, quotes=0):
    return {
        "id": str(post_id),
        "author_handle": handle,
        "created_at": created_iso,
        "text": text,
        "likes": int(likes),
        "reposts": int(reposts),
        "replies": int(replies),
        "quotes": int(quotes),
    }


def envelope(topic, rows, dates, provider):
    from_day, to_day = dates
    calls = [
        {"lane": "topic", "handles": [], "posts": rows[i : i + ROWS_PER_CALL]}
        for i in range(0, len(rows), ROWS_PER_CALL)
    ]
    return {
        "schema": "last30days-x-posts/1",
        "generated_at": iso_now(),
        "topic": topic,
        "window": {"from": from_day, "to": to_day},
        "provider": provider,
        "status": "ok",
        "calls": calls,
    }


def live_rows(args, dates):
    twitter = shutil.which("twitter")
    if not twitter:
        raise SystemExit("twitter CLI not found on PATH")
    from_day, to_day = dates
    cmd = [
        twitter, "search", args.query,
        "-n", str(args.max),
        "--since", from_day,
        "--exclude", "retweets",
        "--json",
    ]
    if args.as_of:
        cmd += ["--until", to_day]
    if args.min_likes:
        cmd += ["--min-likes", str(args.min_likes)]
    cmd += list(args.search_args or [])
    env = dict(os.environ)
    env.update(load_cookies())
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=env)
    if proc.returncode != 0:
        raise SystemExit("twitter search failed: " + proc.stderr.strip()[:300])
    payload = json.loads(proc.stdout)
    if not payload.get("ok"):
        raise SystemExit("twitter search error: " + str(payload.get("error"))[:300])
    rows = []
    for item in payload.get("data") or []:
        handle = ((item.get("author") or {}).get("screenName") or "").strip()
        text = (item.get("text") or "").strip()
        created = item.get("createdAtISO") or parse_twitter_time(item["createdAt"])
        if not item.get("id") or not handle or not text:
            continue
        metrics = item.get("metrics") or {}
        rows.append(
            row(item["id"], handle, created, text,
                metrics.get("likes", 0), metrics.get("retweets", 0),
                metrics.get("replies", 0), metrics.get("quotes", 0))
        )
    return rows


def bookmark_rows(args, dates):
    path = Path(args.file) if args.file else BOOKMARKS
    if not path.exists():
        raise SystemExit("bookmarks file not found: " + str(path))
    from_day, to_day = dates
    terms = [t.lower() for t in args.query.split()]
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            item = json.loads(line)
            text = (item.get("text") or "").strip()
            if not text or not all(t in text.lower() for t in terms):
                continue
            posted = item.get("postedAt")
            if not posted:
                continue
            created = parse_twitter_time(posted)
            if not (from_day <= created[:10] <= to_day):
                continue
            handle = (item.get("authorHandle") or "").strip()
            post_id = str(item.get("tweetId") or item.get("id") or "")
            if not handle or not post_id:
                continue
            engagement = item.get("engagement") or {}
            rows.append(
                row(post_id, handle, created, text,
                    engagement.get("likeCount", 0), engagement.get("repostCount", 0),
                    engagement.get("replyCount", 0), engagement.get("quoteCount", 0))
            )
            if len(rows) >= args.max:
                break
    return rows


def write_envelope(args, rows, dates, provider):
    data = envelope(args.topic, rows, dates, provider)
    out = Path(args.out) if args.out else BASE / "out" / "x-posts.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return out, len(rows)


def selfcheck():
    sys.path.insert(0, str(SKILL_SCRIPTS))
    from lib import x_envelope

    now = datetime.now(timezone.utc)
    rows = [
        row(synthetic_id(now), "someone", now.isoformat(timespec="seconds"), "fresh post", 12, 3, 1, 0),
        row(synthetic_id(now - timedelta(days=10)), "other", (now - timedelta(days=10)).isoformat(timespec="seconds"), "ten days old", 5, 0, 0, 0),
    ]
    topic = "selfcheck topic"
    data = envelope(topic, rows, window(30), "local-x-cli")
    tmp = Path(tempfile.mkdtemp(prefix="xenv-"))
    path = tmp / "x-posts.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    loaded = x_envelope.read(str(path), window(30), topic)
    assert loaded.accepted == 2, "engine accepted %s of 2" % loaded.accepted
    assert sum(loaded.counters.values()) == 0, "engine dropped rows: %s" % loaded.counters
    assert parse_twitter_time("Thu Oct 08 19:31:32 +0000 2026") == "2026-10-08T19:31:32+00:00"
    path.unlink()
    tmp.rmdir()
    print("ok: the engine's own validator accepted 2 of 2 synthetic rows")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--selfcheck", action="store_true")
    parser.add_argument("--topic")
    parser.add_argument("--query")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--bookmarks", action="store_true")
    parser.add_argument("--min-likes", type=int, default=0)
    parser.add_argument("--max", type=int, default=500)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--file")
    parser.add_argument("--out")
    parser.add_argument("--as-of", help="end the window on this date (YYYY-MM-DD) instead of today")
    parser.add_argument(
        "--search-args",
        nargs=argparse.REMAINDER,
        help="extra args passed verbatim to twitter search (must be last)",
    )
    args = parser.parse_args()

    if args.selfcheck:
        selfcheck()
        return

    if not args.topic:
        parser.error("--topic is required")
    if args.live == args.bookmarks:
        parser.error("pick one of --live or --bookmarks")
    if args.min_likes and not args.live:
        parser.error("--min-likes only applies to --live")
    args.query = args.query or args.topic
    args.max = min(args.max, MAX_ROWS)

    dates = window(args.days, args.as_of)
    rows = live_rows(args, dates) if args.live else bookmark_rows(args, dates)
    if not rows:
        raise SystemExit("no posts matched inside the %d-day window" % args.days)
    out, count = write_envelope(args, rows, dates, "local-x-cli")
    print("%d posts -> %s" % (count, out))
    print(
        'next: python "%s\\last30days.py" "%s" --x-posts "%s"'
        % (SKILL_SCRIPTS, args.topic, out)
    )


if __name__ == "__main__":
    main()
