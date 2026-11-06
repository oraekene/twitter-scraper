"""AI-researched opportunities pass over the whole bookmark database.

The regex roundup parser in opportunities.py only sees bullet lists of three or
more dated items. This module reads EVERY tweet in bookmarks.db and asks a
language model whether it announces something a person can apply to, then
resolves the links in the tweet, fetches the page, and extracts the real
application URL, deadline and status. It writes those facts back into
opportunities_manual.json, so opportunities.py renders them.

    python research.py plan                      # how many tweets, batches, tokens
    python research.py scan                      # classify every tweet, cached
    python research.py scan --year 2026 --limit 200   # subset, for a test run
    python research.py enrich                    # fetch pages, extract facts
    python research.py merge                     # write facts into opportunities_manual.json
    python research.py clean                     # drop junk names from dedupe registry
    python research.py selftest                  # parser checks, no network

Cache: out/research.db. Re-running skips what is already classified or fetched,
so a long scan resumes where it stopped. Delete out/research.db to redo it.

The model comes from .env: LLM_BASE_URL, LLM_API_KEY, RESEARCH_MODEL. If
LLM_API_KEY is missing it falls back to sem.py's key order.
"""
from __future__ import annotations

import argparse
import concurrent.futures as futures
import datetime as dt
import email.utils
import html
import json
import os
import pathlib
import re
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "out"
DB_PATH = os.path.expandvars(r"%USERPROFILE%\.fieldtheory\bookmarks\bookmarks.db")
MANUAL = HERE / "opportunities_manual.json"
RESEARCH_DB = OUT / "research.db"
REGISTRY = OUT / "dedupe_registry.json"
BLOCKLIST = OUT / "registry_blocklist.json"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

# Model config, read from .env. Free routes are throttled, so ask() rotates
# across several working endpoints and cools a provider down when it 429s.
KEY_ORDER = ("LLM_API_KEY", "TOKENHARBOR_API_KEY", "NVIDIA_API_KEY",
             "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY",
             "OPENCODE_ZEN_KEY", "LITEROUTER_API_KEY", "UNOROUTER_API_KEY")

# Bump this when the scan prompt changes enough that earlier verdicts should be
# rechecked. `checked.version` makes that a filter instead of a manual delete.
CHECKED_VERSION = 2


def env(name):
    """Read a key from the parent .env, then the process env. Never echoes it."""
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(name + "="):
                os.environ.setdefault(name, line[len(name) + 1:].strip().strip('"').strip("'"))
    return os.environ.get(name)


def providers():
    """(name, base, key, model) endpoints, first is preferred."""
    out = []
    # The local FreeLLMAPI gateway is the preferred route: one bearer token,
    # 14 upstream keys, and the "auto" model picks whichever is free.
    fl = env("FREELMAPI_API_KEY")
    if fl:
        out.append(("freellmapi",
                    env("FREELMAPI_BASE_URL") or "http://127.0.0.1:3001/v1",
                    fl, env("FREELMAPI_MODEL") or "auto"))
    # Explabs is the fallback when the local router has no free model left.
    ex = env("EXPLABS_API_KEY")
    if ex:
        out.append(("explabs", "https://api.experientiallabs.ai/v1", ex,
                    "deepseek-v4.1-flash"))
    th = env("TOKENHARBOR_API_KEY") or env("LLM_API_KEY")
    if th:
        out.append(("tokenharbor-v41", "https://tokenharbor.ai/v1", th,
                    "deepseek-v4.1-flash:free"))
        out.append(("tokenharbor-v4", "https://tokenharbor.ai/v1", th,
                    "deepseek-v4-flash:free"))
    for name, base, keyname, model in (
            # APInex answered at zero balance in 2.6s on 5 Nov, so it is a real
            # fallback when Token Harbor's allowance is gone.
            ("apinex", "https://api.apinex.bond/v1", "APINEX_API_KEY",
             "free/deepseek-v4.1-flash"),
            ("literouter", "https://api.literouter.com/v1", "LITEROUTER_API_KEY",
             "deepseek-v4.1-flash:free"),
            ("orcarouter", "https://api.orcarouter.ai/v1", "ORCAROUTER_API_KEY",
             "deepseek/deepseek-v4.1-flash-free"),
            ("unorouter", "https://api.unorouter.com/v1", "UNOROUTER_API_KEY",
             "deepseek-v4.1-flash:free")):
        k = env(keyname)
        if k:
            out.append((name, base, k, model))
    if not out:
        k = next((env(x) for x in KEY_ORDER if env(x)), None)
        if k:
            out.append(("fallback", env("LLM_BASE_URL") or "https://tokenharbor.ai/v1",
                        k, env("RESEARCH_MODEL") or "deepseek-v4.1-flash:free"))
    return out




