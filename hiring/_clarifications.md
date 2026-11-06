Answers to your clarification questions, with code-grounded before/after examples.

## Q1: Must a tweet have three-or-more dated items, or are 1–2 opportunity tweets lost?

Yes. `roundup.parse_text()` first tries a blank-line split, then a single-newline bullet split, and returns `[]` as soon as `len(items) < 3`:

```python
if len(items) < 3:
    chunks = [c.strip() for c in _ITEM_SPLIT_SINGLE.split(text)]
    items = [c for c in chunks if _ITEM_START.match(c)]

if len(items) < 3:
    return []
```

So a tweet listing exactly one or two programs, however useful, is dropped by the roundup pass. It is only recoverable by (a) the single-program regex gate, (b) the hand list, or (c) research.py. Yes, `discover_tweets()` runs on every `opportunities.py` run and is the first thing scheduled by `weekly.ps1` / `weekly-twitter.ps1`:

```python
_discovered, _new_roundups = roundup.discover_tweets(
    args.db, OUT / "roundup_cache.json", years=("2026",), window_days=args.days)
```

`discover_tweets()` caches per-tweet results so once a tweet is tested it costs nothing on later runs, but it *does* run every time. And note the window: only tweets within `window_days` (default 45) of the newest bookmark are tested at all.

**Does cutting the single-program regex path solve it?** Partially. research.py scans *every* tweet with `length(text)>=40` and asks the model directly whether it is an opportunity, so one- or two-program tweets are caught by the LLM and named in one step. The remaining gap is the year window: `research.py scan` defaults to `--year 2026`, so a tweet older than 2026 is never sent unless you pass another year. `read_tweets()` itself has no year filter when `years=None`, so the limit is in the scan default, not the query. The 1-vs-3 threshold gap is fully solved; the age gap is not.

## Q2: Does the roundup pass filter by keywords, and is research.py the semantic primary instrument?

Two separate keyword filters exist.

The roundup pass filters on **structure**, not keywords. `looks_like_roundup()` only checks for three list markers and an opportunity word:

```python
_LIST_MARKER = re.compile(r"(?m)^\s*(?:\d+\.|\u2022|[\-*])\s")
_OPPORTUNITY_WORD = re.compile(
    r"\b(grants?|hackathons?|fellowships?|accelerators?|competitions?|"
    r"residencies?|scholarships?|prizes?)\b", re.I)

def looks_like_roundup(text):
    if len(_LIST_MARKER.findall(text)) < 3:
        return False
    return bool(_OPPORTUNITY_WORD.search(text))
```

A tweet with three bullet items but no opportunity word is skipped even if every bullet is a real program. The single-program gate is the keyword one: it requires *all three* of an apply phrase, an opportunity word, and a date (`_APPLY_PHRASE`, `_OPPORTUNITY_WORD`, `_DATE`).

The live X search (`--live`) *does* use the keyword query `OPPORTUNITY_QUERY`:

```python
OPPORTUNITY_QUERY = (
    '"hackathon" OR "hackathons" OR "grant" OR "grants" OR "fellowship" OR ...')
rows, notes = search.fetch_live_chunked(
    OPPORTUNITY_QUERY, limit=limit, since=since, min_likes=min_likes, exclude=("retweets",))
```

So yes: the regex passes are keyword- and structure-gated, and `research.py` is the semantic primary instrument. It asks the model to classify every tweet with a system prompt that lists what counts and what doesn't, and returns a `confidence` score. A tweet whose poster writes "we just opened our next cohort for builder-funders" with no keyword at all still reaches the model and can be caught. That is also how the model names the program, which fixes the `"program": ""` problem you quoted:

- **Before:** single-program gate passes, but the regex output hardcodes `"program": ""` (see `find_single_tweets` line 205). The human reads the tweet and hand-enters the program into `opportunities_manual.json`.
- **After:** the LLM returns `"program": "Y Combinator"` in one pass, then `enrich()` fetches the page and `merge()` writes `verified_deadline`, `status`, `apply_url` and `verified_at` straight into the manual file.

So yes, cutting the single-program regex path removes the `"program": ""` hand-off; the named output is a feature of the LLM prompt, not of the cut.

## Q3: Why was the roundup pass created, and how do before/after costs compare?

The code says exactly why. `discover_tweets()`'s docstring:

> "The cache means a run only tests bookmarks it has never seen, so the cost stays flat as the database grows."

And `roundup.py` line 101-102:

> "Pure function of the text, so discovery can reuse it without a second database read."

So the roundup pass was created as a **zero-cost filter**: pure Python, no network, cached per tweet, runs in milliseconds, and keeps the compiled report stable as the DB grows from 10k to 100k rows. It is the reason `python opportunities.py` remains instant. It was *not* created primarily to cut LLM cost, because the original pipeline had no LLM scan — `find_single_tweets()` is there precisely because "naming the program is a judgement" the regex can't do. The LLM throughput constraint only appears once `research.py` is wired in.

