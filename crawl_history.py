"""Crawl a whole account timeline back to a cutoff date, page by page, and resume.

`twitter user-posts` stops at 200 tweets per call (rateLimit.maxCount, hard cap
500), so it cannot reach three years on an active account. This drives the same
twitter-cli client directly, keeps the cursor in a state file, and appends every
page to JSONL so an interrupted run continues where it stopped.

Run with the twitter-cli venv python, because that is where the library lives:

  & "$env:APPDATA\\uv\\tools\\twitter-cli\\Scripts\\python.exe" crawl_history.py ascully789
  ... --since 2023-10-28 --delay 1.0
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).parent
OUT = HERE / "out"
sys.path.insert(0, str(HERE))
from sync_bookmarks import load_env  # noqa: E402

from twitter_cli.client import TwitterClient  # noqa: E402
from twitter_cli.exceptions import TwitterAPIError  # noqa: E402
from twitter_cli.graphql import FEATURES  # noqa: E402
from twitter_cli.parser import _deep_get, parse_timeline_response  # noqa: E402
from twitter_cli.serialization import tweet_to_dict  # noqa: E402


def instructions(data):
    """UserTweets moved from timeline_v2 to timeline; accept both."""
    return (_deep_get(data, "data", "user", "result", "timeline_v2", "timeline", "instructions")
            or _deep_get(data, "data", "user", "result", "timeline", "timeline", "instructions"))


def load_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    # split("\n"): tweet text can contain \u2028, which splitlines treats as a break
    return {json.loads(line)["id"] for line in path.read_text(encoding="utf-8").split("\n")
            if line.strip()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("handle")
    ap.add_argument("--since", default=None, help="stop here, YYYY-MM-DD (default: 3 years ago)")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between pages")
    args = ap.parse_args()

    load_env()
    token, ct0 = os.environ.get("TWITTER_AUTH_TOKEN"), os.environ.get("TWITTER_CT0")
    if not token or not ct0:
        raise SystemExit("No TWITTER_AUTH_TOKEN / TWITTER_CT0. Fill in .env.")

    since = args.since or (datetime.now(timezone.utc) - timedelta(days=3 * 365)).strftime("%Y-%m-%d")
    cutoff = datetime.fromisoformat(since).replace(tzinfo=timezone.utc)
    OUT.mkdir(exist_ok=True)
    slug = args.handle.lstrip("@").lower()
    path = OUT / f"history-{slug}.jsonl"
    state_path = OUT / f"history-{slug}.state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}

    if state.get("done"):
        print(f"already done: {path}")
        return 0

    seen = load_ids(path)
    client = TwitterClient(token, ct0, {"requestDelay": args.delay})
    user_id = state.get("userId") or client.resolve_user_id(slug)
    cursor = state.get("cursor")
    pages = state.get("pages", 0)
    written = state.get("count", len(seen))
    empties = stalls = 0
    print(f"resuming @{slug} user_id={user_id} at page {pages}, {written} kept, since {since}",
          flush=True)

    with path.open("a", encoding="utf-8", newline="\n") as fh:
        while True:
            variables = {
                "userId": user_id,
                "count": 40,
                "includePromotedContent": False,
                "latestControlAvailable": True,
                "requestContext": "launch",
                "withQuickPromoteEligibilityTweetFields": True,
                "withVoice": True,
                "withV2Timeline": True,
            }
            if cursor:
                variables["cursor"] = cursor
            while True:
                try:
                    data = client._graphql_get("UserTweets", variables, FEATURES)
                    break
                # X allows 50 UserTweets calls per 15 minutes. The library retries
                # three times in under a minute, which is never enough, so hold
                # the cursor and wait out the whole window instead of dying.
                except TwitterAPIError as exc:
                    if exc.status_code != 429:
                        raise
                    print("429 from X, sleeping 15 minutes", flush=True)
                    time.sleep(900)
                except Exception as exc:  # noqa: BLE001 - keep the cursor, let the next run retry
                    print(f"page {pages + 1} failed: {exc}", flush=True)
                    state_path.write_text(json.dumps({**state, "pages": pages, "cursor": cursor,
                                                      "count": written}, indent=1))
                    return 1

            tweets, next_cursor = parse_timeline_response(data, instructions)

            # Past roughly 1,000 entries X starts answering with cursor-only
            # pages, then recovers after the window rolls over. Hold the cursor:
            # overwriting it here is what turns a pause into a dead crawl.
            if not tweets:
                empties += 1
                if empties < 3:
                    time.sleep(args.delay)
                    continue
                stalls += 1
                if stalls > 3:
                    print("still empty after 3 windows: giving up at this depth", flush=True)
                    state_path.write_text(json.dumps({**state, "pages": pages, "cursor": cursor,
                                                      "count": written}, indent=1))
                    return 1
                print(f"empty pages: waiting out the window ({stalls}/3)", flush=True)
                time.sleep(900)
                empties = 0
                continue
            empties = stalls = 0
            pages += 1
            kept, old, in_window, rts = [], 0, 0, 0
            for tweet in tweets:
                d = tweet_to_dict(tweet)
                if d["id"] in seen:
                    continue
                seen.add(d["id"])
                # A pinned tweet rides at the top of the timeline and is years
                # old, so age is judged per tweet, never by the whole page.
                if datetime.fromisoformat(d["createdAtISO"]) < cutoff:
                    old += 1
                    continue
                in_window += 1
                # Retweets still cost a page each, so skipping them saves disk
                # and rows, not traffic. Kept for when the account's own words
                # are what matters.
                if d["isRetweet"]:
                    rts += 1
                    continue
                kept.append(d)

            for d in kept:
                fh.write(json.dumps(d, ensure_ascii=False) + "\n")
            fh.flush()
            written += len(kept)

            oldest = min((datetime.fromisoformat(d["createdAtISO"]) for d in kept), default=None)
            print(f"page {pages} +{len(kept)} rt{rts} -{old} kept {written}"
                  f" oldest {oldest.date() if oldest else '-'}", flush=True)

            state = {"userId": user_id, "cursor": next_cursor, "pages": pages, "count": written,
                     "since": since, "done": False}
            # A page entirely below the cutoff means the timeline has reached the
            # window's end; the top of the timeline is always newest first.
            if (old and not in_window) or not next_cursor or next_cursor == cursor:
                state["done"] = True
                state_path.write_text(json.dumps(state, indent=1))
                break
            cursor = next_cursor
            state_path.write_text(json.dumps(state, indent=1))
            time.sleep(args.delay)

    print(f"saved {path}  ({len(seen)} tweets, {pages} pages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
