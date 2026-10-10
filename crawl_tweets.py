"""Crawl tweets from X: whole accounts, full threads, and top replies.

Every subcommand shells out to twitter-cli and reads auth_token and ct0 from
the environment or .env, so cookies never hit disk beyond that one file.

  python crawl_tweets.py account AScully789 -n 2000 -o out/mine.json
  python crawl_tweets.py account Weyaxi -n 500 -o out/weyaxi.json
  python crawl_tweets.py thread 2108246041548018053
  python crawl_tweets.py replies 2108246041548018053 --top 5
  python crawl_tweets.py threads --limit 200          # every bookmarked thread
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).parent
OUT = HERE / "out"
BOOKMARKS = Path(os.environ.get("FT_BOOKMARKS", Path.home() / ".fieldtheory/bookmarks/bookmarks.jsonl"))

sys.path.insert(0, str(HERE))
from sync_bookmarks import load_env  # noqa: E402  isort: skip


def twitter(*args: str) -> list[dict]:
    """Run twitter-cli and return the tweet list it printed as JSON."""
    proc = subprocess.run(
        ["twitter", *args, "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        sys.stderr.write(proc.stderr or proc.stdout or "")
        raise SystemExit(f"twitter-cli failed: {proc.returncode}")
    payload = json.loads(proc.stdout[proc.stdout.index("{"):])
    if not payload.get("ok"):
        raise SystemExit(f"X error: {payload.get('error', {}).get('message')}")
    return payload["data"]


def engagement(tweet: dict) -> int:
    """Rank replies by the weight the reader gave them, not by raw likes.

    ponytail: likes dominate and retweets next. Replies and quotes matter but
    count less, because they fire on controversy, not usefulness.
    """
    m = tweet.get("metrics") or {}
    return (
        3 * m.get("likes", 0)
        + 2 * m.get("retweets", 0)
        + m.get("replies", 0)
        + m.get("quotes", 0)
    )


def split_thread(root: str, tweets: list[dict]) -> tuple[list[dict], list[dict]]:
    """twitter tweet returns the author's thread parts and other replies mixed.

    The root author's own tweets, in order, are the thread. Everyone else is a reply.
    """
    author = tweets[0]["author"]["screenName"] if tweets else ""
    thread = [t for t in tweets if t["author"]["screenName"] == author]
    replies = [t for t in tweets if t["author"]["screenName"] != author]
    return thread, replies


def save(name: str, data) -> Path:
    OUT.mkdir(exist_ok=True)
    path = OUT / name
    if isinstance(data, (list, dict)):
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        path.write_text(str(data), encoding="utf-8")
    print(f"saved {path}")
    return path


def cmd_account(a) -> None:
    tweets = twitter("user-posts", a.handle, "-n", str(a.max))
    save(f"account-{a.handle}.json", tweets)
    print(f"{a.handle}: {len(tweets)} tweets")


def cmd_thread(a) -> None:
    tweets = twitter("tweet", a.tweet_id, "-n", str(a.max))
    thread, replies = split_thread(a.tweet_id, tweets)
    print(f"thread parts: {len(thread)}  replies: {len(replies)}")
    for t in thread:
        print(f"  @{t['author']['screenName']}: {t['text'][:70]}")
    if a.save:
        save(f"thread-{a.tweet_id}.json", {"thread": thread, "topReplies": replies[: a.top]})


def cmd_replies(a) -> None:
    tweets = twitter("tweet", a.tweet_id, "-n", str(a.max))
    _, replies = split_thread(a.tweet_id, tweets)
    ranked = sorted(replies, key=engagement, reverse=True)
    for i, t in enumerate(ranked[: a.top], 1):
        m = t.get("metrics") or {}
        print(f"{i}. @{t['author']['screenName']} score={engagement(t)} "
              f"(L{m.get('likes',0)} R{m.get('retweets',0)}) {t['text'][:70]}")
    if a.save:
        save(f"replies-{a.tweet_id}.json", ranked[: a.top])


def cmd_threads(a) -> None:
    """Walk the bookmark cache and pull the full thread behind each bookmark."""
    if not BOOKMARKS.exists():
        raise SystemExit(f"no bookmark cache at {BOOKMARKS}")
    done = OUT / "threads-index.json"
    seen = json.loads(done.read_text()) if done.exists() else {}
    # split("\n"), not splitlines(): tweet text contains \u2028 and \x0b, which
    # splitlines treats as line breaks and would cut a JSON record in half.
    raw = BOOKMARKS.read_text(encoding="utf-8")
    rows = [json.loads(line) for line in raw.split("\n") if line.strip()]
    todo = [r for r in rows if r["tweetId"] not in seen][: a.limit]
    print(f"{len(todo)} bookmarked threads to expand ({len(seen)} done)")
    for i, row in enumerate(todo, 1):
        tid = row["tweetId"]
        try:
            tweets = twitter("tweet", tid, "-n", str(a.max))
            thread, replies = split_thread(tid, tweets)
            save(f"thread-{tid}.json", {"root": row, "thread": thread, "topReplies": replies[: a.top]})
            seen[tid] = {"parts": len(thread), "replies": len(replies)}
        except SystemExit as e:
            print(f"  {tid} failed: {e}")
        done.write_text(json.dumps(seen, indent=2), encoding="utf-8")
        time.sleep(a.delay)
        print(f"[{i}/{len(todo)}] {tid} {seen.get(tid, {})}")


def main() -> None:
    load_env()
    if not os.environ.get("TWITTER_AUTH_TOKEN"):
        raise SystemExit("No TWITTER_AUTH_TOKEN. Copy .env.example to .env and fill it in.")

    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    acc = sub.add_parser("account", help="all tweets from an account")
    acc.add_argument("handle")
    acc.add_argument("-n", "--max", type=int, default=200)
    acc.set_defaults(fn=cmd_account)

    thr = sub.add_parser("thread", help="full thread behind one tweet")
    thr.add_argument("tweet_id")
    thr.add_argument("-n", "--max", type=int, default=100)
    thr.add_argument("--top", type=int, default=20, help="top N replies to keep")
    thr.add_argument("--save", action="store_true")
    thr.set_defaults(fn=cmd_thread)

    rep = sub.add_parser("replies", help="top replies to one tweet, ranked")
    rep.add_argument("tweet_id")
    rep.add_argument("-n", "--max", type=int, default=200, help="how many replies to fetch")
    rep.add_argument("--top", type=int, default=5)
    rep.add_argument("--save", action="store_true")
    rep.set_defaults(fn=cmd_replies)

    allt = sub.add_parser("threads", help="expand every bookmarked thread")
    allt.add_argument("--limit", type=int, default=50)
    allt.add_argument("-n", "--max", type=int, default=100)
    allt.add_argument("--top", type=int, default=20)
    allt.add_argument("--delay", type=float, default=1.5, help="seconds between calls")
    allt.set_defaults(fn=cmd_threads)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()