**Cost comparison, before vs after.** Numbers below are measured or inferred from your own probes: tokenharbor `deepseek-v4.1-flash:free` answers in ~2.2s then 429s; `deepseek-v4-flash:free` ~7.2s; `literouter/qwen` works. The DB is 99,355 rows; `read_tweets()` filters to 93,421 tweets with text and `>=40` chars (~25.9M chars ≈ 6.5M input tokens). The scan batches 30 tweets per call at 4k output tokens per call.

**Before (existing pipeline, no research scan):**

- `roundup discover_tweets()`: ~0 cost after first run, fully cached. First run touches all 93k tweets once with pure regex.
- `find_single_tweets()`: pure regex over ~93k 2026 tweets, O(N) string scans, sub-minute, cached by your 45-day window.
- LLM calls: zero. The LLM is not in this pipeline.
- Total wall-clock: seconds. Total token cost: $0.
- Coverage: misses 1-2 program tweets, tweets without your keywords, and anything the human hasn't hand-entered into the manual list.

**After (research scan + cut single-program regex):**

- `roundup discover_tweets()`: unchanged, still runs, still near-zero cost and still the instant path for roundups.
- `find_single_tweets()`: removed.
- `research.py scan`: 93,421 tweets ÷ 30 per batch ≈ 3,115 LLM calls, each with ~600 chars of text (600 chars × 30 tweets ≈ 18k input chars per batch) plus the batch header. At ~2.2s per successful call on the hot tokenharbor v4.1 route, that is 3,115 × 2.2s ≈ 19 hours of pure model time, plus provider rotation overhead and cooldowns. Enrichment adds one page fetch plus one 700-token extraction call per classified opportunity — call it another few hours if the scan yields a few thousand opportunities.
- Total wall-clock: many hours (the 467-minute estimate in `plan()` was for 2 calls/s; free-route throttling makes the real number higher).
- Total token cost: ~6.3M input tokens + ~3M output tokens across the scan, plus enrichment. On paid rates that is dollars to tens of dollars depending on model; on your free routes it is time and quota, not money.
- Coverage: near-complete over the scanned window, including tweets with no keywords and 1-2 program lists, all with named programs and (after enrich) verified fields.

**Is the cost reduced?** No — the raw token/time cost goes from $0 / seconds to many hours and paid tokens. What is reduced is *work-per-unit-recall*: before, every missed tweet was a human finding and typing a row; after, the model does that classification at the same rate as everything else. The trade-off you already accepted when you asked for the researched pass: full semantic coverage at the price of a long LLM pass. If you want the cheap path kept, the roundups stay exactly as they are; if you want full coverage, the LLM scan is the cost of it.

A way to cut the cost without losing much: keep `--limit` small until the scan warms. The `checked` table caches every tweet the model answered, including tweets with no opportunity, so a second full run classifies almost zero tweets. You run the expensive scan once, then every scheduled `opportunities.py` run stays instant because it no longer needs `find_single_tweets()` or the human hand-off. Also note `research.py scan` defaults to 2026, so it will naturally stop when your newest bookmark passes 2026 - plan to widen `--year` over time rather than re-scanning the whole 99k on every run.

## Q4: What is the regex candidate generator, and why was `find_single_tweets()` created?

The "regex candidate generator" is `roundup.find_single_tweets()`. It is the generator of candidates: it emits single-program tweets that look like opportunities but arrive with `"program": ""`, and the human is expected to name the program and add a row to `opportunities_manual.json`. The name is literal — it generates candidates for a human to review:

> "Tweets that announce one opportunity rather than a list of them... So this returns the evidence a reader needs, and leaves `program` empty."

It was created in 2024-2025 because the roundup parser can only handle lists of three or more dated items, so there was a structural hole for single-program announcements. The author explicitly called naming the program "a judgement" — "We are hosting the world's first Autonomous Company Hackathon" names the program only once you know the account — and built a regex gate to widen coverage while offloading the naming to a person. It is the human-in-the-loop entry point for anything the list parser can't handle.

**In the after pipeline** this function is no longer called: `opportunities.py --candidates` would emit nothing useful because research.py already names everything the model classifies. Its output table (`single-candidates.md`) is superseded by `research_opportunities.json`, which carries `program`, `org`, `kind`, `confidence`, `deadline_text`, `apply_url`, `money`, `eligibility` and, after merge, `verified_deadline`, `status`, `website`, `verified_at`, `source: research` and `evidence_url`.

## Q5

You ended with "5." and no question. The remaining gap is the **year filter**: `research.py scan` defaults to 2026, so it only sees tweets from that year. As 2026 progresses into 2027, you will need to widen `--year` and raise `window_days` if you want older tweets re-evaluated. Also the manual list stays your recall anchor regardless, since `opportunities.py` reads `opportunities_manual.json` first and auto-discovered rows never override a matching hand row.
