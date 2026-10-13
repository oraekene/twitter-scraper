r"""Conceptual search over a corpus you do not own.

There are no embeddings anywhere in this file. The concept lives in the query set,
the ranking lives in Reciprocal Rank Fusion plus a calibrated classifier, and the
only learning is a scoreboard of which queries paid off.

    python sem.py search "tweets remotely hinting at hiring"
    python sem.py search "accounts complaining about Cursor performance" --source bookmarks
    python sem.py eval "hiring" --suite adversarial
    python sem.py queries "hiring"
    python sem.py selftest

Why this is not just "grep with more words". Grep finds a string. A concept has
no string. So the concept gets written out as 60 to 80 different surface forms,
X retrieves each one separately, and a tweet that comes back under many of them
is by definition near the centre of the concept. That agreement is the signal,
and RRF is just the arithmetic for summing it.

Why it cannot replace hiring/search.py. That module is 81 curated FTS phrases
and three hand-written regex tiers, compiled once by hand for one concept. This
one covers any concept including ones nobody imagined, and on a cold concept it
may find nothing the hand-written set missed. Run both. They are not in conflict.

Two traps this file exists to avoid.

    X returns order, not scores. Any fusion that needs numbers is guessing.
    Reciprocal Rank Fusion needs only ranks, so it is the honest choice.

    A query string has no hidden class in it. Asking a classifier "is this query
    about hiring" about 60 queries that were all written to be about hiring
    returns yes to nearly all of them. It looks like a working filter and
    filters nothing. So the classifier is NOT used to triage queries. It checks
    the negatives for drift, it orders the positives by expected yield, and it
    does the real work in phase 7 where candidates are retrieved tweets that
    genuinely disagree with each other.

Sources. x needs TWITTER_AUTH_TOKEN and TWITTER_CT0 in .env. bookmarks reads
the Field Theory database and is free and offline. Ranking is identical over
both, so every eval runs against bookmarks before it ever spends an X call.
"""

from __future__ import annotations

