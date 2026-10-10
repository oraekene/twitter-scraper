"""Self-check for the weekly scan: timestamp filtering and resume state.

Run: python test_weekly.py
"""

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import weekly_scan as w


def test_filters_by_last_run():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "b.jsonl"
        path.write_text("\n".join([
            json.dumps({"tweetId": "old", "syncedAt": "2026-10-01T00:00:00.000Z"}),
            json.dumps({"tweetId": "new", "syncedAt": "2026-10-09T00:00:00.000Z"}),
            json.dumps({"tweetId": "undated", "syncedAt": ""}),
        ]), encoding="utf-8")
        w.crawl.BOOKMARKS = path

        assert sorted(w.new_bookmarks_since(None, {})) == ["new", "old", "undated"]
        assert sorted(w.new_bookmarks_since("2026-10-05T00:00:00.000Z", {})) == ["new", "undated"]
        assert sorted(w.new_bookmarks_since(None, {"new": {}})) == ["old", "undated"]


def test_missing_cache_is_not_fatal():
    w.crawl.BOOKMARKS = Path("does-not-exist.jsonl")
    assert w.new_bookmarks_since(None, {}) == []


def test_runtime_cap_leaves_room_for_retries():
    """Must finish well inside the 6-hour 10am-4pm retry window."""
    assert w.MAX_RUNTIME == 150 * 60
    assert w.MAX_RUNTIME < 6 * 3600
    assert w.MAX_NEW_PER_RUN > 0


def test_stamp_is_sortable_and_iso():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    assert stamp.endswith("Z")
    assert stamp[:10] == datetime.now(timezone.utc).strftime("%Y-%m-%d")


def test_fieldtheory_paths_resolve():
    """main() builds the ft argv from these; a bad path fails only at run time."""
    from sync_bookmarks import FT, NODE

    assert NODE.exists(), f"node missing at {NODE}"
    assert FT.exists(), f"fieldtheory missing at {FT}"


def test_progress_checkpoints_each_thread():
    """Index must be written inside the loop; a run killed mid-way would otherwise
    redo every thread it already fetched."""
    src = (HERE / "weekly_scan.py").read_text(encoding="utf-8")
    loop = src.split("for tid in todo:")[1].split("now = datetime")[0]
    assert loop.count("idx.write_text") == 1, "index written once, inside the loop"


def test_eperm_is_warned_not_failed():
    """ft exits 1 when another process holds bookmarks.db open, but the bookmarks
    already landed. Treating that as a failure would skip thread expansion forever."""
    src = (HERE / "weekly_scan.py").read_text(encoding="utf-8")
    assert '"EPERM" not in tail' in src, "EPERM must downgrade to a warning"


def test_ft_receives_explicit_cookies():
    """ft sync cannot read browser cookies under a scheduled task (DPAPI fails),
    so the credentials must be passed with --cookies, not left in the env alone."""
    src = (HERE / "weekly_scan.py").read_text(encoding="utf-8")
    assert '"--cookies", ct0, token' in src, "ft sync must get --cookies"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"{name} ok")
    print("all ok")