class _ScanRoot:
    """Thread-safe roving provider order with per-provider cooldowns, shared
    across threads. Free routes 429 often, so the first provider is usually a
    dead one; ready providers are tried in declared order, and cooling ones
    only after every ready one failed. The *same* instance is reused for the
    whole process so cooldowns persist across all `ask` calls and threads."""

    # Literouter's basic tier rejects a second message within 7 seconds, so its
    # calls are serialised with that gap; concurrent workers get 403 otherwise.
    GAPS = {"literouter": 7}
    # A 429 that says the free allowance is used up will not clear in 45s.
    DEAD_429 = ("allowance", "used up", "billing", "quota exceeded")

    def __init__(self, providers_list, root):
        self._provs = list(providers_list)
        self._cool = {}  # name -> epoch when it may be tried again
        self._last = {}  # name -> epoch of the last request
        self._prov_lock = {p[0]: threading.Lock() for p in self._provs}
        self._root = root  # contains the lock

    def _sorted(self):
        """Ready providers in declared order, then cooling ones by how soon
        they recover. Keeping the declared order stops a slow fallback from
        taking over after one success."""
        now = time.time()
        ready = [p for p in self._provs if self._cool.get(p[0], 0) <= now]
        cooling = sorted((p for p in self._provs
                          if self._cool.get(p[0], 0) > now),
                         key=lambda p: self._cool.get(p[0], 0))
        return ready + cooling

    def ask(self, prompt, system="", max_tokens=3500, temperature=0.0):
        """One chat completion with provider rotation, retries and backoff.
        All retries run on the same provider list, sorted with the "cool" map
        updated under the lock, so concurrent workers don't all collapse onto
        the same dead route."""
        with self._root._lock:
            pro = self._sorted()
        if not pro:
            return None, f"no API key in .env ({', '.join(KEY_ORDER)})"
        return self._call(pro, prompt, system, max_tokens, temperature)

    def _call(self, pro, prompt, system, max_tokens, temperature):
        last = None
        for prov in pro:
            name, base, key, model = prov
            body = json.dumps({
                "model": model, "temperature": temperature, "max_tokens": max_tokens,
                "messages": ([{"role": "system", "content": system}] if system else [])
                            + [{"role": "user", "content": prompt}],
            }).encode()
            gap = self.GAPS.get(name, 0)
            # Only a provider with a required gap needs its calls serialised;
            # the rest can run in parallel across workers.
            lock = self._prov_lock[name] if gap else None
            if lock:
                lock.acquire()
            cool_for = 45
            try:
                for attempt in range(4):
                    if gap:
                        wait = self._last.get(name, 0) + gap - time.time()
                        if wait > 0:
                            time.sleep(wait)
                    req = urllib.request.Request(base.rstrip("/") + "/chat/completions", body, {
                        "Authorization": "Bearer " + key,
                        "Content-Type": "application/json",
                        "User-Agent": UA, "Accept": "application/json"})
                    try:
                        with urllib.request.urlopen(req, timeout=90) as r:
                            out = json.loads(r.read())
                    except urllib.error.HTTPError as e:
                        raw = e.read()[:200].decode(errors="replace")
                        self._last[name] = time.time()
                        last = f"HTTP {e.code}: {raw[:120]}"
                        if e.code in (429, 500, 502, 503, 504):
                            if any(w in raw.lower() for w in self.DEAD_429):
                                cool_for = 6 * 3600
                                break
                            last = f"HTTP {e.code}: {raw[:80]}"
                            time.sleep(6 * (attempt + 1))
                            continue
                        break
                    except Exception as e:  # noqa: BLE001  transport failure is one case
                        last = f"{type(e).__name__}: {e}"
                        self._last[name] = time.time()
                        time.sleep(5 * (attempt + 1))
                        continue
                    self._last[name] = time.time()
                    msg = (out.get("choices") or [{}])[0].get("message") or {}
                    text = (msg.get("content") or "").strip()
                    if text:
                        with self._root._lock:
                            self._cool.pop(name, None)
                        return text, None
                    # Reasoning models can spend the whole budget thinking and return
                    # an empty content. That is retryable, not a verdict.
                    last = "empty completion"
                with self._root._lock:
                    self._cool[name] = time.time() + cool_for
            finally:
                if lock:
                    lock.release()
        return None, last or "all providers cooled down"


