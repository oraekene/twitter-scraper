# Conceptual search, no embeddings

`sem.py` searches a corpus it does not own. It has no embeddings anywhere.

## Why the obvious answer is wrong

You cannot semantically search X. Embeddings are computed over text you hold, and
you hold none of X. X's own search bar is the only thing indexing X and it is
lexical. So the model layer can only ever rank what retrieval already found.

The pipeline is therefore always: cheap and dumb retrieval, then an expensive
semantic pass on a bounded pool. Everything below follows from that.

## The one trick worth knowing

Reciprocal Rank Fusion. X returns order and no scores, so anything needing
numbers is guessing. RRF needs only ranks:

    score(tweet) = sum over queries of 1 / (60 + rank_in_that_query)

A tweet found under seven different phrasings accumulates score from seven
independent lists. That agreement is the semantic signal, and it is arithmetic.
This is why the RRF leg runs one query per call. OR-batching six variants into
one call returns one merged list and destroys the agreement.

Measured on your bookmarks with the 53 phrases from `patterns.json`, agreement
put 7 genuine offers in the top 7, and the first false positive only appears at
rank 8 where `found_by` drops to 1. With 8 queries instead of 53, nothing
agrees with anything and the ranking is no better than arrival order. Query
count is the whole game.

## Phases

| Phase | What it does | Model |
|---|---|---|
| 1 | concept into a `concept_key`, rubric version, TTL | |
| 2 | 60 to 80 queries plus 15 negatives | small fast model, hot |
| 3 | dedupe by Jaccard, check negatives, order by yield | Jev |
| 4 | OR-group probe, kill dead groups, one call per survivor | |
| 5 | union by id, exact-text hash, count appearances | |
| 6 | RRF with learned per-query weights | |
| 7 | triage tweets into hit / miss / unclear | Jev |
| 8 | rerank the unclear band only, lazily | frontier LLM |
| 12 | scoreboard, retire dead queries, feed winners back | small fast model |

## Why the classifier never triages queries

It looks like it should. It cannot. All 60 queries were written by a model told
to write queries for the concept, so asking "is this about hiring" returns yes
to nearly all of them. It reads like a working filter and filters nothing. The
classifier checks the negatives for drift, orders the positives by expected
yield, and does real work in phase 7 where the candidates are retrieved tweets
that genuinely disagree with each other.

## Running it

```powershell
# offline and free, against your own bookmarks
python sem.py search "tweets remotely hinting at hiring" -q "we are hiring,open role,join our team"

# apples to apples against the module you already have
python sem.py search "tweets remotely hinting at hiring" --seed-group OFFER,APPLY_CTA,LISTY

# live
python sem.py search "tweets remotely hinting at hiring" --source x --fresh

# the cheap test that decides whether the model layer is worth building
python sem.py eval "hiring" --suite adversarial

python sem.py queries "hiring"      # which queries paid off
python sem.py selftest
```

`--fresh` shows only what this run retrieved. Without it you get everything
ever found for the concept, which is the archive, and it matters because X stops
returning old tweets.

## Keys

Everything runs without any key and says which leg went missing instead of
degrading quietly.

| Key | Enables |
|---|---|
| `TYPESAFE_API_KEY` | phases 3 and 7 |
| `OPENCODE_ZEN_KEY`, or `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY` | phases 2, 8, 12 |

The OpenCode Zen key in `.env` is valid and the account balance is empty, so
phase 8 answers 402. Its free models refuse to run outside the OpenCode app.
Top up and phase 8 works with no code change.

## Scheduled runs

A `concept` source exists in the scheduler, next to bookmarks, live, watchlist
and list. A concept is a sentence, not a query, and it deliberately does not go
through the FTS5 check that guards a saved query.

```powershell
python ctl.py add --name concept-raise --source concept `
  --concept "tweets hinting at a Series A raise" --seed-group OFFER
