"""Sync every X bookmark to out/ using twitter-cli (raw JSON) then fieldtheory (markdown).

Reads auth_token and ct0 from the environment or from a .env file next to this script.
Requires: uv tool install twitter-cli  /  npm install -g fieldtheory

  python sync_bookmarks.py                          # the usual run, 240 minutes
  python sync_bookmarks.py --max-minutes 60         # stop sooner, run again to resume
  python sync_bookmarks.py --target-adds 500        # fetch 500 new ones and stop
  python sync_bookmarks.py --gaps                   # backfill quotes and article text
  python sync_bookmarks.py --folders                # also sync your X folder tags
  python sync_bookmarks.py --rebuild                # full re-crawl, throws the cursor away
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "out"
NODE = Path(os.environ.get("NODE_BIN", r"C:\Users\rotim\AppData\Local\hermes\node\node.exe"))
FT = NODE.parent / "node_modules" / "fieldtheory" / "bin" / "ft.mjs"


def load_env(env_file: Path | None = None) -> None:
    env_file = env_file or HERE / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def run(cmd: list[str]) -> None:
    print("$", " ".join(cmd[:3]), "...", flush=True)
    subprocess.run(cmd, check=True)


def sync_flags(a) -> list[str]:
    """Build the fieldtheory sync arguments.

    Split out from main so test_sync.py can check the flags without touching
    the network or the real database. Credentials are not added here, they are
    the caller's business: --api ignores them entirely.

    --continue and --yes are always on, because this script is meant to be
    rerun until it stops saying "max runtime reached". --rebuild is the opposite
    of --continue, so rebuild wins and throws the cursor away on purpose.
    """
    cmd = ["sync", "--yes", "--rebuild" if a.rebuild else "--continue"]
    for on, flag in ((a.gaps, "--gaps"), (a.classify, "--classify"),
                     (a.folders, "--folders"), (a.skip_profile_images,
                                                "--skip-profile-images")):
        if on:
            cmd.append(flag)
    if not a.media:
        cmd.append("--no-media")
    for value, flag in ((a.folder, "--folder"), (a.engine, "--engine"),
                        (a.max_pages, "--max-pages"), (a.target_adds, "--target-adds"),
                        (a.delay_ms, "--delay-ms"), (a.media_max_bytes, "--media-max-bytes"),
                        (a.max_minutes, "--max-minutes")):
        if value:
            cmd += [flag, str(value)]
    return cmd


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-minutes", type=int, default=240,
                    help="fieldtheory stops here and saves a cursor; run again to resume")
    ap.add_argument("--count", type=int, default=100000,
                    help="how many bookmarks to ask twitter-cli for")
    ap.add_argument("--target-adds", type=int, default=0,
                    help="stop after N new bookmarks, gentler on rate limits than a time limit")
    ap.add_argument("--max-pages", type=int, default=0, help="cap pages fetched per pass")
    ap.add_argument("--delay-ms", type=int, default=0,
                    help="milliseconds between requests, fieldtheory default is 600")
    ap.add_argument("--gaps", action="store_true",
                    help="backfill quoted tweets, truncated articles, and linked article text")
    ap.add_argument("--rebuild", action="store_true",
                    help="full re-crawl of every bookmark. Slower, and throws the cursor away")
    ap.add_argument("--folders", action="store_true", help="also sync your X folder tags")
    ap.add_argument("--folder", default="", help="sync only this one folder by name")
    ap.add_argument("--classify", action="store_true",
                    help="run the classifier after syncing. Costs tokens")
    ap.add_argument("--engine", default="", help="override the LLM engine, claude or codex")
    ap.add_argument("--media", action="store_true",
                    help="download images and video. Off by default because it is slow")
    ap.add_argument("--media-max-bytes", type=int, default=0,
                    help="per-asset byte cap, fieldtheory default is 200 MB")
    ap.add_argument("--skip-profile-images", action="store_true",
                    help="do not download author profile pictures")
    ap.add_argument("--api", action="store_true",
                    help="use the OAuth API instead of your browser cookies")
    ap.add_argument("--skip-md", action="store_true",
                    help="stop after the database sync, do not write markdown")
    args = ap.parse_args()

    load_env()
    token = os.environ.get("TWITTER_AUTH_TOKEN")
    ct0 = os.environ.get("TWITTER_CT0")
    if not (token and ct0):
        print(
            "Missing credentials. Copy .env.example to .env and fill in "
            "TWITTER_AUTH_TOKEN and TWITTER_CT0.",
            file=sys.stderr,
        )
        return 1

    OUT.mkdir(exist_ok=True)

    run(["twitter", "bookmarks", "--full-text", "-n", str(args.count), "-o", str(OUT / "bookmarks.json")])
    count = len(json.loads((OUT / "bookmarks.json").read_text(encoding="utf-8")))
    print(f"twitter-cli: {count} bookmarks")

    # ponytail: ft stops at --max-minutes and saves a cursor. If it prints
    # "max runtime reached", run this script again; --continue resumes.
    cmd = [str(NODE), str(FT), *sync_flags(args)]
    # --api reads its own OAuth token and must not be handed cookie values.
    cmd += [] if args.api else ["--cookies", ct0, token]
    run(cmd)
    if not args.skip_md:
        run([str(NODE), str(FT), "md"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())