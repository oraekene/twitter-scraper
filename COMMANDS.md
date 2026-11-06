# Command Reference

Two tools. `fieldtheory` is the brain (local database, search, markdown). `twitter` is the fetcher
(talks to X live). Note: `ft` is a PowerShell alias for Format-Table, so never type `ft`.

## 1. Keep everything up to date

| Command | Why you run it |
|---|---|
| `python sync_bookmarks.py` | Pull new bookmarks. Repeat until it stops saying "max runtime reached". |
| `python crawl_tweets.py threads --limit 200 --top 20` | Expand full threads behind every bookmarked tweet. Resumable. |
| `python crawl_tweets.py account <handle> -n 2000` | Pull every tweet from an account, yours or anyone's. |
| `python parse_archive.py <zip>` | Turn X's data archive into `out\history-<handle>.jsonl`. The only complete way to get years. |
| `python crawl_tweets.py replies <id> --top 10` | Top N replies to one tweet, ranked by engagement. |
| `python crawl_tweets.py replies-all --limit 200 --top 10` | Same batch pass over every bookmark, ranked. Resumable. |
| `python crawl_tweets.py thread <id> --save` | Full thread behind one tweet. |

All six are buttons on the control panel. The four you run by hand are on the
Dashboard, and all six with every parameter are on the **Fetch** tab. Start the
panel with `python hiring\ctl.py serve`.

The two corpus passes are separate on purpose. `threads` marks a tweet done in
`out\threads-index.json`, so if `replies-all` shared that index it would find
nothing left to do. It keeps `out\replies-index.json` instead, ranks by
engagement rather than fetch order, and takes `--redo` for when you want more
replies than the last run kept.

### Whole account history, years back

`twitter user-posts` stops at 200 tweets (`rateLimit.maxCount`, hard cap 500),
which is three days on a busy account. `crawl_history.py` calls the same client
directly, keeps the cursor in `out\history-<handle>.state.json`, and appends to
`out\history-<handle>.jsonl`, so a run can stop and resume.

```
powershell -File crawl_history.ps1        # @ascully789, since 2023-10-28, detached
& "$env:APPDATA\uv\tools\twitter-cli\Scripts\python.exe" crawl_history.py <handle> --since 2023-10-28
```

It must run on the twitter-cli venv python, because that is where the library
lives. X allows **50 UserTweets calls per 15 minutes** per account and returns
20 tweets per call, so the ceiling is 200 pages per hour. `--delay 19` sits just
under the limit instead of wasting windows on 429s.

**X stops the profile timeline at about 1,000 entries.** Measured on
@ascully789 on 2026-10-28: pages 1-43 return tweets, page 44 and later return
only cursors, a fresh chain starts working again, and waiting out the rate
window does not revive the old cursor. That is 2-3 days of a busy account, not
three years. Search cannot fill the gap either: for one day it returned 19 of
the 32 tweets the timeline had.

So for years of history use the archive X builds for you, which is complete and
costs no API traffic. Ask for it in Settings -> Your account -> Download an
archive of your data, then:

```
python parse_archive.py twitter-2026-10-29-abc123.zip --since 2023-10-28
```

It reads `data/tweets.js`, skips retweets unless `--include-retweets`, and
merges into `out\history-<handle>.jsonl` by id, so the recent tweets the crawler
already has survive.

Every route was priced and checked on 2026-10-28 in `X-HISTORY-OPTIONS.md`. The
API is now pay per use at $0.001 per own post, but it stops at about 3,200 posts,
so the archive remains the only complete option.


### The sync has more knobs than it used to

`python sync_bookmarks.py --help` lists them all. The ones that change what a
sync does, rather than just how much of it runs:

