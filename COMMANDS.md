# Command Reference

Two tools. `fieldtheory` is the brain (local database, search, markdown). `twitter` is the fetcher
(talks to X live). Note: `ft` is a PowerShell alias for Format-Table, so never type `ft`.

## 1. Keep everything up to date

| Command | Why you run it |
|---|---|
| `python sync_bookmarks.py` | Pull new bookmarks. Repeat until it stops saying "max runtime reached". |
| `python crawl_tweets.py threads --limit 200 --top 20` | Expand full threads behind every bookmarked tweet. Resumable. |
| `python crawl_tweets.py account <handle> -n 2000` | Pull every tweet from an account, yours or anyone's. |
| `python crawl_tweets.py replies <id> --top 10` | Top N replies to one tweet, ranked by engagement. |
| `python crawl_tweets.py thread <id> --save` | Full thread behind one tweet. |

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
| `node hiring\fix-fieldtheory.js` | Re-applies the search fix below. Run after `npm update -g fieldtheory`. |

## 9. Find hiring posts and job openings

Everything lives in the `hiring` folder. See `hiring\README.md`. Two jobs, one shared engine.

```
python hiring\search.py                          # your bookmarks
python hiring\search.py --json out\h.json        # same, full text, nothing truncated
python hiring\search.py --days 8 --md -          # only the last 8 days
python hiring\search.py --live --min-likes 30    # search X for a query
python hiring\search.py --watchlist hiring\watchlist.txt   # X, from the watchlist
pwsh -File hiring\weekly.ps1                     # schedule the bookmark hunt
pwsh -File hiring\weekly-twitter.ps1             # schedule the X hunt
```

The X half runs two passes. A live search finds accounts you have never heard of but returns noise, so
raise `--min-likes`. The watchlist is the higher signal read because you chose the accounts. Two
seconds between accounts is required or X answers HTTP 429 halfway through and the run looks
successful.

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