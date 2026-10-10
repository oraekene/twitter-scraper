"""Self-check: verify the tools exist and the credential plumbing is wired.

Run: python sync_bookmarks.py --selftest
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
NODE = Path(os.environ.get("NODE_BIN", r"C:\Users\rotim\AppData\Local\hermes\node\node.exe"))
FT = NODE.parent / "node_modules" / "fieldtheory" / "bin" / "ft.mjs"


def selftest() -> int:
    assert shutil.which("twitter"), "twitter-cli missing: uv tool install twitter-cli"
    assert NODE.exists(), f"node missing at {NODE}"
    assert FT.exists(), f"fieldtheory missing at {FT}"

    subprocess.run([str(NODE), str(FT), "--help"], check=True, capture_output=True)

    # load_env must fill os.environ from .env without overwriting real shell vars.
    sys.path.insert(0, str(HERE))
    import sync_bookmarks

    with tempfile.TemporaryDirectory() as tmp:
        env_file = Path(tmp) / ".env"
        env_file.write_text(
            "# comment\nTWITTER_CT0=from_file\nTWITTER_AUTH_TOKEN=from_file\n\nBAD LINE\n",
            encoding="utf-8",
        )
        os.environ["TWITTER_CT0"] = "from_shell"
        os.environ.pop("TWITTER_AUTH_TOKEN", None)
        sync_bookmarks.load_env(env_file)
        assert os.environ["TWITTER_CT0"] == "from_shell", "shell value must win"
        assert os.environ["TWITTER_AUTH_TOKEN"] == "from_file", ".env value must apply"

    json.dumps({"ok": True})
    print("selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(selftest())