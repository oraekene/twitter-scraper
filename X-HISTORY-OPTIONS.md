🌐 last30days v3.28.0 · synced 2026-10-28

What I learned: X's own data archive is the only free source that returns every tweet you ever posted, because every other route stops at 3,200 posts from the top of the timeline, and X says so in its own migration guide. The X API v2 is no longer subscription based, it charges $0.001 per post for reads of your own account, but the same guide caps the user timeline at "most recent 3200 Posts". Your account holds 481,373 posts, so no endpoint can walk back three years, and a 2026 forum report shows busy accounts sometimes stop far earlier. The community evidence agrees: twscrape repeats the 3,200 ceiling, r/DataHoarder threads point at the archive for anything older, and gallery-dl is built for media rather than text. The practical answer is to request the archive today and let the crawler cover only the days after the archive snapshot.

# Every free way to get your complete X history

Measured against @ascully789 on 2026-10-28. The target is every original tweet since 2023-10-28, retweets skipped.

## What I measured on your account

| Fact | Value | How |
| :- | :- | :- |
| Total posts | 481,373 | profile counter |
| Recent rate | about 166 posts a day, 84 percent retweets | last 4 days of crawl |
| Page size, web timeline | 20 tweets, regardless of `count` 20, 40, 100 or 200 | direct test |
| Rate limit, web timeline | 50 requests per 15 minutes | `x-rate-limit-limit` header |
| Depth before empty pages | about 1,000 entries, then only cursors | 43 to 50 pages |
| Bandwidth | about 215 KB per 20 tweet page | response sizes |

Three years at 166 posts a day is about 181,000 entries, about 9,000 pages, about 1.9 GB, and about 48 hours at a 19 second delay. The depth cap makes that number unreachable, which is the whole problem.

## 1. X data archive (free, complete, the answer)

Settings and privacy, Your account, Download an archive of your data. Confirm the password and X emails a link when the archive is built. There is no payment step, and no rate limit applies to the download. X's help page is the authority on turnaround time, and it blocks automated fetches, so treat "about a day" as the historical norm rather than a promise.

The zip contains `data/tweets.js`, which starts with:

```js
window.YTD.tweets.part0 = [ { "tweet": { "id_str": "...", "created_at": "...", "full_text": "...", ... } } ]
```

Large archives split that into `tweets-part0.js`, `tweets-part1.js` and so on, so a parser that reads only `tweets.js` can silently import a fraction. `parse_archive.py` reads every `data/tweets*.js`, in both the zip and the extracted folder.

It also carries `like.js`, `direct-messages.js`, `followers.js`, `account.js` and ad data. Tweets that you deleted before the request are not in it, and media appears as URLs rather than bundled files.

This project already converts it:

```powershell
python parse_archive.py "$HOME\Downloads\twitter-2026-10-28.zip" --handle ascully789 --since 2023-10-28
```

That prints the archive count and oldest date, drops retweets, merges by id into `out/history-ascully789.jsonl`, and keeps the newer live crawl rows when both sources have the same tweet.

Source: https://help.x.com/en/managing-your-account/how-to-download-your-x-archive

## 2. X API v2 owned reads (paid, still capped)

Current pricing is pay per use, with no subscription. Reads of your own posts through `GET /2/users/{id}/tweets` qualify as Owned Reads at $0.001 per post, so 1,000 posts cost $1. There is a monthly cap of 3 million post reads, a per user rate limit of 900 requests per 15 minutes, and `max_results` tops out at 100. New accounts get $20 in credits after saving a card.

The catch is depth, not money. X documents the wall in its own migration guide: "User timeline (user Post timeline) provides access to most recent 3200 Posts; mentions timeline (user mention timeline) provides access to most recent 800 mentions." twscrape's README states the same ceiling. A June 2026 report on X's developer forum adds that on busy accounts the endpoint sometimes drops `next_token` far earlier, around 100 results, with no error. Our 1,000 entry measurement is that failure, not a rate limit. At 3,200 posts the bill is $3.20 and you still only cover the last few weeks.

Sources: https://docs.x.com/x-api/getting-started/pricing.md, https://docs.x.com/x-api/fundamentals/rate-limits.md, https://docs.x.com/x-api/users/get-posts.md, https://docs.x.com/x-api/posts/timelines/migrate/standard-to-twitter-api-v2, https://devcommunity.x.com/t/users-id-tweets-endpoint-not-reaching-3-200-cap-on-some-accounts/267433, https://github.com/vladkens/twscrape

## 3. Private GraphQL with your cookies (free, capped)

This is what `twitter-cli`, `crawl_history.py` and twscrape all do. No API key, no fee, same account cookies. twscrape adds multi account rotation and per account locking, which helps only if you own several accounts, and X's terms discourage that.

Limits are the ones measured above: 20 tweets a page, 50 pages per 15 minutes, roughly 1,000 entries in the current web client and about 3,200 according to twscrape. It is the right tool for the last few days and the wrong tool for three years.