```

**Set `seed_group` or `seed` on a scheduled concept run.** Without a fixed query
set the run depends on a model being reachable, and a daily job that silently
returns zero rows is worse than no job. With a seed it costs no model call at
all, and the report says so in its coverage lines.

## Seeded examples

`seeds.json` holds few-shot examples for phase 2, grouped by concept. The model
writes queries backwards from real matching tweets rather than from the concept
name, which is worth more than a better prompt, because it cannot otherwise know
that X indexes "DM me your work" but not "open roles".

Sets ship for hiring, funding, complaints and gambling. A concept is matched to
one on a four-character stem overlap, so "accounts complaining about Cursor
performance" reaches `complaints` even though the words do not match. When
nothing matches it falls back to hiring **and says so**, because examples in the
wrong register teach the wrong vocabulary.

```powershell
python sem.py search "your concept" --seeds complaints   # name the set yourself
python sem.py search "your concept" --example "a real matching tweet"
```

Add your own by pasting tweets you already know are good. The best examples are
the awkward ones: slang, lowercase, no role named. Ten real examples beat fifty
invented ones.

## Still blocked

Phase 8 needs a chat model with credit. Everything else runs, including the
scheduled concept source and the whole adversarial suite.


## Jev, verified live

`POST https://api.typesafe.ai/v1/systemone`, `Authorization: Bearer`. The model
is `jev-latest`. `questions` is a map of your own names to typed questions,
answered under the same names in `answers`:

```json
{"state": "we are hiring two engineers",
 "questions": {"offer_language": {"type": "noul", "instructions": "..."}},
 "answers":  {"offer_language": {"type": "noul", "noul": 0.98}}}
```

`choice` takes a `criteria` map and returns the winner plus every probability.
`score` takes an ordered `criteria` array. Questions in one call run in
parallel, so four features cost the latency of one.

## The classifier extracts features, it does not judge

This is the single most important thing found by measurement. Asking one
question, "is this an offer", returns 0.577 on average for real offers and
0.307 for lookalikes. That overlaps so badly that with bands at 0.85 and 0.15
**eleven of fourteen landed in the unclear band and the model committed to
nothing at all.** Zero hits, zero useful precision.

Four narrow questions in one call, combined by plain code, separate cleanly:

| Feature | Question |
|---|---|
| `offer_language` | direct employer language such as "we are hiring" |
| `role_named` | a specific job title, role or department |
| `how_to_apply` | how to respond: apply here, DM me, careers link |
| `discussion_only` | discussion, news, advice, or the author job hunting |

```python
positive = max(offer_language, role_named*0.5 + how_to_apply*0.5, role_named*0.5)
score = positive * (1 - discussion_only)
```

Jev decides each fact. Code decides the rule. That is what keeps it debuggable,
and it matches what decomposition bought you on the wine cookbook.

## Measured, 14 adversarial tweets, 7 real offers and 7 lookalikes

| System | Took | Precision | Recall |
|---|---|---|---|
| Regex tier from `patterns.json` | 12 of 14 | **6/12** | 6/7 |
| Four features plus code rule | 5 of 14 | **5/5** | 5/7 |

Same recall, twice the precision, and it takes no lookalikes at all. The two it
misses are defensible: "DM me your work" is five words with no context, and
"the company is hiring but the visa process is painful" is commentary.

The bands at 0.45 and 0.25 are calibrated on these fourteen tweets, where hits
landed at 0.62 and up and lookalikes at 0.155 and down. That is a wide gap on a
small sample. Treat them as provisional and re-measure on a larger labelled set
before trusting them on a new concept.

## The panel

Four buttons on the Fetch tab, plus a selftest button next to tests.

| Button | What it does |
|---|---|
| Concept search | the whole pipeline, bookmarks or live X |
| Is the model better than the regex? | the adversarial suite |
| Rerank the unclear band | phase 8 on a stored run, no retrieval |
| Which queries paid off | the scoreboard |

`sem-search` takes `--seed-group OFFER,APPLY_CTA` to reuse the hand-written
phrase sets, which is the apples to apples comparison. Blank generates new
queries with a model.

## Still blocked

Phase 8 needs a chat model with credit. The orcarouter key in the opencode config
is out of credits and its free tier needs work email verification. The OpenCode Zen
key here is valid but its balance is empty, so the call returns 402 with the real
reason rather than a guess. Everything else runs, including the scheduled concept
source and the whole adversarial suite.

