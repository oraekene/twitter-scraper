# Hiring search

Finds tweets about hiring, job openings, layoffs, and job hunting, then groups
them so you can read a shortlist instead of 94,415 bookmarks.

There are two jobs here, and they are separate on purpose.

| Job | Searches | Runs | Output |
|---|---|---|---|
| `weekly.ps1` | your saved bookmarks | `search.py` | `out\weekly\` |
| `weekly-twitter.ps1` | accounts on X | `search.py --watchlist` | `out\weekly-twitter\` |

Both call the same `search.py` and the same classifier, so a tweet reads the
same whichever report it lands in. They are split only because the two run at
different times and read different things.

## Run it by hand

```powershell
cd "C:\Users\rotim\Documents\twitter scraper\hiring"

python search.py                                  # your bookmarks
python search.py --json out\hiring.json           # full text, nothing truncated
python search.py --days 8 --md -                 # only the last 8 days
python search.py --watchlist watchlist.txt        # X, from the watchlist
python search.py --live                           # X search, broken, see below
python search.py --selfcheck                      # check the code, touch nothing
```

Truncation is a reading aid in the markdown only. The JSON export always carries
the whole tweet. Every other tool you own works on the same data too:
`fieldtheory search "hiring" --json`, `fieldtheory md`, and `fieldtheory show <id>`.

## The X half

Two ways in, and they have different shapes.

`--live` searches X for a query. With no `--query` it uses the **full 81 phrase
set**, the same one the bookmark pass uses, because there is no reason for live
search to recall less. X caps one query at 512 characters and the set is 1329,
so it is split into 4 batches and merged. A three second pause sits between
batches. The report's `Coverage` section shows how each batch did.

It found accounts you have never heard of, which is the whole point, but a
general search for `hiring` is noisy. Raise `--min-likes` to cut the spam.

```powershell
python search.py --live --days 7 --min-likes 30 --md -      # full phrase set
python search.py --live --query 'hiring OR "open role"' --md -   # one narrow query
```

`--watchlist` reads every handle in `watchlist.txt`, one per line. It sends **no
query at all**: it reads everything the account posts and then classifies each
post. That is why the watchlist pass does not need the phrase set and is the
higher signal read, because you chose the accounts. Seed it yourself and add
handles when a report names an account you do not follow.

### Why search was broken, and what fixes it

`twitter search` returned HTTP 404 on this machine until 2026-10-09. The cause
was not the query id. It was the `x-client-transaction-id` header.

twitter-cli builds that header by fetching `https://x.com` and scraping the
`ondemand.s` chunk hash out of the page. It fetched that page **without the auth
cookies**, so X served the logged-out shell. The logged-out shell has no chunk
manifest, so the scrape returned nothing, so no header was generated, so no
header was sent. X answers HTTP 404 for search without it.

Every other endpoint the CLI uses keeps working without the header, which is why
this looked like "search is broken" and not "auth is broken". The CLI swallows
the failure and prints `Failed to init ClientTransaction`, then carries on.

Fix: `node fix-twitter-cli.js`. It puts the auth cookies on the session before
the homepage fetch. Idempotent, and re-run it after any upgrade of the CLI. Also
delete `%USERPROFILE%\.twitter-cli\transaction_cache.json` once, because the
failed result gets cached for an hour.

While diagnosing, four other query ids were tried and all four failed, which is
what ruled the query id out: the CLI's own hardcoded fallback, a fresh scrape of
the live page, the community `fa0311/twitter-openapi` list, and two ids captured
separately in `oraekene/x-automation` and a vendored `@steipete/bird`. The CLI's
built-in fallback works once the header is present, so nothing else needs patching.

A pause of 2 seconds between accounts is required in watchlist mode. Nineteen
accounts back to back returns HTTP 429 from the eighth onwards, which looks like
a successful run that quietly covered half the list. The report's
`accounts_read` section tells you which ones failed.

## Weekly

```powershell
pwsh -File weekly.ps1                # bookmarks, last 8 days
pwsh -File weekly-twitter.ps1        # X, two passes: search then watchlist
```

Each writes dated markdown reports, dated JSON exports, and a log, keeping the
last 12 runs. The X job writes two reports per run, suffixed `-search` and
`-watchlist`, because a search and a watchlist answer different questions.

A scheduled task called `TwitterBookmarkWeeklyScan` already exists in the parent
folder. It syncs bookmarks and expands threads every Sunday from ten in the
morning to four in the afternoon. That is why `weekly.ps1` does not sync by
default. Register the two new ones for a quiet hour so they never collide with
it. The commands are in the last lines of each script.

## Files

| File | What it is |
|---|---|
| `search.py` | The whole thing. Bookmarks, watchlist, and live modes, plus the classifier. |
| `pat.py` | Regex guard. Every pattern must match its own probe or the run stops. |
| `weekly.ps1` | Scheduled job for your bookmarks. |
| `weekly-twitter.ps1` | Scheduled job for X. |
| `watchlist.txt` | The accounts the watchlist pass reads. Edit this to change what it watches. |
| `fix-fieldtheory.js` | Re-applies the search fix in `fieldtheory`. Run after `npm update -g fieldtheory`. |
| `fix-twitter-cli.js` | Re-applies the transaction header fix in `twitter-cli`. Run after upgrading the CLI, or if `twitter search` starts returning 404 again. |
| `scratch/` | Throwaway scripts from the first run on 2026-10-09. Kept for history. Do not run them. |

## Three traps this already handles

All three failed silently, and all three were found on 2026-10-09.

Join `bookmarks_fts` on `rowid`, never on `b.id`. The `bookmarks.id` column is
declared TEXT, so joining on it compares text to an integer, matches nothing,
and turns the query into a full table scan. Measured: 382 seconds for zero rows
against 0.19 seconds for the rowid join.

FTS5 takes plain phrases, not regex. It rejects `\b` and `(?:` with a syntax
error. That is why the recall list is a list of words and `pat_fts` refuses
regex syntax.

`twitter user-posts` returns retweets. A retweet carries the original author, so
one founder who retweeted a job ad dragged that advertiser's whole spam feed into
the report, and nineteen watched accounts produced 74 fake openings instead of
14 real ones. `normalise_live` drops them, and `live_shape_check` proves it.

## Known limits

Roughly one opening in three is a false positive, mostly a story about hiring
rather than an actual job post. The report is a shortlist to skim, not a clean
list.

The database has no `follower_count` or `is_verified` column, so the report does
not show follower counts. Those live in the JSONL inside nested author objects
with no index, so getting them costs a 155 MB scan per run. Say so before paying
for it.
