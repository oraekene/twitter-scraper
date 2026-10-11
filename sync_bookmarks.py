"""Sync every X bookmark to out/ using twitter-cli (raw JSON) then fieldtheory (markdown).

Reads auth_token and ct0 from the environment or from a .env file next to this script.
Requires: uv tool install twitter-cli  /  npm install -g fieldtheory

  python sync_bookmarks.py                     # 100000 bookmarks, 240 minutes a pass
  python sync_bookmarks.py --max-minutes 60    # stop sooner, then run it again
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-minutes", type=int, default=240,
                    help="fieldtheory stops here and saves a cursor; run again to resume")
    ap.add_argument("--count", type=int, default=100000,
                    help="how many bookmarks to ask twitter-cli for")
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
    run([str(NODE), str(FT), "sync", "--cookies", ct0, token,
         "--continue", "--no-media", "--max-minutes", str(args.max_minutes), "--yes"])
    run([str(NODE), str(FT), "md"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())