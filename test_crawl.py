"""Self-check for crawl_tweets: thread splitting, reply ranking, cache resume.

Run: python test_crawl.py
"""

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import crawl_tweets as c


def tweet(author, likes=0, retweets=0, replies=0, quotes=0, text="x"):
    return {
        "author": {"screenName": author},
        "text": text,
        "metrics": {"likes": likes, "retweets": retweets, "replies": replies, "quotes": quotes},
    }


def test_split_thread():
    tweets = [tweet("alice"), tweet("bob"), tweet("alice"), tweet("carol")]
    thread, replies = c.split_thread("1", tweets)
    assert [t["author"]["screenName"] for t in thread] == ["alice", "alice"]
    assert [t["author"]["screenName"] for t in replies] == ["bob", "carol"]


def test_engagement_weights():
    plain = tweet("a", likes=10)  # 30
    shared = tweet("a", retweets=20)  # 40
    discussed = tweet("a", replies=10)  # 10
    assert c.engagement(shared) > c.engagement(plain)
    assert c.engagement(plain) > c.engagement(discussed)
    assert c.engagement(tweet("a")) == 0


def test_replies_ranked_desc():
    tweets = [tweet("alice"), tweet("b", likes=1), tweet("c", likes=100), tweet("d", retweets=50)]
    _, replies = c.split_thread("1", tweets)
    ranked = sorted(replies, key=c.engagement, reverse=True)
    assert [t["author"]["screenName"] for t in ranked] == ["c", "d", "b"]


def test_bookmark_cache_parsing():
    """split("\\n") only: splitlines() cuts records on \\u2028 and \\x0b inside tweet text."""
    tricky = {"tweetId": "1", "text": "a\u2028b\x0bc"}
    raw = "\n".join(json.dumps(r, ensure_ascii=False) for r in (tricky, {"tweetId": "2", "text": "ok"}))
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "bookmarks.jsonl"
        path.write_text(raw, encoding="utf-8")
        c.BOOKMARKS = path
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line.strip()]
    assert [r["tweetId"] for r in rows] == ["1", "2"]
    assert rows[0]["text"] == "a\u2028b\x0bc"


def test_save_and_resume_index():
    cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        c.OUT = Path(tmp)
        try:
            path = c.save("x.json", [{"a": 1}])
            assert json.loads(path.read_text(encoding="utf-8")) == [{"a": 1}]
            assert path.parent == Path(tmp), "must not write into out/"
        finally:
            c.OUT = cwd / "out"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"{name} ok")
    print("all ok")