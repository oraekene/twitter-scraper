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

sys.path.insert(0, str(HERE))
import sync_bookmarks


def selftest() -> int:
    assert shutil.which("twitter"), "twitter-cli missing: uv tool install twitter-cli"
    assert NODE.exists(), f"node missing at {NODE}"
    assert FT.exists(), f"fieldtheory missing at {FT}"

    subprocess.run([str(NODE), str(FT), "--help"], check=True, capture_output=True)

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


def _flags(**kw):
    """sync_flags with defaults filled in, so a test never touches main()."""
    import argparse
    a = argparse.Namespace(max_minutes=240, count=100000, target_adds=0, max_pages=0,
                           delay_ms=0, gaps=False, rebuild=False, folders=False, folder="",
                           classify=False, engine="", media=False, media_max_bytes=0,
                           skip_profile_images=False, api=False, skip_md=False)
    for k, v in kw.items():
        setattr(a, k, v)
    return sync_bookmarks.sync_flags(a)


def test_sync_flags_match_the_old_hardcoded_call():
    """The default run must be byte for byte the command the script always ran."""
    got = _flags()
    assert got == ["sync", "--yes", "--continue", "--no-media", "--max-minutes", "240"], got


def test_sync_flags_expose_the_real_knobs():
    assert "--target-adds" in _flags(target_adds=500)
    assert _flags(target_adds=500)[_flags(target_adds=500).index("--target-adds") + 1] == "500"
    assert "--gaps" in _flags(gaps=True)
    assert "--folders" in _flags(folders=True)
    assert "--delay-ms" in _flags(delay_ms=1200)
    assert "--folder" in _flags(folder="AI stuff")
    assert "--classify" in _flags(classify=True)


def test_sync_flags_rebuild_and_continue_are_exclusive():
    """They are opposites. Passing both would restart and immediately resume."""
    assert "--rebuild" in _flags(rebuild=True)
    assert "--continue" not in _flags(rebuild=True)
    assert "--continue" in _flags()
    assert "--rebuild" not in _flags()


def test_sync_flags_skip_blank_values():
    """0 and empty mean "leave it off", never --target-adds 0."""
    got = _flags(target_adds=0, max_pages=0, delay_ms=0, media_max_bytes=0)
    for flag in ("--target-adds", "--max-pages", "--delay-ms", "--media-max-bytes"):
        assert flag not in got, f"{flag} was passed as a blank"
    assert "--no-media" in _flags(media=False), "media stays off by default"
    assert "--no-media" not in _flags(media=True)


def test_sync_flags_only_use_flags_fieldtheory_has():
    """A typo here fails at run time, hours into a sync, which is the worst
    place to find out. Read the real --help instead of trusting this list."""
    import subprocess
    out = subprocess.run([str(NODE), str(FT), "sync", "--help"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    assert "--cookies" in out, "fieldtheory sync --help did not print, cannot verify"
    for flag in ("--yes", "--rebuild", "--continue", "--gaps", "--classify", "--folders",
                 "--folder", "--no-media", "--media-max-bytes", "--skip-profile-images",
                 "--max-pages", "--target-adds", "--delay-ms", "--max-minutes", "--engine"):
        assert flag in out, f"{flag} is not a fieldtheory sync option"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"{name} ok")
    raise SystemExit(selftest())