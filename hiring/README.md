# Hiring search

Finds tweets about hiring, job openings, layoffs, and job hunting, then groups
them so you can read a shortlist instead of 94,415 bookmarks.

## The control panel

```powershell
cd "C:\Users\rotim\Documents\twitter scraper\hiring"
python ctl.py serve
```

Opens `http://127.0.0.1:8765`. Five tabs: Commands, Searches, Results, Status, Settings.
It is bound to loopback on purpose, because running anything here uses your `.env`
credentials, so nothing leaves this machine.

There is no server and no database. The page reads and writes `searches.json`
directly and the standard library serves it. QMD has no web page either; what
you remember is its MCP Inspector.

The Commands tab lists every command in `COMMANDS.md`, read from the file so the
page cannot drift from it. Only the nine on the allowlist can be started from the
page. Everything else is there to copy.

### Writing your X credentials is locked by default

The Settings tab can write `auth_token` and `ct0` into `.env`, but only if you
start the panel with the write path armed:

```powershell
$env:FT_ALLOW_ENV_WRITE='1'; python ctl.py serve
```

Without that variable the save button is disabled and the server answers 403.

This exists because of a real accident on 2026-10-10. A test posted to the write
endpoint to prove it worked, and that overwrote the live `auth_token` with a test
string. The backup command had a wrong path so it silently did nothing. It then
happened a second time to `ct0` during the follow-up test. Both were restored, but
it should not have been possible twice, so proving the path now requires arming
it, and `FT_ENV_FILE` redirects it away from the real file.
`python test_credentials.py` checks the write logic against a temp file and
asserts the real `.env` is byte-for-byte unchanged.

## The CLI

Same thing without the browser.

```powershell
python ctl.py list                                        # show everything
python ctl.py check                                       # validate config, run nothing
python ctl.py run --all                                   # run everything now
python ctl.py run --due                                   # only what is due today
python ctl.py run --name hiring-live                      # run one

python ctl.py add --name ai-jobs --source live --query 'hiring OR "we are hiring"' --every-days 3
python ctl.py add --name aakash --source watchlist --handle aakashgupta
python ctl.py add --name my-list --source list --list-id 1908587200419422252
```

Sources are `bookmarks`, `live`, `watchlist`, and `list`.

| Source | Reads | Network | Notes |
|---|---|---|---|
| `bookmarks` | your saved tweets | no | free, no rate limits |
| `live` | X search, full 81 phrase set in batches | yes | noisy, raise `--min-likes` |
| `watchlist` | every post by accounts you named | yes | no query sent, highest signal |
| `list` | one X list by numeric id | yes | id comes from `x.com/i/lists/<id>` |

## Scheduling

One Windows task runs daily and decides what is due, rather than registering a
task per search, which Windows makes painful. A search is due when
`days since last run >= every_days`, so a day the laptop was asleep does not
skip it.

```powershell
pwsh -Command "Register-ScheduledTask -TaskName 'hiring-runs' -Description 'Run due hiring searches' -Trigger (New-ScheduledTaskTrigger -Daily -At 8:55am) -Action (New-ScheduledTaskAction -Execute 'python' -Argument '\"C:\Users\rotim\Documents\twitter scraper\hiring\ctl.py\" run --due' -WorkingDirectory 'C:\Users\rotim\Documents\twitter scraper\hiring') -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2) -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries)"
```

Keep the daily trigger away from `TwitterBookmarkWeeklyScan`, which fires Sunday
ten in the morning through four in the afternoon. Both open the same database.

Output lands in `out\searches\` as `<name>-<timestamp>.md` and `.json`.

## Adding accounts to a watchlist

Three ways, in order of effort.

Edit `watchlist.txt` by hand, one handle per line. It is already wired to the
`hiring-watchlist` search.

```
python ctl.py add --name somename --source watchlist --handle aakashgupta
```

Or add the handle in the browser page. For a one-account watchlist this is
better than editing a shared file, because it gets its own schedule.

## X lists

A list id is the last number in the list URL, `x.com/i/lists/<id>`. X refuses
cookie auth on every list-enumeration endpoint, verified 2026-10-10:
`/i/api/1.1/lists/list.json` answers 401 and `/i/api/2/lists/created.json`
answers 403. So there is no way to read your list list, ids have to be copied.

Three of yours are seeded into `searches.json`, disabled until you turn them on.

## Run it by hand

```powershell
python search.py                                  # your bookmarks
python search.py --json out\hiring.json           # full text, nothing truncated
python search.py --days 8 --md -                  # only the last 8 days
python search.py --watchlist watchlist.txt        # X, from the watchlist
python search.py --live --min-likes 30 --days 7 --md -   # X search, full phrase set
python search.py --selfcheck                      # check the code, touch nothing
```

`search.py` is the engine. `ctl.py` is a scheduler and config layer on top of it,
so both remain useful on their own.

Truncation is a reading aid in the markdown only. The JSON export always carries
the whole tweet.

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
| `ctl.py` | The control plane. Config, CLI, and scheduler. Start here. |
| `search.py` | The engine. Classifier and the four fetch modes. |
| `serve.py` | The localhost server. Standard library only, loopback only. |
| `web/index.html` | The page itself. One file, no build, no dependencies. |
| `test_credentials.py` | Proves the credential write path, against a temp file only. |
| `searches.json` | Your searches. Safe to edit by hand, but the CLI and page are easier. |
| `pat.py` | Regex guard. Every pattern must match its own probe or the run stops. |
| `weekly.ps1` | Standalone bookmark hunt, if you do not want the control plane. |
| `weekly-twitter.ps1` | Standalone X hunt, same. |
| `watchlist.txt` | Accounts for the `hiring-watchlist` search. |
| `fix-fieldtheory.js` | Re-applies the search fix in `fieldtheory`. |
| `fix-twitter-cli.js` | Re-applies the transaction header fix in `twitter-cli`. |
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
