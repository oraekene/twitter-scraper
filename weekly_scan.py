"""Weekly maintenance: pull new bookmarks, expand threads for the new ones, log it.

Run by Task Scheduler on Sunday. Safe to run by hand any time.
  python weekly_scan.py
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "out"
LOG = HERE / "weekly_scan.log"
STATE = OUT / "weekly-state.json"
MAX_RUNTIME = 150 * 60  # stop before the scheduler's next hourly retry fires
MAX_NEW_PER_RUN = 150   # first run has 94k backlog; drip-feed it

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import crawl_tweets as crawl  # noqa: E402
from sync_bookmarks import FT, NODE, load_env  # noqa: E402


def log(msg: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def read_state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def new_bookmarks_since(since: str | None, seen: dict) -> list[str]:
    """Tweet ids synced after the last run and not yet thread-expanded."""
    if not crawl.BOOKMARKS.exists():
        return []
    raw = crawl.BOOKMARKS.read_text(encoding="utf-8")
    ids = []
    for line in raw.split("\n"):
        if not line.strip():
            continue
        row = json.loads(line)
        if row["tweetId"] in seen:
            continue
        if since:
            stamped = row.get("syncedAt") or ""
            # syncedAt looks like 2026-10-08T20:34:52.912Z
            if stamped and stamped < since:
                continue
        ids.append(row["tweetId"])
    return ids


def main() -> int:
    load_env()
    started = time.time()
    deadline = started + MAX_RUNTIME
    OUT.mkdir(exist_ok=True)
    state = read_state()
    log("=== weekly scan start ===")

    # 1. Incremental bookmark sync. --continue resumes from Field Theory's own cursor.
    #    Cookies are passed explicitly because browser extraction needs DPAPI, which
    #    fails under a scheduled task. Env vars alone do not help ft; it wants the flag.
    token = os.environ.get("TWITTER_AUTH_TOKEN")
    ct0 = os.environ.get("TWITTER_CT0")
    if not (token and ct0):
        log("no credentials in .env or environment, aborting")
        return 1

    ft = [str(NODE), str(FT), "sync", "--cookies", ct0, token,
          "--continue", "--no-media", "--max-minutes", "40", "--yes"]
    log("syncing new bookmarks")
    proc = subprocess.run(ft, cwd=HERE, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    tail = (proc.stdout or "") + (proc.stderr or "")
    # ft exits 1 when its search-index rebuild cannot rename bookmarks.db.tmp over
    # bookmarks.db, which Windows refuses while any other process holds the file open.
    # The bookmarks themselves already synced, so treat that alone as a warning.
    if proc.returncode != 0 and "EPERM" not in tail:
        log(f"bookmark sync FAILED rc={proc.returncode}")
        print(tail[-1500:])
    elif proc.returncode != 0:
        log("bookmarks synced, but search index rebuild was blocked "
            "(another process has bookmarks.db open). Run 'fieldtheory index' later.")

    # 2. Expand threads only for bookmarks we have not expanded before.
    seen = {}
    idx = OUT / "threads-index.json"
    if idx.exists():
        seen = json.loads(idx.read_text())
    since = state.get("lastSuccessfulRun")
    todo = new_bookmarks_since(since, seen)
    # First run has no state file, so every bookmark ever saved looks new. Cap it
    # so the task finishes in one sitting; the rest trickle in on later runs.
    todo = todo[:MAX_NEW_PER_RUN]
    log(f"{len(todo)} bookmarks to thread-expand this run")

    done = 0
    for tid in todo:
        if time.time() > deadline:
            log("hit time cap, remaining threads wait for next run")
            break
        try:
            tweets = crawl.twitter("tweet", tid, "-n", "100")
            thread, replies = crawl.split_thread(tid, tweets)
            crawl.save(f"thread-{tid}.json",
                       {"thread": thread, "topReplies": replies[:20]})
            seen[tid] = {"parts": len(thread), "replies": len(replies)}
            done += 1
        except SystemExit as e:
            log(f"  {tid} failed: {e}")
        # Checkpoint every thread, not at the end: a killed run must not redo work.
        idx.write_text(json.dumps(seen, indent=2), encoding="utf-8")
        time.sleep(1.5)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    STATE.write_text(json.dumps({"lastSuccessfulRun": now, "threadsDone": done}), encoding="utf-8")

    total = subprocess.run(
        [str(NODE), str(FT), "status"], capture_output=True, text=True
    ).stdout
    log(f"expanded {done} threads")
    log("=== weekly scan done: " + " | ".join(l.strip() for l in total.splitlines() if "bookmarks:" in l) + " ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())