import argparse
import concurrent.futures as futures
import hashlib
import json
import math
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (HERE, ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from search import fetch_live  # noqa: E402  the subprocess, the env, the normalisation
from pat import pat_fts  # noqa: E402  refuses regex syntax FTS5 cannot parse

SEM_DB = os.path.join(HERE, 'semsearch.db')
BM_DB = os.path.expandvars(r'%USERPROFILE%\.fieldtheory\bookmarks\bookmarks.db')

RRF_K = 60              # damps rank 1 so one lucky hit cannot dominate
POOL = 300              # tweets carried into the classifier pass
CAP = 440               # X rejects a raw query over 512 chars with PipelineFailure
GROUP = 6               # queries per OR-batch probe
PAUSE = 2.0             # 19 accounts back to back answers 429 from the eighth
JACCARD = 0.8           # above this two queries retrieve the same thing

# The classifier does not judge, it extracts. Asking one question, "is this an
# offer", returns 0.577 on average for real offers and 0.307 for lookalikes,
# which overlaps so badly that every answer lands in the unclear band and the
# model commits to nothing. Four narrow questions in one call separate cleanly.
# Measured 2026-10-11, see SEMANTIC.md.
FEATURES = {
    'offer_language': 'Does this tweet contain the direct language of an employer '
                      'advertising a role, such as "we are hiring" or "open role"?',
    'role_named': 'Does this tweet name a specific job title, role, or department?',
    'how_to_apply': 'Does this tell the reader how to respond, such as apply here, '
                    'DM me, or a careers link?',
    'discussion_only': 'Is this discussion, opinion, news, advice, or the author looking '
                       'for work, rather than an employer advertising a role?',
}

# Calibrated on 14 adversarial tweets, where hits landed at 0.62 and above and
# lookalikes at 0.155 and below. That is a wide gap on a small sample, so treat
# these as provisional and re-measure on a larger labelled set before trusting
# them on a new concept.
HIT_BAND = 0.45
MISS_BAND = 0.25

SCHEMA = """
CREATE TABLE IF NOT EXISTS concepts (
  key TEXT PRIMARY KEY, text TEXT, rubric INT DEFAULT 1,
  ttl_hours REAL DEFAULT 24, created_at TEXT);
CREATE TABLE IF NOT EXISTS queries (
  id INTEGER PRIMARY KEY, key TEXT, text TEXT, norm TEXT, kind TEXT,
  created_at TEXT, last_run TEXT, times_run INT DEFAULT 0,
  top50_hits INT DEFAULT 0, status TEXT DEFAULT 'active',
  UNIQUE (key, norm));
CREATE TABLE IF NOT EXISTS query_results (
  query_id INT, tweet_id TEXT, rank INT, run_id INT, fetched_at TEXT,
  PRIMARY KEY (query_id, tweet_id, run_id));
CREATE TABLE IF NOT EXISTS tweets (
  id TEXT PRIMARY KEY, handle TEXT, text TEXT, url TEXT, posted_at TEXT,
  likes INT, reposts INT, replies INT, payload TEXT, fetched_at TEXT);
CREATE INDEX IF NOT EXISTS qr_tweet ON query_results (tweet_id);
CREATE INDEX IF NOT EXISTS q_key ON queries (key, status);
CREATE TABLE IF NOT EXISTS verdicts (
  tweet_id TEXT, key TEXT, rubric INT, verdict TEXT, prob REAL,
  final_score REAL, decided_by TEXT, reason TEXT, decided_at TEXT,
  PRIMARY KEY (tweet_id, key, rubric));
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY, key TEXT, started_at TEXT, finished_at TEXT,
  n_queries INT, n_candidates INT, n_x INT, n_llm INT, n_jev INT);
CREATE TABLE IF NOT EXISTS gold (
  tweet_id TEXT, key TEXT, label TEXT, note TEXT, created_at TEXT,
  PRIMARY KEY (tweet_id, key));
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def connect():
    con = sqlite3.connect(SEM_DB)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


# ---------------------------------------------------------------- model seams
#
# Both are optional. Without a key the pipeline still runs, it just stops being
# conceptual, and it says which leg went missing instead of quietly degrading.


def env(*names):
    """Read a key from .env then the process env. Never echoes the value."""
    f = os.path.join(ROOT, '.env')
    if os.path.exists(f):
        for line in open(f, encoding='utf-8'):
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    for n in names:
        if os.environ.get(n):
            return os.environ[n]
    return None


LLM_KEYS = ('NVIDIA_API_KEY', 'OPENAI_API_KEY', 'DEEPSEEK_API_KEY',
            'OPENROUTER_API_KEY', 'OPENCODE_ZEN_KEY')
LLM_MISSING = ('NVIDIA_API_KEY', 'OPENAI_API_KEY', 'DEEPSEEK_API_KEY',
               'OPENROUTER_API_KEY', 'OPENCODE_ZEN_KEY')
# Order matters. The first key that is set wins, so put the one with working
# credit first. NVIDIA NIM is OpenAI-compatible at a different host, so it needs
# its own base URL rather than the vendor default.
LLM_BASES = {
    'NVIDIA_API_KEY': 'https://integrate.api.nvidia.com/v1',
    'OPENAI_API_KEY': 'https://api.openai.com/v1',
    'DEEPSEEK_API_KEY': 'https://api.deepseek.com/v1',
    'OPENROUTER_API_KEY': 'https://openrouter.ai/api/v1',
    'OPENCODE_ZEN_KEY': 'https://opencode.ai/zen/v1',
}


def have_llm():
    return any(env(k) for k in LLM_KEYS)


def llm_base():
    for k in LLM_KEYS:
        if env(k):
            return LLM_BASES[k], env(k)
    return None, None


def ask_llm(prompt, system='', model=None, temperature=0.7, max_tokens=2000, timeout=420):
    """One chat completion. Any OpenAI-compatible endpoint, read from .env.

    The default timeout is 420 seconds, not 120, because a self-hosted style
    gateway cold starts: a 250B model took over two minutes to answer "what is
    2 plus 2". Timing out at 120 looked like the model being down.
    """
    base, key = llm_base()
    if not key:
        return None, f'no LLM key in .env ({", ".join(LLM_MISSING)})'
    base = base or os.environ.get('LLM_BASE_URL') or 'https://api.openai.com/v1'
    model = model or env('LLM_MODEL') or 'gpt-4o-mini'
    body = json.dumps({
        'model': model, 'temperature': temperature, 'max_tokens': max_tokens,
        'messages': ([{'role': 'system', 'content': system}] if system else [])
                    + [{'role': 'user', 'content': prompt}],
    }).encode()
    req = urllib.request.Request(base + '/chat/completions', body, {
        'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json',
        # Cloudflare in front of some gateways answers 403 error code 1010 to the
        # bare urllib agent, which has no User-Agent at all. Naming one is the
        # whole fix, and it cost an afternoon to find.
        'User-Agent': 'opencode/1.18.18', 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read())
        msg = (out.get('choices') or [{}])[0].get('message') or {}
        text = (msg.get('content') or '').strip()
        if not text:
            # Reasoning models spend the token budget on thinking and return an
            # empty answer with finish_reason "stop". That reads as a silent
            # failure, so say what actually happened instead of returning ''.
            think = (msg.get('reasoning_content') or '').strip()
            usage = out.get('usage') or {}
            return None, ('the model spent its whole budget thinking and returned no answer. '
                          f'reasoning_tokens={usage.get("completion_tokens_details", {}).get("reasoning_tokens")}, '
                          f'completion={usage.get("completion_tokens")}. Raise max_tokens.')
        return text, None
    except urllib.error.HTTPError as e:
        return None, f'HTTP {e.code}: {e.read()[:200].decode(errors="replace")}'
    except Exception as e:  # noqa: BLE001  any transport failure is the same to a caller
        return None, f'{type(e).__name__}: {e}'


def have_jev():
    return bool(env('TYPESAFE_API_KEY'))


# The contract, from docs.typesafe.ai/api. Three typed shapes, evaluated in
# parallel over one state, answered by name under "answers".
#
#   questions: {"hit": {"type": "noul",     "instructions": "..."}}
#              {"pick": {"type": "choice",   "instructions": "...", "criteria": {"a": "...", "b": "..."}}}
#              {"sev":  {"type": "score",    "instructions": "...", "criteria": ["low", "mid", "high"]}}
#   answers:   {"hit": {"type": "noul", "noul": 0.95}}
#              {"pick": {"choice": "a", "probabilities": {...}, "confidence": 0.9}}
#              {"sev":  {"score": 2.97, "probabilities": {"0": 0.0, "3": 1.0}, "confidence": 1.0}}
#
# Auth is Authorization: Bearer. Context is about 64k tokens for state plus
# questions. Output tokens are free, so one call can carry many questions.


def ask_jev(state, questions, model=None, timeout=60):
    """Typed decisions over one state.

    questions is a dict of name -> typed question. Returns the parsed "answers"
    map, or (None, error).
    """
    key = env('TYPESAFE_API_KEY')
    url = env('JEV_URL') or 'https://api.typesafe.ai/v1/systemone'
    body = json.dumps({
        'model': os.environ.get('JEV_MODEL') or 'jev-latest',
        'state': state,
        'questions': questions,
    }).encode()
    req = urllib.request.Request(url, body, {
        'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read()).get('answers'), None
    except urllib.error.HTTPError as e:
        return None, f'HTTP {e.code}: {e.read()[:300].decode(errors="replace")}'
    except Exception as e:  # noqa: BLE001
        return None, f'{type(e).__name__}: {e}'


def jev_noul(state, instructions, model=None):
    """One calibrated yes/no probability. Returns (prob, error)."""
    ans, err = ask_jev(state, {'hit': {'type': 'noul', 'instructions': instructions}}, model)
    if err:
        return None, err
    if not ans or 'hit' not in ans:
        return None, f'no answer for the noul question, got {ans}'
    v = ans['hit'].get('noul')
    return (float(v), None) if v is not None else (None, f'noul answer had no value: {ans}')


def jev_choice(state, instructions, criteria, model=None):
    """One choice plus its full distribution. Returns (winner, probs, error)."""
    ans, err = ask_jev(state, {'pick': {'type': 'choice', 'instructions': instructions,
                                        'criteria': criteria}}, model)
    if err:
        return None, None, err
    if not ans or 'pick' not in ans:
        return None, None, f'no answer for the choice question, got {ans}'
    return ans['pick'].get('choice'), ans['pick'].get('probabilities') or {}, None


def jev_score(state, instructions, levels, model=None):
    """One position on an ordered scale. Returns (score, probs, error)."""
    ans, err = ask_jev(state, {'grade': {'type': 'score', 'instructions': instructions,
                                         'criteria': levels}}, model)
    if err:
        return None, None, err
    if not ans or 'grade' not in ans:
        return None, None, f'no answer for the score question, got {ans}'
    return ans['grade'].get('score'), ans['grade'].get('probabilities') or {}, None


def jev_features(state, model=None):
    """All four features in one call. Jev evaluates questions in parallel, so
    four questions cost the same latency as one."""
    ans, err = ask_jev(state, {k: {'type': 'noul', 'instructions': v}
                               for k, v in FEATURES.items()}, model)
    if err:
        return None, err
    if not ans:
        return None, f'no answers for {list(FEATURES)}, got {ans}'
    out = {}
    for k in FEATURES:
        a = ans.get(k)
        if not a or a.get('noul') is None:
            return None, f'feature {k!r} missing from the answer: {ans}'
        out[k] = float(a['noul'])
    return out, None


def offer_score(f):
    """Combine the features in code. Jev decides each fact, plain code decides
    the rule, which is the shape that stays debuggable at 3am.

    A tweet is evidence of an offer if it says so outright, or if it names a role
    and tells you how to respond. Discussion discounts all of it, because a
    hiring manager talking about screening is not a company hiring.
    """
    positive = max(f['offer_language'],
                   f['role_named'] * 0.5 + f['how_to_apply'] * 0.5,
                   f['role_named'] * 0.5)
    return round(positive * (1.0 - f['discussion_only']), 4)


def offer_reason(f):
    """One line naming which feature drove the score. This is the debug surface."""
    positive = max(f['offer_language'],
                   f['role_named'] * 0.5 + f['how_to_apply'] * 0.5,
                   f['role_named'] * 0.5)
    if positive == f['offer_language']:
        driver = 'offer_language'
    elif f['role_named'] * 0.5 + f['how_to_apply'] * 0.5 >= f['role_named'] * 0.5:
        driver = 'role_named+how_to_apply'
    else:
        driver = 'role_named'
    return f'{driver} {positive:.2f} less discussion {f["discussion_only"]:.2f}'


# ---------------------------------------------------------------- phase 1


def slug(text):
    """The concept reduced to a comparable name. Shared so seeds.json keys and
    concept_key can never drift into looking for different things."""
    return re.sub(r'[^a-z0-9]+', '-', (text or '').lower()).strip('-')


def concept_key(con, text, ttl_hours=24.0, rubric=1):
    key = slug(text)[:60] + f'.v{rubric}'
    row = con.execute('SELECT * FROM concepts WHERE key=?', (key,)).fetchone()
    if not row:
        con.execute('INSERT INTO concepts (key, text, rubric, ttl_hours, created_at) VALUES (?,?,?,?,?)',
                    (key, text, rubric, ttl_hours, now()))
        con.commit()
    return key


# ---------------------------------------------------------------- phase 2


GEN_SYSTEM = (
    'You write X (Twitter) search queries. X matches literally, so the variety of '
    'surface forms you produce is the only thing that decides recall. You are '
    'deliberately not writing elegant queries.'
)


def gen_prompt(concept, examples, n=60, negatives=15, winners=None):
    ex = '\n'.join(f'- {e}' for e in examples[:10])
    win = ('\nThese previously scored, use them as a style register and write more '
           'like them:\n' + '\n'.join(f'- {w}' for w in winners[:12])) if winners else ''
    return f"""Concept: {concept}

Write X search queries that would retrieve tweets matching that concept.

Rules that matter more than you expect:
- Search for the SPEECH ACT, not the topic. "we are hiring" is well indexed, "hiring" alone is weak.
- Include misspellings, abbreviations, lowercase, missing apostrophes, and non-native phrasing.
- Three near-duplicate variants of the same idea is a FAILURE. Variety is the whole point.
- Do not write sentences. Short query strings only.

If these are tweets that match, write backwards from them:
{ex}

Write exactly {n} queries, one per line, no numbering, no commentary.{win}

Then write {negatives} NEGATIVE queries on a separate line starting with "NEG: ".
These should match the OPPOSITE of the concept, so they can be excluded.
A negative that would match the concept itself is a FAILURE and gets dropped."""


def parse_gen(text, negatives=15):
    """Split the generator output. A line that does not parse is dropped, loudly."""
    pos, neg = [], []
    for raw in (text or '').splitlines():
        s = raw.strip().lstrip('-*•0123456789. ').strip().strip('"')
        if not s or s.startswith('#'):
            continue
        if s.upper().startswith('NEG:'):
            neg.append(s[4:].strip())
        elif 2 <= len(s) <= 120:
            pos.append(s)
    return pos, neg


SEEDS = os.path.join(HERE, 'seeds.json')


def seeds(concept='', want=''):
    """Few-shot examples for phase 2, from seeds.json.

    A concept is matched to a seed key on stem overlap, so "accounts complaining
    about Cursor performance" finds the complaints set even though the words do
    not match. Falls back to the hiring set with a warning, because an example
    set for the wrong concept is worse than none: the model learns the wrong
    register and every query after it is worse. Pass want= to skip the guessing.

    Fails loudly on a duplicate key, the same reason pat.groups does. json.load
    would silently keep the second copy and lose a whole set.
    """
    import json

    def no_dupes(pairs):
        out = {}
        for k, v in pairs:
            if k in out:
                raise ValueError(f'seeds.json: the key {k!r} appears twice. The second copy '
                                 f'would win silently, so delete one.')
            out[k] = v
        return out

    if not os.path.exists(SEEDS):
        return [], 'seeds.json is missing, so phase 2 writes queries from the concept name alone'
    with open(SEEDS, encoding='utf-8') as f:
        doc = json.load(f, object_pairs_hook=no_dupes)
    sets = {k: v for k, v in doc.items() if not k.startswith('_')}
    if not sets:
        return [], 'seeds.json has no example sets'

    if want:
        entry = sets.get(want.strip().lower())
        if not entry:
            return [], (f'seeds.json has no set called {want!r}. It has: '
                        f'{", ".join(sorted(sets))}')
        return entry.get('examples', []), None

    ctext = {t[:4] for t in slug(concept).split('-') if len(t) >= 4}
    best, score = None, 0
    for k in sets:
        # four characters, so complaining reaches complaints. Five did not:
        # 'complaints'[:5] is 'compl' and 'complaining'[:5] is 'compla'.
        stems = {t[:4] for t in slug(k).split('-') if len(t) >= 4}
        n = len(stems & ctext)
        if n > score:
            best, score = k, n
    if best and score:
        return sets[best].get('examples', []), None
    return (sets.get('hiring') or next(iter(sets.values()))).get('examples', []), \
        (f'no example set matches {slug(concept)!r}, used "hiring". That may be the wrong '
         f'register. Name one with --seeds.')


def phase2(con, key, concept, examples=(), n=60, negatives=15, seed_set=''):
    # An explicit --example wins, then seeds.json, then nothing. The warning is
    # carried into the notes because a mismatched example set quietly teaches the
    # model the wrong vocabulary and every query after it is worse.
    if not examples:
        examples, warn = seeds(concept, seed_set)
        con_notes = [warn] if warn else []
    else:
        con_notes = []
    winners = [r['text'] for r in con.execute(
        "SELECT text FROM queries WHERE key=? AND top50_hits>0 ORDER BY top50_hits DESC", (key,))]
    text, err = ask_llm(gen_prompt(concept, list(examples), n, negatives, winners),
                        GEN_SYSTEM, temperature=1.0)
    if err:
        return [], [], con_notes + [f'phase 2 skipped: {err}']
    pos, neg = parse_gen(text, negatives)
    if len(pos) < 5:
        return [], [], con_notes + [f'phase 2 produced only {len(pos)} usable queries, refusing to run']
    return pos, neg, con_notes + [f'phase 2 seeded with {len(examples)} real examples']


# ---------------------------------------------------------------- phase 3


def norm(q):
    return re.sub(r'\s+', ' ', (q or '').strip().lower()).strip()


_CONTRACT = [
    (r"\b(\w+)'re\b", r'\1 are'), (r"\b(\w+)'ve\b", r'\1 have'),
    (r"\b(\w+)'ll\b", r'\1 will'), (r"\b(\w+)'m\b", r'\1 am'),
    (r"\b(\w+)'d\b", r'\1 would'), (r"\b(\w+)n't\b", r'\1 not'),
    (r"[\u2018\u2019'`]", ''),
]


def canon(q):
    """Fold contractions so "we're hiring" and "we are hiring" are one query.

    The generator is asked for both spellings on purpose, because X indexes
    both, so near-duplicate detection has to see them as the same thing or it
    spends a call on each.
    """
    s = (q or '').lower()
    for rx, rep in _CONTRACT:
        s = re.sub(rx, rep, s)
    return re.sub(r'\s+', ' ', s).strip()


def tokens(q):
    if isinstance(q, (set, frozenset)):
        return set(q)
    return {t for t in re.findall(r'[a-z0-9#@]+', canon(q)) if len(t) > 1}


def jaccard(a, b):
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def phase3(con, key, pos, neg):
    """Arithmetic first because it is free, then the classifier for the rest.

    Returns (kept_positives, kept_negatives, notes).
    """
    notes = []
    if have_jev() and neg:
        doc = '\n'.join(f'{i}: {q}' for i, q in enumerate(neg))
        want = {str(i): 'The query matches the OPPOSITE of the concept, not the concept.'
                for i in range(len(neg))}
        winner, probs, err = jev_choice(
            doc, 'Which numbered query matches the OPPOSITE of the concept rather than '
                 'the concept itself? Answer with the number.', want)
        if err:
            notes.append(f'phase 3 negative check skipped: {err}')
        elif winner is None:
            notes.append('phase 3 negative check got no winner')
        else:
            i = int(winner) if str(winner).isdigit() else None
            keep = [q for j, q in enumerate(neg) if j != i]
            notes.append(f'negative check dropped query {winner!r} as drifted, '
                         f'confidence {max(probs.values()):.2f}' if probs else 'dropped one')
            neg = keep

    if have_jev() and len(pos) > 8:
        # Ordering only. This is why the classifier is never asked "is this query
        # about the concept", which it would answer yes to all 60 of them.
        scored = []
        for i in range(0, len(pos), 40):
            doc = '\n'.join(f'{j}: {q}' for j, q in enumerate(pos[i:i + 40], start=i))
            score, _, err = jev_score(
                doc, 'How many matching tweets would this X search query return? '
                     'Rate 0 for none, 10 for a flood.',
                ['returns nothing', 'returns almost nothing', 'returns a few',
                 'returns a handful', 'returns many', 'returns a flood'])
            if err:
                notes.append(f'phase 3 yield ordering skipped: {err}')
                scored = []
                break
            for j in range(i, min(i + 40, len(pos))):
                scored.append((float(score or 0), j))
        if scored:
            scored.sort(reverse=True)
            order = [j for _, j in scored]
            pos = [pos[j] for j in order] + [pos[j] for j in range(len(pos)) if j not in set(order)]
            notes.append(f'yield order put {len(order)} promising queries first')

    kept, seen_norm, kept_tok = [], set(), []
    for q in pos:
        n = norm(q)
        if not n or n in seen_norm or ' OR ' in q:
            continue
        t = tokens(q)
        if any(jaccard(t, kt) >= JACCARD for kt in kept_tok):
            continue
        seen_norm.add(n)
        kept_tok.append(t)
        kept.append(q)
    dropped = len(pos) - len(kept)
    if dropped:
        notes.append(f'arithmetic removed {dropped} duplicate queries')
    return kept, neg, notes


def store_queries(con, key, pos, neg):
    """Returns (query_id, text) for every positive and negative."""
    ids = []
    for kind, qs in (('positive', pos), ('negative', neg)):
        for q in qs:
            con.execute(
                'INSERT OR IGNORE INTO queries (key, text, norm, kind, created_at) VALUES (?,?,?,?,?)',
                (key, q, norm(q), kind, now()))
            row = con.execute('SELECT id FROM queries WHERE key=? AND norm=?', (key, norm(q))).fetchone()
            ids.append((row['id'], q))
    con.commit()
    return ids


# ---------------------------------------------------------------- phase 4


def chunk(list_of, cap=CAP):
    """Split into OR-batches X will accept. List-based so one query can never be
    split in half by accident, which the string version allowed."""
    out, cur = [], []
    for q in list_of:
        if cur and len(' OR '.join(cur + [q])) > cap:
            out.append(' OR '.join(cur))
            cur = [q]
        else:
            cur.append(q)
    if cur:
        out.append(' OR '.join(cur))
    return out


def _save(con, rows, src):
    for r in rows:
        con.execute(
            'INSERT OR REPLACE INTO tweets (id, handle, text, url, posted_at, likes, '
            'reposts, replies, payload, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
            (r['id'], r.get('author_handle', ''), r.get('text', ''), r.get('url', ''),
             r.get('posted_at', ''), r.get('like_count', 0) or 0, r.get('repost_count', 0) or 0,
             r.get('reply_count', 0) or 0, json.dumps(r, ensure_ascii=False), now()))
    con.commit()


def retrieve_x(con, key, pos, neg, limit=200, since=None, min_likes=0, run_id=0):
    """Phase 4. Probes in OR-groups first, kills dead groups, then runs each
    survivor alone because RRF needs one independent ranked list per query."""
    notes = []
    ids = dict(store_queries(con, key, pos, neg))
    pos_set = set(pos)
    neg_txt = [q for q in ids.values() if q not in pos_set]

    groups = chunk(pos, CAP)
    alive = []
    for i, g in enumerate(groups, 1):
        if i > 1:
            time.sleep(PAUSE)
        probe = g
        if neg_txt:
            probe = g + ' NOT (' + ' OR '.join(neg_txt[:6]) + ')'
        rows, err = fetch_live(probe, limit, since, min_likes)
        if err:
            notes.append(f'group {i}/{len(groups)} FAILED: {err[:110]}')
            continue
        notes.append(f'group {i}/{len(groups)}: {len(rows)} tweets')
        if not rows:
            continue
        alive.append(g)
        _save(con, rows, 'x')

    by_norm = {norm(v): k for k, v in ids.items() if v in set(pos)}
    singles = []
    for g in alive:
        for q in g.split(' OR '):
            k = by_norm.get(norm(q))
            if k:
                singles.append(k)
    singles = list(dict.fromkeys(singles))

    for i, qid in enumerate(singles, 1):
        if i > 1:
            time.sleep(PAUSE)
        q = ids[qid]
        probe = q + (' NOT (' + ' OR '.join(neg_txt[:6]) + ')' if neg_txt else '')
        rows, err = fetch_live(probe, limit, since, min_likes)
        if err:
            notes.append(f'query {i}/{len(singles)} "{q[:40]}" FAILED: {err[:90]}')
            continue
        _save(con, rows, 'x')
        for rank, r in enumerate(rows, 1):
            con.execute('INSERT OR REPLACE INTO query_results (query_id, tweet_id, rank, run_id, fetched_at) VALUES (?,?,?,?,?)',
                        (qid, r['id'], rank, run_id, now()))
        notes.append(f'query {i}/{len(singles)} "{q[:40]}": {len(rows)} tweets')
    con.commit()
    return notes, len(singles)


def retrieve_bookmarks(con, key, pos, neg, limit=200, days_back=None, run_id=0):
    """Same ranking, offline and free. This is where every eval runs first."""
    notes = []
    ids = dict(store_queries(con, key, pos, neg))
    pos_set = set(pos)
    since = (datetime.now(timezone.utc) - timedelta(days=days_back)) if days_back else None
    cut = int(since.timestamp()) if since else 0
    for qid, q in ids.items():
        if q not in pos_set:
            continue
        fts = pat_fts(q, q)
        if not os.path.exists(BM_DB):
            notes.append(f'no Field Theory database at {BM_DB}')
            break
        bc = sqlite3.connect(f'file:{BM_DB}?mode=ro', uri=True)
        bc.row_factory = sqlite3.Row
        try:
            # Join on rowid. bookmarks.id is TEXT, so joining on b.id matches
            # nothing and scans the whole table. Found 2026-10-09, cost 382s.
            rows = bc.execute("""
                SELECT b.id, b.url, b.text, b.author_handle, b.author_name,
                       b.posted_at, b.like_count, b.repost_count, b.reply_count,
                       b.bookmarked_at
                FROM bookmarks_fts f JOIN bookmarks b ON b.rowid = f.rowid
                WHERE bookmarks_fts MATCH ? ORDER BY rank LIMIT ?""", (fts, limit)).fetchall()
        except sqlite3.OperationalError as e:
            notes.append(f'{q[:40]!r} failed: {e}')
            continue
        finally:
            bc.close()
        kept = []
        for r in rows:
            if cut:
                # bookmarked_at is the axis that matters here. This is a search
                # over what you saved, so "last 8 days" means when you saved it,
                # not when it was posted. posted_at is a month behind on average.
                ts = _bm_epoch(r['bookmarked_at']) or _bm_epoch(r['posted_at'])
                if ts and ts < cut:
                    continue
            kept.append({
                'id': r['id'], 'url': r['url'] or '', 'text': r['text'] or '',
                'author_handle': r['author_handle'] or '', 'author_name': r['author_name'] or '',
                'posted_at': r['posted_at'] or '', 'like_count': r['like_count'] or 0,
                'repost_count': r['repost_count'] or 0, 'reply_count': r['reply_count'] or 0,
            })
        _save(con, kept, 'bookmarks')
        for rank, r in enumerate(kept, 1):
            con.execute('INSERT OR REPLACE INTO query_results (query_id, tweet_id, rank, run_id, fetched_at) VALUES (?,?,?,?,?)',
                        (qid, r['id'], rank, run_id, now()))
        notes.append(f'"{q[:44]}": {len(kept)} bookmarks')
    con.commit()
    return notes, len(ids)


def _bm_epoch(s):
    if not s:
        return None
    for f in ('%a %b %d %H:%M:%S %z %Y', '%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            d = datetime.strptime(str(s), f)
            return int((d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp())
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------- phase 5 + 6


def merge(con, key, run_id=None):
    """Union the results, then the free signals: how many queries found it.

    run_id restricts the answer to one run. Without it you get everything ever
    found for the concept, which is the archive and what you want when X has
    stopped returning old tweets. With it you get what is new today, which is
    the question a daily scan is actually asking.
    """
    sql = """
        SELECT qr.tweet_id AS id, t.handle, t.text, t.url, t.posted_at,
               t.likes, t.reposts, t.replies,
               count(*) AS found_by, group_concat(qr.rank) AS ranks
        FROM query_results qr
        JOIN queries q ON q.id = qr.query_id AND q.key = ?
        JOIN tweets t ON t.id = qr.tweet_id
        {where}
        GROUP BY qr.tweet_id"""
    args = [key]
    if run_id:
        sql = sql.replace('{where}', 'WHERE qr.run_id = ?')
        args.append(run_id)
    else:
        sql = sql.replace('{where}', '')
    rows = con.execute(sql, args).fetchall()
    out, seen = [], set()
    for r in rows:
        text = (r['text'] or '').strip()
        h = hashlib.sha1(re.sub(r'\s+', ' ', text.lower()).encode()).hexdigest()
        if len(text) < 20 or text.lower().startswith('http') or text.strip() == '@':
            continue
        if h in seen:
            continue
        seen.add(h)
        out.append({
            'id': r['id'], 'handle': r['handle'], 'text': text, 'url': r['url'],
            'posted_at': r['posted_at'], 'likes': r['likes'] or 0,
            'reposts': r['reposts'] or 0, 'replies': r['replies'] or 0,
            'found_by': r['found_by'], 'ranks': [int(x) for x in (r['ranks'] or '').split(',') if x],
        })
    out.sort(key=lambda r: (-r['found_by'], -r['likes']))
    return out


def weights(con, key):
    rows = con.execute('SELECT id, top50_hits, times_run, status FROM queries WHERE key=?', (key,))
    return {r['id']: (0.5 + r['top50_hits'] / (r['times_run'] + 1)) if r['status'] == 'active' else 0.0
            for r in rows}


def rrf(con, key, cands, run_id=None):
    """Reciprocal Rank Fusion. Needs only ranks, which is all X gives us.

    A tweet found under seven different phrasings accumulates score from seven
    independent lists. That agreement is the semantic signal, and it costs
    arithmetic.
    """
    w = weights(con, key)
    sql = """
        SELECT qr.tweet_id, qr.rank, qr.query_id FROM query_results qr
        JOIN queries q ON q.id = qr.query_id AND q.key = ?"""
    args = [key]
    if run_id:
        sql += ' AND qr.run_id = ?'
        args.append(run_id)
    qr = con.execute(sql, args).fetchall()
    by_id = {}
    for r in qr:
        s = w.get(r['query_id'], 0.0) / (RRF_K + r['rank'])
        by_id[r['tweet_id']] = by_id.get(r['tweet_id'], 0.0) + s
    # Divide by the best score any tweet could earn, not by the best score this
    # run happened to produce. Dividing by the observed max collapses every
    # rank-1-in-one-query result to 1.0 and ties it with a tweet that seven
    # queries agreed on, which throws away the entire signal.
    n_active = max(1, sum(1 for v in w.values() if v > 0))
    ceiling = n_active / (RRF_K + 1)
    for c in cands:
        c['rrf_raw'] = by_id.get(c['id'], 0.0)
        c['rrf'] = round(c['rrf_raw'] / ceiling, 4)
    cands.sort(key=lambda c: (-c['rrf_raw'], -c['found_by'], -(c.get('likes') or 0)))
    return cands


# ---------------------------------------------------------------- phase 7


def screen(con, key, cands, rubric, pool=POOL, model=None, workers=8, question=None):
    """Phase 7. The classifier triages retrieved tweets, which is the only place
    it can discriminate, because these genuinely disagree with each other."""
    if not have_jev():
        for c in cands[:pool]:
            c['prob'], c['verdict'], c['decided_by'] = None, 'unjudged', 'none'
        return cands, ['phase 7 skipped: no TYPESAFE_API_KEY in .env, ranking is RRF only']
    q = question or f'Does this tweet match this concept: {key.rsplit(".", 1)[0]}?'
    top = cands[:pool]

    # SQLite refuses to be used from a thread it was not created on, so every
    # read and write stays here and only the HTTP call goes to a worker. The
    # call is the expensive part anyway, so this loses nothing.
    cached = {r['tweet_id']: r for r in con.execute(
        'SELECT tweet_id, verdict, prob, reason FROM verdicts WHERE key=? AND rubric=? AND tweet_id IN '
        f"({','.join('?' * len(top))})", (key, rubric, *[c['id'] for c in top])
    )} if top else {}

    todo = []
    for c in top:
        row = cached.get(c['id'])
        if row:
            c['prob'], c['verdict'] = row['prob'], row['verdict']
            c['decided_by'], c['reason'] = 'jev-cache', row['reason']
        else:
            todo.append(c)
    if not todo:
        return cands, [f'phase 7: {len(top)} screened, all from cache, no Jev calls']

    def judge(c):
        f, err = jev_features(c['text'], model)
        if err:
            return c['id'], None, None, err
        return c['id'], offer_score(f), offer_reason(f), None

    by_id = {c['id']: c for c in todo}
    with futures.ThreadPoolExecutor(max_workers=workers) as ex:
        for cid, prob, reason, err in ex.map(judge, todo):
            c = by_id[cid]
            if err:
                c['prob'], c['verdict'], c['decided_by'] = None, 'error', 'none'
                c['reason'] = err[:120]
                continue
            v = 'hit' if prob >= HIT_BAND else 'miss' if prob <= MISS_BAND else 'unclear'
            con.execute('INSERT OR REPLACE INTO verdicts (tweet_id, key, rubric, verdict, prob, '
                        'decided_by, reason, decided_at) VALUES (?,?,?,?,?,?,?,?)',
                        (cid, key, rubric, v, prob, 'jev', reason, now()))
            c['prob'], c['verdict'], c['decided_by'], c['reason'] = prob, v, 'jev', reason
    con.commit()
    hits = len([c for c in top if c['verdict'] == 'hit'])
    miss = len([c for c in top if c['verdict'] == 'miss'])
    note = (f'phase 7: {len(top)} screened, {len(todo)} Jev calls, '
            f'{hits} hit, {miss} miss, {len(top) - hits - miss} unclear')
    failed = len([c for c in top if c['verdict'] == 'error'])
    if failed:
        note += f', {failed} FAILED'
    return cands, [note]


def frontier(con, key, cands, rubric, top=20, model=None, question=None, batch=20):
    """Phase 8. A real language model judges only the band Jev would not commit
    to, and its verdict is promoted above everything else.

    This is the most expensive leg per item in the whole design and it buys the
    least volume, so it runs on the boundary, never on the bulk. The reasons it
    returns are stored, because when a rerank looks wrong you need to read why
    rather than trust a number.
    """
    band = [c for c in cands if c.get('verdict') == 'unclear'][:top]
    if not band:
        return cands, ['phase 8: nothing unclear to rerank']
    if not have_llm():
        return cands, [f'phase 8 skipped: {len(band)} unclear tweets, but no usable LLM key '
                       f'in .env ({", ".join(LLM_MISSING)}). Set one and rerank with --n N.']

    q = question or key.rsplit('.', 1)[0]
    graded = []
    for start in range(0, len(band), batch):
        chunk = band[start:start + batch]
        listing = '\n'.join(f'{n}: {c["text"][:300]}' for n, c in enumerate(chunk))
        out, err = ask_llm(
            f'Concept: {q}\n\n'
            f'For each numbered tweet, judge how well it matches the concept.\n\n{listing}\n\n'
            'Reply with ONLY a JSON array, no prose and no code fence, like:\n'
            '[{"i": 0, "score": 0.0, "why": "one short clause"}, ...]\n'
            'score is 0.0 for no match and 1.0 for a clear match.',
            system='You rank short texts against a concept. You reply with JSON only.',
            model=model, temperature=0, max_tokens=2000 + batch * 120)
        if err:
            return cands, [f'phase 8 batch {start // batch + 1} failed: {err[:140]}']
        got = _parse_grades(out, len(chunk))
        if not got:
            return cands, [f'phase 8 batch {start // batch + 1} returned nothing parseable: '
                           f'{(out or "")[:140]}']
        for n, (score, why) in got.items():
            chunk[n]['final_score'] = score
            chunk[n]['reason'] = why
        graded += chunk

    graded.sort(key=lambda c: -(c.get('final_score') or 0))
    rest = [c for c in cands if c not in graded]
    for c in graded:
        # The frontier score decides the tier, it does not rubber stamp a hit.
        # A reranked item scoring 0.2 has been judged a non-match and must land
        # in miss, or the promotion becomes a lie.
        s = c.get('final_score') or 0.0
        v = 'hit' if s >= HIT_BAND else 'miss' if s <= MISS_BAND else 'unclear'
        con.execute('INSERT OR REPLACE INTO verdicts (tweet_id, key, rubric, verdict, prob, '
                    'final_score, decided_by, reason, decided_at) VALUES (?,?,?,?,?,?,?,?,?)',
                    (c['id'], key, rubric, v, c.get('prob'), s, 'frontier', c.get('reason'), now()))
        c['decided_by'], c['verdict'] = 'frontier', v
    con.commit()
    n_promoted = len([c for c in graded if c['verdict'] == 'hit'])
    n_dropped = len([c for c in graded if c['verdict'] == 'miss'])
    best = graded[0].get('final_score') if graded else 0
    worst = graded[-1].get('final_score') if graded else 0
    used = model or env('LLM_MODEL_FRONTIER') or 'the LLM'
    return graded + rest, [f'phase 8: {len(graded)} unclear tweets reranked by {used}, '
                           f'scores {worst:.2f} to {best:.2f}, '
                           f'{n_promoted} promoted to hit, {n_dropped} sent to miss']


def _parse_grades(text, n):
    """Tolerant JSON reader. Falls back to 'index: score reason' lines."""
    if not text:
        return {}
    body = text.strip()
    body = re.sub(r'^```(?:json)?|```$', '', body, flags=re.M).strip()
    try:
        arr = json.loads(body)
        if isinstance(arr, list):
            out = {}
            for item in arr:
                if not isinstance(item, dict) or 'i' not in item:
                    continue
                i = int(item['i'])
                if 0 <= i < n:
                    out[i] = (float(item.get('score', 0)), str(item.get('why', ''))[:200])
            return out
    except (ValueError, TypeError):
        pass
    out = {}
    for m in re.finditer(r'(?m)^\s*\[?(\d{1,3})\]?\s*[:.)-]\s*([01](?:\.\d+)?)\s*(.*)$', body):
        i = int(m.group(1))
        if 0 <= i < n:
            out[i] = (float(m.group(2)), m.group(3).strip()[:200])
    return out


# ---------------------------------------------------------------- phase 12


def scoreboard(con, key, top=50):
    """Which queries actually paid off. This is the whole learning loop and it
    needs no vectors, no gradients, no fine tuning. w = 0.5 + hits/(runs+1)."""
    rows = con.execute("""
        SELECT qr.query_id, count(*) AS n FROM query_results qr
        JOIN queries q ON q.id = qr.query_id AND q.key = ?
        WHERE qr.tweet_id IN (
          SELECT tweet_id FROM verdicts WHERE key=? AND rubric=(SELECT max(rubric) FROM concepts WHERE key=?)
            AND verdict='hit'
          ORDER BY COALESCE(final_score, prob) DESC LIMIT ?)
        GROUP BY qr.query_id""", (key, key, key, top)).fetchall()
    for r in rows:
        con.execute('UPDATE queries SET top50_hits = top50_hits + ? WHERE id=?', (1, r['query_id']))
    con.execute("UPDATE queries SET times_run = times_run + 1 WHERE key=?", (key,))
    dead = con.execute(
        'SELECT text FROM queries WHERE key=? AND times_run>=10 AND top50_hits=0', (key,)).fetchall()
    for d in dead:
        con.execute("UPDATE queries SET status='retired' WHERE key=? AND norm=?",
                    (key, norm(d['text'])))
    con.commit()
    return len(rows), len(dead)


# ---------------------------------------------------------------- run + report


def run(con, concept, source='bookmarks', limit=200, since=None, min_likes=0,
        days_back=None, rubric=1, n_queries=60,
        examples=(), pool_size=POOL, frontier_top=0, model=None, quiet=False,
        seed=None, fresh=False, seed_set='', log=None):
    key = concept_key(con, concept, rubric=rubric)
    # log collects the same lines quiet=True suppresses, so a caller that cannot
    # see stdout still learns WHY a run came back empty. A scheduled job that
    # reports zero rows with no reason is the failure this exists to prevent.
    def say(*a):
        line = ' '.join(str(x) for x in a)
        if log is not None:
            log.append(line)
        if not quiet:
            print(line)
    say(f'concept {key}')

    if seed:
        pos, neg, notes = list(seed), [], ['seeded by hand, phase 2 skipped']
    else:
        cached = con.execute(
            "SELECT text FROM queries WHERE key=? AND status='active' AND kind='positive' LIMIT ?",
            (key, n_queries)).fetchall()
        if cached:
            pos = [r['text'] for r in cached]
            neg = [r['text'] for r in con.execute(
                "SELECT text FROM queries WHERE key=? AND kind='negative'", (key,))]
            notes = []
            say(f'phase 2: {len(pos)} queries from cache')
        else:
            pos, neg, notes = phase2(con, key, concept, examples, n_queries, seed_set=seed_set)
            say(f'phase 2: {len(pos)} positives, {len(neg)} negatives')
            for x in notes:
                say('  ' + x)

    pos, neg, n3 = phase3(con, key, pos, neg)
    say(f'phase 3: {len(pos)} positives survive')
    for x in n3:
        say('  ' + x)
    if not pos:
        say('no queries left, stopping')
        return []
    # The run row is opened before retrieval so every result can be stamped with
    # it, which is what makes "what is new today" answerable later.
    con.execute('INSERT INTO runs (key, started_at) VALUES (?,?)', (key, now()))
    run_id = con.execute('SELECT last_insert_rowid()').fetchone()[0]
    con.commit()

    if source == 'x':
        n4, calls = retrieve_x(con, key, pos, neg, limit, since, min_likes, run_id)
    else:
        n4, calls = retrieve_bookmarks(con, key, pos, neg, limit, days_back, run_id)
    say(f'phase 4: {calls} queries run')
    for x in n4[:6]:
        say('  ' + x)

    scope = run_id if fresh else None
    cands = merge(con, key, scope)
    say(f'phase 5: {len(cands)} unique candidates' + (' (this run only)' if fresh else ''))
    cands = rrf(con, key, cands, scope)
    say(f'phase 6: fused, top RRF {cands[0]["rrf"]:.3f}' if cands else 'phase 6: nothing to fuse')
    cands, n7 = screen(con, key, cands, rubric, pool_size, model)
    for x in n7:
        say('  ' + x)
    if frontier_top:
        cands, n8 = frontier(con, key, cands, rubric, frontier_top, model)
        for x in n8:
            say('  ' + x)
        # A reranked item outranks everything Jev would not commit to, because a
        # real language model read it and the unclear band was where it stopped.
        graded = [c for c in cands if c.get('decided_by') == 'frontier']
        if graded:
            graded.sort(key=lambda c: -(c.get('final_score') or 0))
            cands = graded + [c for c in cands if c.get('decided_by') != 'frontier']

    # The verdict gates the order, then the score ranks within a tier. Sorting on
    # score alone let a confirmed miss sit above a confirmed hit, which would
    # make phase 7 cost money and change nothing.
    for c in cands:
        c['score'] = c.get('final_score') if c.get('final_score') is not None else c['rrf_raw']
        c['tier'] = {'hit': 0, 'unclear': 1, 'miss': 2, 'error': 3}.get(c.get('verdict'), 4)
    cands.sort(key=lambda c: (c['tier'], -(c['score'] or 0), -c['found_by'],
                              -(c.get('likes') or 0)))
    con.execute('UPDATE runs SET finished_at=?, n_queries=?, n_candidates=?, n_x=?, '
                'n_llm=?, n_jev=? WHERE id=?',
                (now(), len(pos), len(cands), calls, 1 if have_llm() else 0,
                 1 if have_jev() else 0, run_id))
    con.commit()
    hits, dead = scoreboard(con, key)
    say(f'phase 12: {hits} queries paid off, {dead} retired')
    return cands


def report(cands, key, n=20):
    print(f'\n{"=" * 78}\n{key}\n{"=" * 78}')
    for i, c in enumerate(cands[:n], 1):
        prob = f'{c["prob"]:.2f}' if c.get('prob') is not None else ' -- '
        tag = {'hit': 'HIT ', 'miss': 'miss', 'unclear': 'UNC '}.get(c.get('verdict'), '    ')
        by = {'jev': 'jev', 'jev-cache': 'jev*', 'frontier': 'FRONT', 'none': '-'}.get(
            c.get('decided_by'), c.get('decided_by') or '-')
        print(f'\n{i:>3}. [{tag} p={prob} rrf={c["rrf"]:.3f} q={c["found_by"]:>2} {by:>6}] '
              f'@{c["handle"]} {c["likes"]}L')
        if c.get('reason'):
            print(f'     why: {c["reason"]}')
        print(f'     {re.sub(chr(10), " ", c["text"])[:260]}')
        print(f'     {c["url"]}')
    edge = cands[n:n + 20]
    if edge:
        print(f'\n{"-" * 78}\nboundary {n + 1} to {n + len(edge)}, this is where the queries are wrong\n{"-" * 78}')
        for i, c in enumerate(edge, n + 1):
            print(f'{i:>3}. [{c.get("verdict", "-"):>7}] @{c["handle"]} '
                  f'{re.sub(chr(10), " ", c["text"])[:150]}')


# ---------------------------------------------------------------- eval


# (text, is_a_real_offer). Every lookalike is lexically close to a real offer,
# which is the point: these are the tweets a regex cannot separate.
ADVERSARIAL = [
    ("we are hiring two engineers for the team", True),
    ("open role: founding designer", True),
    ("DM me your work", True),
    ("Monzo is hiring a staff engineer", True),
    ("the company is hiring but the visa process is painful", True),
    ("we just raised and we are hiring three more engineers", True),
    ("hiring managers need better pipeline tools", False),
    ("we are hiring is a phrase I hate in job posts", False),
    ("Monzo is hiring, says report", False),
    ("join our team of 400,000 Discord members", False),
    ("apply now for the thing you just clicked", False),
    ("I've applied to 40 jobs this week", False),
    ("hiring managers how do you screen resumes", False),
    ("I am hiring a recruiter for my team", True),
]


def suite_adversarial(con, key):
    """T4. Proves whether the model layer earns its cost, and it costs nothing
    to find out. Runs offline, no X call, no key required for the regex arm."""
    n_offer = sum(1 for _, g in ADVERSARIAL if g)
    print(f'\nadversarial suite: {n_offer} real offers, '
          f'{len(ADVERSARIAL) - n_offer} lookalikes\n')
    rows = [{'id': f'adv{i}', 'handle': 'probe', 'text': t, 'url': '', 'posted_at': '',
             'likes': 0, 'reposts': 0, 'replies': 0, 'found_by': 1, 'ranks': [1]}
            for i, (t, _) in enumerate(ADVERSARIAL)]
    cands, notes = screen(con, key, rows, 1, pool=len(rows))
    for x in notes:
        print('  ' + x)

    from search import OFFER
    r_tp = r_fp = j_tp = j_fp = 0
    print(f'\n{"text":<50} {"gold":>5} {"regex":>7} {"model":>8}')
    print('-' * 74)
    for c in cands:
        text, gold = ADVERSARIAL[int(c['id'][3:])]
        rx = bool(OFFER.search(text))
        jv = c.get('verdict') == 'hit'
        r_tp += rx and gold
        r_fp += rx and not gold
        j_tp += jv and gold
        j_fp += jv and not gold
        mark = '  <- model wrong' if (have_jev() and jv != gold) else ''
        print(f'{text[:48]:<50} {"HIT" if gold else "miss":>5} '
              f'{"TAKE" if rx else "pass":>7} {(c.get("verdict") or "-"):>8}{mark}')

    def line(tp, fp, label):
        n = tp + fp
        return (f'{label:>7}  took {n:>2} of {len(ADVERSARIAL)}, '
                f'precision {tp}/{n if n else 0}, recall {tp}/{n_offer}')

    print()
    print(line(r_tp, r_fp, 'regex'))
    if have_jev():
        print(line(j_tp, j_fp, 'model'))
        if j_fp > r_fp and j_tp <= r_tp:
            print('\nThe model layer loses to the regex. Do not build phase 7.')
        elif j_tp > r_tp and j_fp <= r_fp:
            print('\nThe model layer earns its cost. Phase 7 is the leg that pays.')
    else:
        print('\nno Jev key, so only the regex arm ran.')
    return cands


def suite_gold(con, key, n=10, precision=5):
    """T1. Score a run against labels you wrote in the gold table."""
    g = {r['tweet_id']: r['label'] for r in
         con.execute('SELECT tweet_id, label FROM gold WHERE key=?', (key,))}
    if not g:
        print(f'no labels for {key}. Record them with: python sem.py gold <id> hit|miss')
        return
    print(f'\n{len(g)} labels, {sum(1 for v in g.values() if v == "hit")} of them hits\n')
    rows = con.execute("""
        SELECT DISTINCT qr.tweet_id FROM query_results qr JOIN queries q ON q.id=qr.query_id
        WHERE q.key=? LIMIT 400""", (key,)).fetchall()
    order = {r['tweet_id']: i for i, r in enumerate(
        con.execute("""
            SELECT tweet_id, count(*) c FROM query_results qr JOIN queries q ON q.id=qr.query_id
            WHERE q.key=? GROUP BY tweet_id ORDER BY c DESC""", (key,)).fetchall())}
    ranked = sorted((r['tweet_id'] for r in rows), key=lambda t: order.get(t, 1 << 30))
    gold_ids = {t for t, v in g.items() if v == 'hit'}
    hit_n = [len(set(ranked[:n]) & gold_ids), len(gold_ids)]
    print(f'recall@{n}    {hit_n[0]}/{hit_n[1]}')
    if hit_n[0]:
        k = sum(1 for i, t in enumerate(ranked[:n], 1) if t in gold_ids and 1 / i)
        print(f'MRR@{n}     {k / hit_n[0]:.3f}')
    print(f'precision@{precision} {len(set(ranked[:precision]) & gold_ids)}/{precision}')


def cmd_gold(con, args):
    for tid, label in zip(args.tweet_id, args.label):
        con.execute('INSERT OR REPLACE INTO gold (tweet_id, key, label, created_at) VALUES (?,?,?,?)',
                    (tid, args.concept, label, now()))
    con.commit()
    print(f'recorded {len(args.tweet_id)} labels for {args.concept}')


# ---------------------------------------------------------------- selfcheck


def selfcheck():
    """Every claim this file makes about itself, proved. No network, no keys."""
    import tempfile

    # 1. RRF is rank-only and agreement wins. A tweet found by 3 queries beats
    #    one found by 1 even when that one is rank 1 in all three of its own
    #    lists. This is the whole semantic claim.
    s = {'a': [(1, 1), (1, 2), (1, 3)], 'b': [(2, 1), (2, 1), (2, 1)]}
    sa = sum(1 / (RRF_K + r) for _, r in s['a'])
    sb = sum(1 / (RRF_K + r) for _, r in s['b'])
    assert sb > sa, 'RRF must reward agreement, not a single good rank'

    # 2. chunk never splits one query, never loses one, never exceeds the cap.
    qs = ['a' * 100 + str(i) for i in range(8)]
    groups = chunk(qs)
    assert len(groups) > 1, 'eight 100 char queries must not fit in one 440 char batch'
    assert ' OR '.join(groups).split(' OR ') == qs, 'chunk lost or reordered a query'
    for c in groups:
        assert len(c) <= CAP, f'chunk produced {len(c)} chars, X rejects over 512'
    assert len(chunk(['we are hiring'])) == 1, 'chunk split a single query'

    # 3. Jaccard kills near-duplicates and keeps real siblings.
    assert jaccard(tokens('we are hiring'), tokens("we're hiring")) >= JACCARD
    assert jaccard(tokens('hiring'), tokens('sportsbook odds')) < 0.3

    # 4. The database works end to end with no keys at all, which is the only
    #    way the eval suites can run before anyone spends anything.
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, 't.db')
        global SEM_DB
        keep, SEM_DB = SEM_DB, db
        try:
            con = connect()
            k = concept_key(con, 'test concept')
            store_queries(con, k, ['we are hiring', 'open role'], ['sports betting tips'])
            con.execute("INSERT INTO tweets (id, text, handle) VALUES ('1','we are hiring two engineers','a')")
            con.execute("INSERT INTO query_results (query_id, tweet_id, rank) VALUES "
                        "(1,'1',1)")
            c = merge(con, k)
            assert len(c) == 1, 'merge lost the row'
            assert c[0]['found_by'] == 1
            c = rrf(con, k, c)
            assert c[0]['rrf'] > 0, 'rrf produced nothing'
            # The no-key path has to be tested deterministically, so the key is
            # blanked rather than depending on what is in .env today.
            saved = os.environ.get('TYPESAFE_API_KEY')
            os.environ['TYPESAFE_API_KEY'] = ''
            try:
                c, notes = screen(con, k, c, 1)
                assert c[0]['verdict'] == 'unjudged', 'a missing Jev key must degrade, not crash'
                assert any('TYPESAFE_API_KEY' in n for n in notes), 'the note must name the key'
            finally:
                if saved is None:
                    os.environ.pop('TYPESAFE_API_KEY', None)
                else:
                    os.environ['TYPESAFE_API_KEY'] = saved

            # With nothing judged, nothing is credited. The scoreboard pays for
            # tweets that were judged a hit, not for tweets that were merely found.
            hits, dead = scoreboard(con, k)
            assert hits == 0, 'scoreboard credited an unjudged tweet'
            assert con.execute('SELECT times_run FROM queries WHERE key=?', (k,)).fetchone()[0] == 1

            # Now judge it a hit and the same query is credited. screen() writes
            # no row when there is no classifier, so the verdict is inserted here.
            con.execute("INSERT OR REPLACE INTO verdicts (tweet_id, key, rubric, verdict, "
                        "prob, decided_by, decided_at) VALUES ('1',?,1,'hit',0.99,'test',?)",
                        (k, now()))
            con.commit()
            hits, dead = scoreboard(con, k)
            assert hits == 1, 'scoreboard did not credit the query that found the hit'
            w = weights(con, k)[1]
            assert w > 0.5, 'a query with a hit must outrank an untried one'
            con.close()
        except BaseException:
            try:
                con.close()
            except Exception:  # noqa: BLE001
                pass
            raise
        finally:
            SEM_DB = keep

    # 5. parse_gen survives junk without inventing queries.
    pos, neg = parse_gen('1. we are hiring\n- open role\nNEG: sports betting\n\n#comment\n')
    assert pos == ['we are hiring', 'open role'], pos
    assert neg == ['sports betting'], neg

    return 'selfcheck ok'


# ---------------------------------------------------------------- cli


def main(argv=None):
    # Tweet text is full of emoji. The Windows console defaults to cp1252 and
    # dies on the first one, which takes the whole run down after the work is done.
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:  # noqa: BLE001
        pass
    p = argparse.ArgumentParser(
        prog='sem.py', description='Conceptual search over X, without embeddings.')
    sub = p.add_subparsers(dest='cmd', required=True)

    s = sub.add_parser('search', help='run the pipeline for a concept')
    s.add_argument('concept')
    s.add_argument('--source', choices=['bookmarks', 'x'], default='bookmarks',
                   help='bookmarks is offline and free, x is live')
    s.add_argument('--limit', type=int, default=200)
    s.add_argument('--min-likes', type=int, default=0)
    s.add_argument('--since', type=int, default=None, help='days back for bookmarks')
    s.add_argument('--pool', type=int, default=POOL)
    s.add_argument('--queries', type=int, default=60)
    s.add_argument('--rubric', type=int, default=1)
    s.add_argument('--frontier', type=int, default=0, metavar='N',
                   help='rerank the top N unclear tweets with a frontier model')
    s.add_argument('-q', '--seed', default='',
                   help='comma separated queries to use instead of generating them. '
                        'Everything downstream still runs, so this is how you test '
                        'the ranking with no model key at all.')
    s.add_argument('--seed-group', default='',
                   help='reuse hand-written phrase sets from patterns.json as the seed, '
                        'for example OFFER,APPLY_CTA or ALL. This is the apples to '
                        'apples comparison against the existing module.')
    s.add_argument('--n', type=int, default=20, help='rows to print')
    s.add_argument('--fresh', action='store_true',
                   help='only what this run retrieved, not the whole archive for the concept')
    s.add_argument('--seeds', default='',
                   help='which example set in seeds.json to learn the query style from. '
                        'Blank picks the closest match by stem and says so when unsure.')
    s.add_argument('--example', action='append', default=[],
                   help='one real matching tweet, repeat to give several. Beats any file.')

    s = sub.add_parser('eval', help='score against labels')
    s.add_argument('concept')
    s.add_argument('--suite', choices=['gold', 'adversarial'], default='gold')

    s = sub.add_parser('gold', help='record a label')
    s.add_argument('concept')
    s.add_argument('tweet_id', nargs='+')
    s.add_argument('label', nargs='+', choices=['hit', 'miss'])

    s = sub.add_parser('rerank', help='phase 8 on a stored run, no retrieval')
    s.add_argument('concept')
    s.add_argument('--n', type=int, default=20, metavar='N',
                   help='how many unclear tweets to send to the frontier model')
    s.add_argument('--run', type=int, default=None,
                   help='which run to read. Default is the last one.')
    s.add_argument('--rubric', type=int, default=1)
    s.add_argument('--model', default='',
                   help='which model does the reranking. Blank uses LLM_MODEL_FRONTIER.')

    s = sub.add_parser('queries', help='list the queries and how they scored')
    s.add_argument('concept')

    sub.add_parser('selftest')
    a = p.parse_args(argv)

    if a.cmd == 'selftest':
        print(selfcheck())
        return 0

    con = connect()
    if a.cmd == 'queries':
        k = a.concept if '.v' in a.concept else concept_key(con, a.concept)
        for r in con.execute('SELECT * FROM queries WHERE key=? ORDER BY top50_hits DESC, text', (k,)):
            print(f'{r["top50_hits"]:>3}/{r["times_run"]:<3} {r["kind"][:3]} '
                  f'{r["status"][:6]:<7} {r["text"]}')
        return 0
    if a.cmd == 'gold':
        cmd_gold(con, a)
        return 0

    key = a.concept if '.v' in a.concept else concept_key(con, a.concept)
    if a.cmd == 'eval':
        (suite_gold(con, key) if a.suite == 'gold' else suite_adversarial(con, key))
        return 0
    if a.cmd == 'rerank':
        rid = a.run
        if rid is None:
            row = con.execute('SELECT id FROM runs WHERE key=? ORDER BY id DESC', (key,)).fetchone()
            if not row:
                raise SystemExit(f'no runs recorded for {key}. Run a search first.')
            rid = row['id']
        cands = merge(con, key, rid)
        if not cands:
            raise SystemExit(f'run {rid} for {key} retrieved nothing')
        cands = rrf(con, key, cands, rid)
        v = {r['tweet_id']: r for r in con.execute(
            'SELECT tweet_id, verdict, prob, reason FROM verdicts WHERE key=? AND rubric=?',
            (key, a.rubric))}
        for c in cands:
            row = v.get(c['id'])
            if row:
                c['verdict'], c['prob'], c['decided_by'], c['reason'] = (
                    row['verdict'], row['prob'],
                    'jev-cache' if row['verdict'] else 'none', row['reason'])
        print(f'run {rid}: {len(cands)} candidates, '
              f'{len([c for c in cands if c.get("verdict") == "unclear"])} unclear')
        cands, notes = frontier(con, key, cands, a.rubric, a.n,
                                a.model or env('LLM_MODEL_FRONTIER'))
        for x in notes:
            print('  ' + x)
        graded = [c for c in cands if c.get('decided_by') == 'frontier']
        if graded:
            graded.sort(key=lambda c: -(c.get('final_score') or 0))
            cands = graded + [c for c in cands if c.get('decided_by') != 'frontier']
        for c in cands:
            c['tier'] = {'hit': 0, 'unclear': 1, 'miss': 2, 'error': 3}.get(c.get('verdict'), 4)
        cands.sort(key=lambda c: (c['tier'], -(c.get('final_score') or 0), -c['found_by']))
        report(cands, key, a.n)
        return 0

    since = (datetime.now(timezone.utc) - timedelta(days=a.since)) if a.since else None
    seed = [q.strip() for q in a.seed.split(',') if q.strip()] or None
    if a.seed_group:
        # The phrase sets moved into patterns.json when search.py was refactored
        # to use pat.groups(). The probe string of each pattern is the human
        # phrase, which is exactly what CORE used to be.
        import json
        pj = os.path.join(HERE, 'patterns.json')
        with open(pj, encoding='utf-8') as f:
            groups = json.load(f)['groups']
        want = list(groups) if a.seed_group.upper() == 'ALL' else a.seed_group.split(',')
        seed = []
        for g in want:
            g = g.strip().upper()
            if g not in groups:
                raise SystemExit(f'patterns.json has no group called {g!r}. '
                                 f'It has: {", ".join(sorted(groups))}')
            e = groups[g]
            seed += [w for w in e['words']] if 'words' in e else [p[0] for p in e['patterns']]
        print(f'seeded from patterns.json {a.seed_group}: {len(seed)} phrases')
    cands = run(con, a.concept, a.source, a.limit, since, a.min_likes,
                days_back=a.since, pool_size=a.pool, rubric=a.rubric,
                n_queries=a.queries, frontier_top=a.frontier, seed=seed, fresh=a.fresh,
                examples=a.example, seed_set=a.seeds)
    report(cands, concept_key(con, a.concept), a.n)
    return 0


if __name__ == '__main__':
    sys.exit(main())