class _Root:
    """Container for the shared lock and the one persistent provider root.
    Built lazily so module import never touches the network."""

    def __init__(self):
        import threading
        self._lock = threading.Lock()
        self._scan_root = None

    def root(self):
        with self._lock:
            if self._scan_root is None:
                self._scan_root = _ScanRoot(providers(), root=self)
            return self._scan_root


_ROOT = _Root()




_ROOT = _Root()


def ask(prompt, system="", max_tokens=3500, temperature=0.0, verbose=False):
    """Thin wrapper so call sites keep reading `ask(...)` unchanged."""
    return _ROOT.root().ask(prompt, system, max_tokens, temperature)


def extract_json(text):
    """Pull a JSON array or object out of a model reply that added prose."""
    text = text or ""
    m = re.search(r"```(?:json)?\s*(\[.*?\]|\{.*\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    # Reasoning models often explain first and print the JSON later; the first
    # brace can belong to an example. Keep the best parse: an array beats an
    # object, then more elements win.
    dec = json.JSONDecoder()
    best, score = None, None
    for i, ch in enumerate(text):
        if ch not in "[{":
            continue
        try:
            obj, _ = dec.raw_decode(text[i:])
        except ValueError:
            continue
        if not isinstance(obj, (list, dict)):
            continue
        rank = (1 if isinstance(obj, list) else 0, len(obj))
        if score is None or rank > score:
            best, score = obj, rank
    if best is not None:
        return best, None
    return None, "no JSON in reply"


def scan_objects(parsed):
    """The scan asks for an array, but some models wrap it in an object."""
    if isinstance(parsed, dict):
        parsed = next((v for v in parsed.values() if isinstance(v, list)), [parsed])
    return [o for o in parsed if isinstance(o, dict)]


def get_db():
    OUT.mkdir(exist_ok=True)
    con = sqlite3.connect(RESEARCH_DB)
    con.executescript(
        "CREATE TABLE IF NOT EXISTS scans("
        " tweet_id TEXT PRIMARY KEY, model TEXT, verdict TEXT, checked_at TEXT);"
        "CREATE TABLE IF NOT EXISTS pages("
        " url TEXT PRIMARY KEY, status TEXT, error TEXT, title TEXT, text TEXT,"
        " fetched_at TEXT);"
        # Every tweet in a batch the model answered, including the ones it found
        # nothing in. Without this, a non-opportunity is re-sent on every run.
        # `version` lets a prompt change invalidate old verdicts without a
        # manual delete.
        "CREATE TABLE IF NOT EXISTS checked("
        " tweet_id TEXT PRIMARY KEY, checked_at TEXT,"
        " version INTEGER DEFAULT 1);")
    cols = {r[1] for r in con.execute("PRAGMA table_info(checked)")}
    if "version" not in cols:
        con.execute("ALTER TABLE checked ADD COLUMN version INTEGER DEFAULT 1")
    return con


def read_tweets(db_path, years, limit):
    """Yield (tweet_id, text, author, posted, links), newest posted first.

    `years` is a list of years to INCLUDE; to scan EVERY year you must pass None.
    That is how the "after" pipeline actually reaches older tweets: years=None
    means no year filter at all, and since_seconds is None means no age window,
    so a one-program tweet from 2023 is not cut off by a 45-day or 2026 gate.
    """
    con = sqlite3.connect(db_path)
    try:
        if years:
            like = " OR ".join("posted_at LIKE ?" for _ in years)
            params = [f"% {y}" for y in years]
            rows = con.execute(
                f"SELECT tweet_id, text, author_handle, posted_at, links_json "
                f"FROM bookmarks WHERE ({like}) AND length(text)>=40", params).fetchall()
        else:
            rows = con.execute(
                "SELECT tweet_id, text, author_handle, posted_at, links_json "
                "FROM bookmarks WHERE length(text)>=40").fetchall()
    finally:
        con.close()

    def key(r):
        try:
            return email.utils.parsedate_to_datetime(r[3]) or dt.datetime.min
        except (TypeError, ValueError):
            return dt.datetime.min
    rows.sort(key=key, reverse=True)
    if limit:
        rows = rows[:limit]
    return rows


def tweet_by_id(tweet_id):
    """(text, links_json) for one bookmark, or (None, None)."""
    con = sqlite3.connect(DB_PATH)
    try:
        r = con.execute("SELECT text, links_json FROM bookmarks WHERE tweet_id=?",
                        (tweet_id,)).fetchone()
    finally:
        con.close()
    return (r[0], r[1]) if r else (None, None)


SCAN_SYSTEM = (
    "You are an opportunity radar for an indie builder. You read tweets and find "
    "things a person can APPLY TO: grants, hackathons, fellowships, accelerators, "
    "scholarships, residencies, competitions, prizes, open calls, funds for "
    "founders or students, incubators, subsidized programs, research programs and "
    "cohorts. Include single-program tweets and prose announcements. Exclude job "
    "postings, paid gigs or paid tasks, products or courses for sale, discount "
    "codes, swag giveaways, news that a company raised money, conference or "
    "webinar announcements that need no application, memes and generic advice. "
    "Only use information present in the tweet. Never invent a deadline or URL.")


def scan_prompt(batch):
    lines = []
    for t in batch:
        links = t[4] or "[]"
        lines.append(json.dumps({
            "id": t[0], "author": t[2], "posted": t[3],
            "text": t[1] or "", "links": links}))
    return ("Classify each tweet. Return a JSON array with one object per "
            "OPPORTUNITY, not one per tweet: a roundup tweet that lists several "
            "programs yields several objects that share the same id. Object "
            'fields: {"id":"...","program":"human-readable program name",'
            '"org":"organizer or null","kind":"hackathon|grant|fellowship|'
            'accelerator|scholarship|residency|competition|fund|incubator|other",'
            '"deadline_text":"exact deadline phrase from the tweet or null",'
            '"apply_url":"https url present in the tweet that leads to the '
            'application, or null","money":"prize or amount as stated, or null",'
            '"eligibility":"eligibility as stated, or null",'
            '"confidence":0.0-1.0}\n\nTweets:\n' + "\n".join(lines))


def scan(years, workers, batch, limit):
    con = get_db()
    rows = read_tweets(DB_PATH, years, limit)
    done = {r[0] for r in con.execute(
        "SELECT tweet_id FROM checked WHERE version >= ?", (CHECKED_VERSION,))}
    todo = [r for r in rows if r[0] not in done]
    print(f"{len(rows)} tweets selected, {len(done)} cached, {len(todo)} to classify")

    def classify(chunk):
        # 8000 tokens leaves room for a long array when the auto model thinks
        # first; 4000 truncated some replies mid-object.
        text, err = ask(scan_prompt(chunk), system=SCAN_SYSTEM, max_tokens=8000)
        if err:
            return chunk, None, err
        parsed, perr = extract_json(text)
        if perr:
            return chunk, None, perr
        ids = {t[0] for t in chunk}
        return chunk, [o for o in scan_objects(parsed) if o.get("id") in ids], None

    def save(chunk, verdicts):
        now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        con.executemany(
            "INSERT OR REPLACE INTO checked(tweet_id, checked_at, version) "
            "VALUES (?,?,?)",
            [(t[0], now, CHECKED_VERSION) for t in chunk])
        # One row per tweet, holding every object the model returned. A roundup
        # yields several objects with the same id; keying the table by tweet_id
        # alone used to keep only the last one.
        by_id = {}
        for v in verdicts:
            by_id.setdefault(v["id"], []).append(v)
        for tid, objs in by_id.items():
            con.execute("INSERT OR REPLACE INTO scans VALUES (?,?,?,?)",
                        (tid, providers()[0][3] if providers() else "?",
                         json.dumps(objs), now))
        con.commit()

    found = 0
    failed = []
    with futures.ThreadPoolExecutor(max_workers=workers) as ex:
        batches = [todo[i:i + batch] for i in range(0, len(todo), batch)]
        for i, (chunk, verdicts, err) in enumerate(ex.map(classify, batches), 1):
            if err:
                print(f"batch {i}/{len(batches)} FAILED: {err[:120]}")
                failed.append(chunk)
                continue
            save(chunk, verdicts)
            found += len(verdicts)
            if i % 10 == 0 or i == len(batches):
                print(f"  batch {i}/{len(batches)}, opportunities so far {found}")
    if failed:
        print(f"retrying {len(failed)} failed batch(es)")
        with futures.ThreadPoolExecutor(max_workers=workers) as ex:
            for chunk, verdicts, err in ex.map(classify, failed):
                if err:
                    print(f"retry FAILED: {err[:120]}")
                    continue
                save(chunk, verdicts)
                found += len(verdicts)
    print(f"done: {found} opportunity tweet(s) classified")


def verdict_objects(raw):
    """Objects from one scans.verdict cell; new cells hold a list, old a dict."""
    try:
        obj = json.loads(raw)
    except ValueError:
        return []
    return [o for o in (obj if isinstance(obj, list) else [obj]) if isinstance(o, dict)]


def opportunity_rows():
    """All classified opportunities, newest first."""
    con = get_db()
    rows = con.execute("SELECT tweet_id, verdict FROM scans").fetchall()
    out = []
    for tid, v in rows:
        for o in verdict_objects(v):
            o["tweet_id"] = tid
            out.append(o)
    return out


def resolve(url):
    """Follow redirects to the final URL. Returns (final_url, error)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                   "Accept": "*/*"})
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.geturl(), None
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def fetch(url):
    """Download a page as text, capped at 1.5MB. Returns (title, text, error)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                   "Accept": "text/html,*/*"})
        with urllib.request.urlopen(req, timeout=25) as r:
            ctype = r.headers.get("Content-Type", "")
            if "text" not in ctype and "html" not in ctype and "json" not in ctype:
                return None, "", "not text"
            raw = r.read(1_600_000)
            data = raw.decode("utf-8", errors="replace")
        data = re.sub(r"<script.*?</script>|<style.*?</style>", " ", data, flags=re.S)
        data = re.sub(r"<[^>]+>", " ", data)
        data = html.unescape(re.sub(r"\s+", " ", data)).strip()
        m = re.search(r"<title>(.*?)</title>", raw.decode("utf-8", errors="replace"),
                      re.S | re.I)
        title = html.unescape(m.group(1).strip()) if m else ""
        return title, data[:12000], None
    except Exception as e:  # noqa: BLE001
        return None, "", f"{type(e).__name__}: {e}"