| Flag | What it does |
|---|---|
| `--target-adds 500` | Stop after 500 new bookmarks. Gentler on rate limits than a time limit. |
| `--gaps` | Backfill quoted tweets, truncated articles, and linked article text. |
| `--gaps-only` | The same backfill without pulling new bookmarks first. |
| `--folders` / `--folder "AI stuff"` | Sync your X folder tags, or just one folder. |
| `--rebuild` | Full re-crawl of everything. Slow, and it throws your cursor away. |
| `--delay-ms 1200` | Milliseconds between requests. The default is 600. Raise it if X answers 429. |
| `--media` | Download images and video. Off by default because it is slow. |
| `--skip-md` | Stop after the database sync. Use `fieldtheory md --changed` to catch up cheaply. |

`--rebuild` is the only one that can lose work, so the panel asks you to confirm
it, and the server refuses to run it without that confirmation even if the page
is bypassed.

`--gaps` costs one network fetch per bookmark that has a quote or a link, and it
does not retry what X reports as deleted. A trial run on 2026-11-04 failed about
four items in five and projected to thirteen hours, so run it in the daytime
where you can watch it, not overnight, and stop it with Ctrl-C when the failure
count runs away.

## 2. Find things you bookmarked

| Command | Why you run it |
|---|---|
| `fieldtheory search "<terms>" --limit 20` | Full-text search across all 94,410 bookmarks. |
| `fieldtheory search "<terms>" --author <handle>` | Same, but only from one person. |
| `fieldtheory search "<terms>" --after 2026-01-01` | Same, but only from a date onward. |
| `fieldtheory search "<terms>" --json` | Machine-readable output, for piping into other tools. |
| `fieldtheory list --category research --limit 30` | Browse by category. Needs `classify` to have run. |
| `fieldtheory list --folder "AI stuff"` | Browse one X bookmark folder. Needs `--folders` sync. |
| `fieldtheory list --author <handle> --after 2026-01-01` | Everything one person posted since a date. |
| `fieldtheory show <id>` | One bookmark in full, by its numeric ID. |
| `fieldtheory library search "<terms>"` | Search your own written notes, not bookmarks. |

Search tips. Terms are OR by default, so `rust async` returns either. Use `rust AND async` to
narrow. Use `"exact phrase"` to force an exact match.

## 3. Understand your own habits

| Command | Why you run it |
|---|---|
| `fieldtheory status` | How many bookmarks you have, and where the data lives. |
| `fieldtheory stats` | Aggregate numbers across everything. |
| `fieldtheory viz` | Visual dashboard of what you bookmark. |
| `fieldtheory categories` | How your bookmarks split by category. |
| `fieldtheory domains` | Which sites you bookmark from most. |
| `fieldtheory folders` | Your X bookmark folder counts. |
| `fieldtheory index` | Rebuild the search index if search looks wrong. |

## 4. Organise

| Command | Why you run it |
|---|---|
| `fieldtheory classify --regex` | Sort into 7 categories using plain regex. Free. Run after a big sync. |
| `fieldtheory classify` | Same but uses Claude or Codex. Smarter, costs tokens. |
| `fieldtheory sample research --limit 10` | Taste-test one category. |
| `fieldtheory sync --folders` | Pull your X bookmark folder tags. |
| `fieldtheory fetch-media` | Download images and video for bookmarks. Slow. |

## 5. Turn bookmarks into knowledge

| Command | Why you run it |
|---|---|
| `fieldtheory md` | Export every bookmark as its own markdown file. |
| `fieldtheory md --changed` | Re-export only what changed. Fast. |
| `fieldtheory ask "<question>"` | Ask a question, get an answer from your bookmarks. Needs Claude or Codex. |
| `fieldtheory wiki` | Compile a linked wiki from everything. Needs Claude or Codex. |
| `fieldtheory lint --fix` | Health-check the markdown base and repair it. |
| `fieldtheory note "<text>"` | Quick note into today's scratchpad. |
| `fieldtheory new brief "<title>"` | Create a brief, command, scratchpad, wiki, or debate page. |

## 6. Search X live, not your bookmarks