## 4. Search (free, incomplete)

`from:ascully789` looked like the shortcut and is not. On a day with 32 posts it returned 19, and over four days it returned 20 of 111 timeline originals. Search indexes a subset, so it cannot be the base of a complete archive. It is still useful to fill a specific gap once you know which ids are missing.

## 5. Nitter and mirrors (free, dead)

Nitter is over. Its README records cease and desist letters from X Corp on 24 August 2026, demanding a permanent takedown of every instance and of the repository, and the maintainer is asking for legal help. Even a working mirror reads the same timeline with the same depth cap, so there is no completeness gain.

## 6. gallery-dl (free, media only)

gallery-dl has a Twitter extractor and it is well maintained, with 20K stars and frequent releases. It downloads images and video, not a clean tweet text corpus, and r/DataHoarder users report it degrading past a few hundred items per account. Use it after the archive if you want the actual image files.

Source: https://github.com/mikf/gallery-dl

## 7. Paid scrapers (not free, not complete)

Apify actors, Bright Data and similar services sit on the same timeline and search surfaces. They resell the same 3,200 entry ceiling and the same partial search index, with a markup. None of them can produce a verified complete history for an account this size, so paying does not solve the problem the archive solves for free.

## 8. Wayback Machine and caches (free, partial)

Occasional snapshots of your profile exist, and each one captures whatever was on screen. Coverage is random, pagination is not archived, and there is no way to reconstruct 481,373 posts from it. Worth a look for a specific deleted tweet, not for a corpus.

## What does not exist

There is no official endpoint, no premium feature and no third party service that exports the full history of a large account. X Premium analytics exports impressions and engagement, not tweet text. TweetDeck is gone. The archive is the only complete path, which is why every data hoarding thread ends there.

## The plan for your account

1. Request the archive now. It is free and it runs while you do other things.
2. When the link arrives, run `parse_archive.py` with `--since 2023-10-28`. That gives you the complete history up to the snapshot date.
3. Run `crawl_history.py` for the gap between the snapshot and today, at `--delay 19`. That window is days, not years, so the depth cap never bites.
4. Keep `out/history-ascully789.jsonl` as the single merged file. Both tools already merge by id and keep the fresher copy.

Do not restart a three year crawl. It will spend two days and 1.9 GB to collect six days of tweets and then stall on empty pages.

## Sources

- X archive help: https://help.x.com/en/managing-your-account/how-to-download-your-x-archive
- X API pricing, Owned Reads at $0.001 per post: https://docs.x.com/x-api/getting-started/pricing.md
- X API rate limits, 900 requests per 15 minutes: https://docs.x.com/x-api/fundamentals/rate-limits.md
- X API user posts endpoint, `max_results` maximum 100: https://docs.x.com/x-api/users/get-posts.md
- X migration guide, user timeline gives the most recent 3,200 posts: https://docs.x.com/x-api/posts/timelines/migrate/standard-to-twitter-api-v2
- X developer forum, endpoint dropping `next_token` before 3,200 on busy accounts: https://devcommunity.x.com/t/users-id-tweets-endpoint-not-reaching-3-200-cap-on-some-accounts/267433
- twscrape, about 3,200 tweet timeline limit: https://github.com/vladkens/twscrape
- nitter takedown notice: https://github.com/zedeus/nitter
- gallery-dl: https://github.com/mikf/gallery-dl
- r/DataHoarder, How to archive a Twitter account: https://www.reddit.com/r/DataHoarder/comments/1xf79ow/how_to_archive_a_twitter_account/
- r/DataHoarder, How To Archive / Save Tweets From An X / Twitter Account: https://www.reddit.com/r/DataHoarder/comments/1xh1j2c/how_to_archive_save_tweets_from_an_x_twitter/
- r/DataHoarder, gallery-dl limits past a few hundred: https://www.reddit.com/r/DataHoarder/comments/1wx34fl/twitter_mass_media_downloader_that_work/

<!-- PASS-THROUGH FOOTER -->
✅ All agents reported back!
├─ 🟠 Reddit: 12 threads │ 1,421 upvotes │ 572 comments
├─ 🔵 X: 3 posts │ 542 likes │ 23 reposts
├─ 🟡 HN: 16 stories │ 1,073 points │ 210 comments
├─ 🐙 GitHub: 2 items │ 23,169 stars │ 1,095 comments
├─ 🗣️ Top voices: @yapyzka, @obie, @KonradSzymaniak │ r/DataHoarder, r/selfhosted, r/uBlockOrigin
├─ 🕒 Recent evidence is thin: only 10 of 33 dated items are from the last 7 days.
└─ 📎 Raw results saved to ~/Documents/Last30Days/free-ways-to-export-your-complete-twitter-x-account-history-raw-v3.md
<!-- END PASS-THROUGH FOOTER -->