def candidate_urls(opp, links_override=None):
    """URLs worth fetching for one opportunity: apply_url, then tweet links."""
    urls = []
    for u in [opp.get("apply_url")] + (links_override or []) \
             + re.findall(r"https?://t\.co/\S+", opp.get("tweet_text") or ""):
        if not u:
            continue
        u = u.rstrip(".,);")
        # X's shortener serves an interstitial page, and its certificate chain
        # fails here, so a t.co link is never evidence of a real program page.
        if "x.com/" in u or "twitter.com/" in u or "t.co/" in u:
            continue
        if u not in urls:
            urls.append(u)
    return urls


EXTRACT_SYSTEM = (
    "You research one program from its application page and report only facts "
    "the page states. If a field is not on the page, return null for it. "
    "status is exactly one of open, closed, unknown.")


def extract_prompt(opp, page_text):
    return (f"Program: {opp.get('program')}\n"
            f"Tweet said: {(opp.get('tweet_text') or '')[:500]}\n"
            f"Page: {page_text[:9000]}\n\n"
            'Return JSON: {"program":"official program name",'
            '"apply_url":"the application page url or null",'
            '"website":"the program website or null",'
            '"deadline_iso":"YYYY-MM-DD or null",'
            '"deadline_text":"deadline as written or null",'
            '"status":"open|closed|unknown",'
            '"eligibility":"eligibility as written or null",'
            '"location":"location as written or null",'
            '"notes":"one short sentence about what it offers"}')