| Command | Why you run it |
|---|---|
| `twitter search "AI agents" --min-likes 500 -n 50` | Search X with quality filters. |
| `twitter search "hiring" --to <handle>` | What people say to a specific account. |
| `twitter search "rust" --has links --exclude retweets` | Require links, drop retweets. |
| `twitter user-posts <handle> -n 200` | One account's tweets. |
| `twitter tweet <id> -n 50` | One tweet with its replies. |
| `twitter followers <handle>` | Who follows someone. |
| `twitter bookmarks folders` | List your X bookmark folders. |
| `twitter whoami` | Confirm which account you are logged in as. |

Useful search flags: `--from`, `--to`, `--lang`, `--since`, `--until`, `--has`, `--exclude`,
`--min-likes`, `--min-retweets`, `-t top|latest|photos|videos`.

## 7. Where the data lives

| Path | What it holds |
|---|---|
| `C:\Users\rotim\.fieldtheory\bookmarks\bookmarks.jsonl` | Raw bookmark data, one JSON object per line, 155 MB. |
| `C:\Users\rotim\.fieldtheory\bookmarks\bookmarks.db` | SQLite database with a full-text search index, 120 MB. |
| `C:\Users\rotim\.fieldtheory\library\` | 94,410 markdown files, one per bookmark. |
| `C:\Users\rotim\Documents\twitter scraper\out\` | Thread and account pulls from crawl_tweets.py. |
| `C:\Users\rotim\Documents\twitter scraper\.env` | Your auth_token and ct0. Never commit this. |

Each line in the JSONL is one bookmark with these fields: `id`, `tweetId`, `url`, `text`,
`authorHandle`, `authorName`, `postedAt`, `bookmarkedAt`, `conversationId`, `language`,
`engagement`, `media`, `links`, `tags`.

## 8. Check the setup still works

| Command | Why you run it |
|---|---|
| `python test_sync.py` | Confirms both tools exist and credential loading works. |
| `python test_crawl.py` | Confirms thread splitting and reply ranking. |
| `python hiring\pat.py` | Confirms the regex guard still rejects a broken pattern. |
| `python hiring\search.py --selfcheck` | Confirms every hiring pattern matches its own probe. |
| `python hiring\opportunities.py --selftest` | Confirms the roundup parser and the report date, no network. |
| `python hiring\test_panel.py` | Confirms the page parses and the Fetch tab matches the manifest. |
| `python hiring\test_api.py` | Confirms every route, every rejection, and the argv each job builds. |
| `node hiring\fix-fieldtheory.js` | Re-applies the search fix below. Run after `npm update -g fieldtheory`. |

## 9. Find hiring posts and job openings

Everything lives in the `hiring` folder. See `hiring\README.md`. Start at the control panel.

```
python hiring\ctl.py serve                 # browser control panel on 127.0.0.1:8770
python hiring\ctl.py list                  # show every search
python hiring\ctl.py run --due             # run whatever is due today
python hiring\ctl.py add --name x --source live --query "hiring" --every-days 3
python hiring\ctl.py add --name y --source watchlist --handle aakashgupta
python hiring\ctl.py add --name z --source list --list-id 1908587200419422252
```

Four sources: `bookmarks` reads your saved tweets from disk, `live` searches X with the full 81
phrase set in batches, `watchlist` reads named accounts with no query at all, and `list` reads one X
list by numeric id. A list id is the last number in `x.com/i/lists/<id>`. X refuses cookie auth on
every list-enumeration endpoint, so ids must be copied by hand.

The engine underneath is `hiring\search.py`, which also runs standalone:

```
python hiring\search.py --search hiring-bookmarks   # your bookmarks
python hiring\search.py --search hiring-bookmarks --json out\h.json   # full text
python hiring\search.py --live --search hiring-live --min-likes 30 --days 7 --md -
python hiring\search.py --watchlist hiring\watchlist.txt
```

Every query is a field on a saved search in `hiring\searches.json`, and the panel edits it. There is no phrase set built into the code, so `--search NAME` is the normal way to run one.

The same folder builds a separate list for grants, hackathons, funds and fellowships. It reads the
same database, so it needs no extra sync:

```
python hiring\opportunities.py                  # out\opportunities-<date>.md
python hiring\opportunities.py --live --days 7  # also search X itself
python hiring\opportunities.py --candidates     # tweets that still need a name
python hiring\opportunities.py --selftest       # check the parser, no network
```

A tweet that lists three or more dated programmes is parsed automatically. A tweet that announces one
programme is not, because naming it is a judgement; `--candidates` lists those and a named row goes
into `hiring\opportunities_manual.json`. `weekly.ps1` runs the bookmarks pass, `weekly-twitter.ps1`
runs the live pass, and each takes `-Only hiring` or `-Only opportunities` so the two questions can
be scheduled on different days. `hiring\install_tasks.ps1` registers all four weekly tasks.

### The AI sweep over every bookmark

`research.py` reads every tweet in the database through the local AI gateway and asks the model to
find anything a person can apply to. It writes nothing but its own database, so stopping and restarting
costs nothing:

```
python hiring\research.py scan                  # classify tweets, resumable
python hiring\research.py enrich                # fetch pages found in tweets
python hiring\research.py merge --stage --raw   # fast staging from the scans table
python hiring\research.py merge --stage         # full staging with page-extracted details
python hiring\research.py merge                 # append approved rows to the curated list
python hiring\research.py clean                # drop the staging and review files
python hiring\research.py selftest             # 21 checks, no network
```

`merge --stage` is the safe one: it writes the staging list and leaves `opportunities_manual.json`
untouched. The Review tab on the dashboard shows that list and lets you approve or reject each row;
approving writes it into the curated file with `source: "research"`. A scan that has not finished
simply stages what it has, so running it on a schedule is harmless.

`--raw` stages straight from the scans table without the slow `enrich()` step, which fetches
web pages and asks the model to extract facts from each one. It is the right flag for the weekly
schedule; run `merge --stage` without `--raw` when you want the staging list to carry page-extracted
details for every candidate.

Paid AI gig work, meaning annotation, expert tasks and hourly rates on platforms such as Mercor,
Outlier and DataAnnotation, is a third question and has its own saved searches:

```
python hiring\search.py --search gig-bookmarks --md -      # from your bookmarks
python hiring\search.py --live --search gig-live --md -    # same search on X
python hiring\gig_snowball.py                              # grow the word list, writes out\gig-terms.md
```

`gig-bookmarks` reads the database and is free; `gig-live` is disabled until you turn it on. The
classifier puts a hit in the `gig` bucket when a gig phrase appears, or when a platform name and a
rate per hour, week, study or task appear in the same tweet.

Every regex it classifies with is in `hiring\patterns.json`, one group per decision, each pattern paired with a probe it must match. A pattern that does not match its probe stops the whole file loading, so `python hiring\search.py --selfcheck` is the check.

Three traps it already handles, all found on 2026-10-09. Join the search table on `rowid`, never on
`b.id`, because `bookmarks.id` is TEXT and the wrong join takes 382 seconds to return zero rows.
FTS5 takes plain phrases, not regex, so it rejects `\b` and `(?:`. And `twitter user-posts` returns
retweets, which carry the original author and drag spam feeds into the report.

`twitter search` used to return HTTP 404. The cause was a missing `x-client-transaction-id` header,
not a stale query id. Re-apply the fix with `node hiring\fix-twitter-cli.js` after any upgrade.

## 10. Known bug in `fieldtheory search`, and the patch

Fieldtheory 1.3.22 breaks OR. Its `sanitizeFtsQuery()` in
`dist\bookmarks-db.js` wraps every word in quotes the moment it sees one FTS5 operator, so `OR`
becomes a literal word to search for.

```
fieldtheory search "hiring OR hire"   ->   290 results, all of them tweets containing the word "OR"
the same query on bookmarks.db        ->  1259 results, which is the correct number
```

It fails silently. No error, just wrong counts, and a wide query returns an empty array.

`node hiring\fix-fieldtheory.js` patches the installed copy. It is safe to run twice. Run it again after
any `npm update -g fieldtheory`, because npm overwrites the file and the bug comes straight back.

To check it worked, run `fieldtheory search "hiring OR hire" --limit 5000 --json` and count. You
want 1259, not 290.