def enrich(limit=None):
    """Fetch pages for scan-found opportunities AND the hand-curated rows, then
    extract verified facts. Manual rows go first so they get resolved even when
    a full scan is still running. Returns the enriched opportunity list."""
    con = get_db()
    opps, seen = [], set()

    def add(o, key):
        if key and key in seen:
            return
        if key:
            seen.add(key)
        opps.append(o)

    # The hand-curated rows: their tweets are in the DB, so link resolution can
    # start immediately without waiting for the scan.
    if os.path.exists(MANUAL):
        data = json.loads(pathlib.Path(MANUAL).read_text(encoding="utf-8"))
        for row in data.get("dated", []) + data.get("undated", []):
            tid = re.search(r"(\d{6,})\s*$", row.get("tweet") or "")
            if not tid:
                continue
            text, links = tweet_by_id(tid.group(1))
            add({"program": row.get("program"), "tweet_id": tid.group(1),
                 "tweet_text": text or "", "_links": links or "[]",
                 "manual": True}, tid.group(1))
    # Everything the AI scan has classified so far.
    for o in opportunity_rows():
        if (o.get("confidence") or 0) < 0.5:
            continue
        text, links = tweet_by_id(o.get("tweet_id") or "")
        o["tweet_text"] = text or ""
        o["_links"] = links or "[]"
        o["manual"] = False
        add(o, o.get("tweet_id"))
    print(f"{len(opps)} opportunities to enrich "
          f"({sum(1 for o in opps if o['manual'])} manual)")
    if limit:
        opps = opps[:limit]

    def enrich_one(opp):
        urls = candidate_urls(opp, links_override=json.loads(opp["_links"])
                              if opp["_links"] else [])
        if not urls:
            return opp, "no url"
        for u in urls:
            final, _ = resolve(u)
            if not final:
                continue
            row = con.execute("SELECT status,error,title,text FROM pages WHERE url=?",
                              (final,)).fetchone()
            if not row:
                title, text, err = fetch(final)
                con.execute("INSERT OR REPLACE INTO pages VALUES (?,?,?,?,?,?)",
                            (final, "ok" if not err else "err", err, title,
                             text, dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")))
                con.commit()
                row = (None, err, title, text)
            if row[1]:
                continue
            opp["_page"] = final
            opp["_title"] = row[2]
            return opp, (final, row[3])
        return opp, "no fetchable url"

    done = 0
    for opp, info in [enrich_one(o) for o in opps]:
        if isinstance(info, tuple) and info[1]:
            text, err = ask(extract_prompt(opp, info[1]), system=EXTRACT_SYSTEM,
                            max_tokens=700)
            if not err:
                parsed, perr = extract_json(text)
                if not perr and isinstance(parsed, dict):
                    for k in ("apply_url", "website", "deadline_iso",
                              "deadline_text", "status", "eligibility",
                              "location", "notes"):
                        opp[k] = parsed.get(k)
            opp["evidence_url"] = info[0]
            done += 1
    print(f"fetched and extracted {done} page(s)")
    return opps


def merge(enriched=None):
    """Fold researched facts into opportunities_manual.json and write a report."""
    import dedupe  # local import keeps this module importable without hiring ctx
    enriched = enriched if enriched is not None else enrich()
    if not os.path.exists(MANUAL):
        print(f"no {MANUAL} yet; run opportunities.py once to seed it")
        return
    data = json.loads(pathlib.Path(MANUAL).read_text(encoding="utf-8"))
    today = dt.date.today().isoformat()

    def norm_tweet(u):
        return (u or "").rstrip("/")

    def real_url(u):
        """Drop X's shortener: it is never the program's own page."""
        return u if u and not re.match(r"https?://t\.co/", u) else None

    dated, undated = data["dated"], data["undated"]
    for o in enriched:
        status = (o.get("status") or "unknown").lower()
        deadline = o.get("deadline_iso") or ""
        closed = status == "closed" or (deadline and deadline < today)
        if closed:
            # A stated deadline in the past outranks a page that still says open.
            status = "closed"
        # Never add a settled-closed program as a brand-new row; it only fills
        # the tables with noise. Update it if it is already listed.
        row = next((r for r in dated + undated
                    if dedupe.known(dedupe.norm(o.get("program")),
                                    {dedupe.norm(r.get("program"))})), None)
        facts = {
            "apply_url": real_url(o.get("apply_url")),
            "website": real_url(o.get("website") or o.get("evidence_url")),
            "status": status if status != "unknown" else None,
            "verified_deadline": deadline or None,
            "deadline_text": o.get("deadline_text") or None,
            "verified_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "source": "research",
            "evidence_url": real_url(o.get("evidence_url")),
        }
        if row:
            row.update({k: v for k, v in facts.items() if v})
            continue
        if closed:
            continue
        if deadline:
            dated.append({"deadline": deadline, "label": deadline,
                          "program": o.get("program"), "detail": o.get("notes")
                          or (o.get("money") or ""), "tweet": o.get("tweet_id")
                          and f"https://x.com/{o['tweet_id']}" or "", **facts})
        else:
            undated.append({"timing": "Rolling" if status != "closed" else "Unknown",
                            "program": o.get("program"),
                            "detail": o.get("notes") or (o.get("money") or ""),
                            "tweet": o.get("tweet_id")
                            and f"https://x.com/{o['tweet_id']}" or "", **facts})
    dated.sort(key=lambda r: r["deadline"])
    data["dated"], data["undated"] = dated, undated
    pathlib.Path(MANUAL).write_text(json.dumps(data, indent=1, ensure_ascii=False),
                                    encoding="utf-8")
    print(f"merged: {len(dated)} dated, {len(undated)} undated rows in {MANUAL.name}")

    with open(OUT / "research_opportunities.json", "w", encoding="utf-8") as fh:
        json.dump(enriched, fh, indent=1, default=str)


def clean():
    """Ask the model which registry names are real programs; drop the junk."""
    import dedupe
    if not os.path.exists(REGISTRY):
        print("no registry to clean")
        return
    reg = json.loads(pathlib.Path(REGISTRY).read_text(encoding="utf-8"))
    names = sorted(reg)
    print(f"{len(names)} registry entries")
    keep, junk = [], []
    for i in range(0, len(names), 40):
        chunk = names[i:i + 40]
        prompt = ("These are program names that a parser extracted from tweets. "
                  "Return JSON mapping each key to \"keep\" if it is the name of "
                  "a program a person can apply to (grant, hackathon, fellowship, "
                  "accelerator, scholarship, fund, residency, competition), or "
                  "\"junk\" if it is a benefit, perk, requirement, skill, VC "
                  "ticket size, location or fragment, not a program name.\n\n" +
                  "\n".join(f"{k}" for k in chunk))
        text, err = ask(prompt, system=EXTRACT_SYSTEM.split("You research")[0]
                        + "You judge names. Return JSON only.", max_tokens=3000)
        if err:
            print(f"clean batch failed, keeping {len(chunk)} names: {err[:100]}")
            keep.extend(chunk)
            continue
        parsed, perr = extract_json(text)
        if perr or not isinstance(parsed, dict):
            print(f"clean batch unparsable: {perr or 'not an object'}")
            continue
        for k in chunk:
            (junk if parsed.get(k) == "junk" else keep).append(k)
    backup = REGISTRY.with_name(f"dedupe_registry.bak-{dt.date.today().isoformat()}.json")
    pathlib.Path(backup).write_text(json.dumps(reg, indent=1), encoding="utf-8")
    pathlib.Path(BLOCKLIST).write_text(json.dumps(sorted(junk), indent=1),
                                       encoding="utf-8")
    reg = {k: reg[k] for k in keep}
    pathlib.Path(REGISTRY).write_text(json.dumps(reg, indent=1, sort_keys=True),
                                      encoding="utf-8")
    print(f"cleaned: {len(keep)} kept, {len(junk)} junk -> blocklist, backup at {backup.name}")


def plan(years):
    rows = read_tweets(DB_PATH, years, None)
    chars = sum(len((t[1] or "")) for t in rows)
    batch = 30
    print(f"{len(rows)} tweets, {chars:,} chars ~ {chars // 4:,} tokens, "
          f"{len(rows) // batch + 1} batches at {batch}/call, "
          f"1 call per {batch} tweets, est. {len(rows) * 0.3 / 60:.0f} min at 2 calls/s")


def selftest():
    bad = 0

    def check(label, got, want):
        nonlocal bad
        ok = got == want
        bad += 0 if ok else 1
        print(f"  {'ok ' if ok else 'BAD'} {label}: {got!r}")

    obj, e = extract_json('here is the answer ```json\n{"a": 1}\n```')
    check("extract fenced", (obj, e), ({"a": 1}, None))
    arr, e = extract_json('x [{"id":"1"}] y')
    check("extract array", (arr, e), ([{"id": "1"}], None))
    _, e = extract_json("no json here")
    check("extract none", e is not None, True)
    mixed = 'The shape is {"id": "x"} and the answer is\n[{"id":"1"},{"id":"2"}]'
    check("extract after prose", len(extract_json(mixed)[0]), 2)
    check("resolve cache cols", get_db().execute("PRAGMA table_info(pages)").fetchall() != [], True)
    check("checked table", get_db().execute("PRAGMA table_info(checked)").fetchall() != [], True)
    check("checked version",
          "version" in {r[1] for r in get_db().execute("PRAGMA table_info(checked)")},
          True)
    # Provider tuples must stay 4-tuples in the order the scan unpacks them.
    fake = [("a", "http://a", "k", "m"), ("b", "http://b", "k", "m")]
    root = _ScanRoot(fake, root=_ROOT)
    check("sorted shape", [len(p) for p in root._sorted()], [4, 4])
    check("verdict old shape", len(verdict_objects('{"program":"old"}')), 1)
    check("verdict roundup shape",
          [o["program"] for o in verdict_objects('[{"program":"a"},{"program":"b"}]')],
          ["a", "b"])
    check("verdict junk", verdict_objects("not json"), [])
    check("scan wrapped",
          [o["id"] for o in scan_objects({"opportunities": [{"id": "1"}]})], ["1"])
    check("scan bare", [o["id"] for o in scan_objects([{"id": "2"}])], ["2"])
    print(f"selftest: {17 - bad}/17 passed")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("plan")
    p.add_argument("--year", action="append", help="2026; repeatable, omit for all")
    p = sub.add_parser("scan")
    p.add_argument("--year", action="append")
    p.add_argument("--limit", type=int)
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--batch", type=int, default=30)
    sub.add_parser("enrich").add_argument("--limit", type=int)
    sub.add_parser("merge")
    sub.add_parser("clean")
    sub.add_parser("selftest")
    args = ap.parse_args()

    if args.cmd == "selftest":
        return selftest()
    if args.cmd == "plan":
        plan(args.year)
        return 0
    if args.cmd == "scan":
        scan(args.year, args.workers, args.batch, args.limit)
        return 0
    if args.cmd == "enrich":
        enriched = enrich(limit=args.limit)
        print(f"{len(enriched)} opportunities, " +
              f"{sum(1 for o in enriched if o.get('status'))} with a status")
        return 0
    if args.cmd == "merge":
        merge()
        return 0
    if args.cmd == "clean":
        clean()
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
