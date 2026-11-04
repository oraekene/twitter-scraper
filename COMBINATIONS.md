# COMBINATIONS: last30days x sciencemadereadable x your three local resources

Every mode and scenario for combining the two global skills with:
R1 = live twitter scraper (twitter CLI + to_envelope.py --live)
R2 = bookmarks corpus (94,410 posts, fieldtheory + hiring + to_envelope.py --bookmarks)
R3 = personal_context (essays, notes, projects, cold-email, sites; md/txt/pdf)

## Legend

- Trigger: AUTO = the model starts it without you naming a skill; ASK = you request it; OFFER = the model proposes it first; SCHED = a scheduled task runs it.
- Status: [now] works today; [tweak] needs a small script change; [config] needs the one-time cookie copy into ~/.config/last30days/.env; [blocked] needs a missing dependency.
- Every entry is a real capability of a real flag or command; nothing here is hypothetical tooling.

## Core run recipes

Live envelope into the engine:
  python to_envelope.py --topic "TOPIC" --live --max 500 [--search-args -t latest]
  python "...\last30days.py" "TOPIC" --x-posts "out\x-posts.json" [--quick|--deep] [--emit html]

Bookmark envelope into the engine:
  python to_envelope.py --topic "TOPIC" --bookmarks --days 30 --max 500
  python "...\last30days.py" "TOPIC" --x-posts "out\x-posts.json"

Personal context as a private ranked source:
  python "...\last30days.py" "TOPIC" --corpus "C:\Users\rotim\Videos\personal_context\my notes" [--corpus-all-time]

Science check:
  https://ask.sciencemadereadable.com/QUESTION?k=8&year_from=2020&type=review
  https://api.sciencemadereadable.com/api/data/search?q=QUOTED+THING

---

# PART A: last30days x live scraper (R1)

## A1. X-side feed modes (what fills the envelope)

1. Top lane, plain keywords (ASK) - highest-signal ranking for the topic. [now]
2. Latest tab via --search-args -t latest (ASK) - real-time stream, no ranking, catches a breaking moment. [now]
3. Photos tab via -t photos (ASK) - chart screenshots, launch visuals, infographic claims. [now]
4. Videos tab via -t videos (ASK) - demo clips and talks the text tabs miss. [now]
5. Exact phrase in quotes in the query (ASK) - kills fuzzy matches, "context engineering" style. [now]
6. OR of synonyms in the query (ASK) - widen recall for a fuzzy concept. [now]
7. NOT / -term narrowing (ASK) - cut a noisy counterfeit usage. [now]
8. min_faves:100 style operators (ASK) - attention floor inside the query. [now]
9. min_retweets:50 operator (ASK) - spread floor, finds the posts that traveled. [now]
10. since:/until: operators (ASK) - sub-windows inside the 30-day frame. [now]
11. from:handle operator (ASK) - first-party voice of the subject. [now]
12. to:handle or @handle (ASK) - what people ask or tell them. [now]
13. filter:verified etc. (ASK) - influencer-only reading of a topic. [now]
14. lang:ja / lang:de operators (ASK) - non-English lanes for the same story. [now]
15. $TICKER cashtag (ASK) - market talk lane next to the general chatter. [now]
16. url:dk-domain operator (ASK) - who shares a specific outlet. [now]
17. conversation_id: or thread_id: (ASK) - pull a whole discussion by id. [now]
18. --from / --to flags (ASK) - CLI-level author lanes without operator syntax. [now]
19. --lang en flag (ASK) - single-language feed. [now]
20. --since / --until flags (ASK) - date bounds; with --as-of the script now closes the upper bound too. [now]
21. --has links / images / videos (ASK, via --search-args) - media-bearing posts only. [now]
22. --exclude replies / links (ASK, via --search-args) - remove noise classes. [now]
23. --min-likes 100 (ASK) - engagement floor at the CLI level. [now]
24. --min-retweets (ASK, via --search-args) - spread floor at the CLI level. [now]
25. -n 50 to -n 1000 depth (ASK/OFFER) - row budget; script chunks into 500-row calls. [now]
26. --as-of 2026-06-01 (ASK) - envelope around a past date; pairs with engine --as-of. [now]
27. Multiple sub-topic pulls into one envelope (OFFER) - run the script twice with different --out then merge calls by hand, or widen terms. [tweak: --merge flag]
28. Account history pull, crawl_tweets user-posts (ASK) - feed a single account's last 30 days to the engine. [tweak: --from-file mapping for user-posts JSON]
29. Thread expansion pull (ASK) - feed a full thread as context rows. [tweak: --from-file]
30. Replies tree pull (ASK) - feed a whole reply tree for sentiment depth. [tweak: --from-file]

## A2. Engine modes over a live envelope

1. Quick brief (ASK) - 20-30 second scan with X counted from your pull. [now]
2. Deep brief (ASK) - full pass, more fetches and synthesis. [now]
3. X-only brief, --search x (ASK) - pure-X read, no other sources. [now]
4. Restrict to x,corpus (ASK) - your pull plus your notes only. [now]
5. Executive register, --register exec (ASK) - decision-grade summary. [now]
6. Developer register (ASK) - API and tooling detail kept in. [now]
7. Creator register (ASK) - audience and content angles kept in. [now]
8. ELI5 register (ASK) - plain-language version. [now]
9. HTML emit (ASK) - shareable report file. [now]
10. Markdown emit (ASK) - file for your notes. [now]
11. JSON emit (ASK) - machine-readable for follow-up scripts. [now]
12. Context emit (ASK) - compact prompt-ready block for another model. [now]
13. Brief emit (ASK) - short form only. [now]
14. --store run into the research DB (ASK/OFFER) - keeps the run for digests and watchlists. [now]
15. --deep-research add-on (ASK) - extra agentic depth pass. [now]
16. --drill into a named subtopic (ASK) - second pass zoomed. [now]
17. --discover-shallow adjacent probe (OFFER) - finds the neighbor topic you missed. [now]
18. --hiring-signals over live posts (ASK) - who is hiring, from the live lane. [now]
19. --verify-freshness (OFFER) - confirm posts are still up before quoting. [now]
20. --max-per-source / --max-source-fetches tuning (ASK) - throttle a costed run. [now]
21. --polymarket-keywords (ASK) - prediction-market numbers beside X chatter. [now]
22. --subreddits focus (ASK) - cross-check X against chosen subreddits. [now]
23. --github-repo enrichment (ASK) - when live posts link a repo, get the repo facts. [now]
24. --github-user enrichment (ASK) - when an X handle equals a builder. [now]
25. --as-of + envelope --as-of (ASK) - a faithful past-month brief. [now]
26. Two runs, live vs bookmarks envelope, same topic (ASK) - gap analysis: world vs your radar. [now]
27. Watchlist topic with fresh live envelope per run (SCHED) - recurring pulse. [now]
28. Briefing digest via briefing.py over stored runs (ASK/SCHED). [now]
29. Comparison run with per-entity x_posts in --competitors-plan (ASK) - script emits one topic lane; add a second envelope per entity by hand. [tweak: --competitors-plan builder]
30. Handle lanes: from/mention/related rows in the envelope (ASK) - fills the engine's handle lanes so --x-handle runs get their lanes from your pulls. [tweak: --lane from --from-pull]
31. --x-related (ASK) - looks-alike accounts next to the subject. [tweak: same lane work]
32. --x-handle focus (ASK) - person-centered brief, rest of sources as usual. [tweak: same lane work]
33. --web-backend / --perplexity-search-type (ASK) - requires a Perplexity key. [config]
34. --amazon-query (ASK) - product research lane. [blocked: brightdata not installed]
35. --telegram-sources (ASK) - the flag exists; telegram is not in the default source list, treat as unverified until a run shows it. [verify]
36. Historical backfill month by month (ASK) - loop --as-of across months for a timeline. [now]

## A3. Scenarios that fire the skill automatically (AUTO)

1. "What are people saying about X" - envelope first, then brief.
2. "What is the reaction to Y" - news pulse.
3. "Is X still alive / still relevant" - ecosystem health.
4. "What happened with X this month" - catch-up.
5. "Who is hiring for Z right now" - hiring lane.
6. "Is the buzz about X real" - due diligence.
7. "Compare the vibes of X vs Y" - engine comparison run.
8. "What did I miss this week" - 7-day envelope and brief.
9. "Draft a reply to this debate" - live pulse informs the reply.
10. "What is the sentiment before I post" - pre-post check.
11. "Should I care about X" - triage by evidence of traction.
12. Keynote or launch day live coverage - latest tab envelope.
13. Backlash or drama pulse - sentiment and scale.
14. Market sentiment on a ticker - cashtag lane.
15. Ecosystem tooling survey - what builders actually use now.
16. Competitor activity scan before outreach.
17. Person of interest recent activity.
18. Regional pulse in another language - lang lane.
19. Pre-purchase research on a product - amazon lane when available, X lane now.
20. Postmortem reading after an incident - what practitioners said.

---

# PART B: last30days x bookmarks (R2)

## B1. Extraction modes (what fills the bookmark envelope)

1. Topic terms AND match (ASK) - envelope of everything you saved about a topic. [now]
2. --days alignment with the engine window (ASK) - both sides read the same window. [now]
3. --max up to 1000 (OFFER) - your whole matching pile. [now]
4. --days 90 with engine --days 90 (ASK) - quarterly radar read. [now]
5. --as-of past date (ASK) - what your radar looked like in a chosen month. [now]
6. Author-only extraction, from fieldtheory search --author results (ASK) - what you saved from one person. [tweak: --ids-file]
7. Category swipe, from fieldtheory list --category (ASK) - e.g. only ai saves. [tweak: --ids-file]
8. Folder swipe, from fieldtheory list --folder (ASK) - your X bookmark folders. [tweak: --ids-file]
9. Engagement floor for saves (ASK) - only saves whose posts did big numbers. [tweak: --min-likes for bookmarks]
10. Bookmark-count top-N (ASK) - your most re-saved posts first. [tweak: sort flag]
11. Date-bounded extraction beyond the term filter (ASK) - a specific week. [tweak]
12. Quote-heavy saves only (ASK) - posts you saved for the commentary. [tweak]

## B2. Engine modes over the bookmark envelope

1. Quick brief "what did I save about X and why does it matter now" (ASK) - your radar summarized. [now]
2. Deep brief with saves as the X lane and public sources as the rest (ASK) - radar vs world. [now]
3. X-only brief from saves (ASK) - your private feed treated as a feed. [now]
4. --store the run (ASK) - builds your radar history. [now]
5. Register variants exec/dev/creator/eli5 over saves (ASK) - four lenses. [now]
6. --hiring-signals over saves (ASK) - saved hiring posts only, who you noticed. [now]
7. --github-repo enrichment for saved launches (ASK). [now]
8. --github-user enrichment for saved authors (ASK). [now]
9. --polymarket-keywords over saves (ASK). [now]
10. --verify-freshness over saves (OFFER) - are the saved posts still up. [now]
11. --drill a saved subtopic (ASK). [now]
12. --discover-shallow from a saved topic (OFFER). [now]
13. --as-of past window with saved slice (ASK) - historical radar brief. [now]
14. --days 7 weekly radar brief (SCHED) - the routine. [now]
15. --days 90 quarterly catch-up (ASK). [now]
16. --subreddits to see whether your saves track Reddit or not (ASK). [now]
17. Live vs bookmarks two-run compare on one topic (ASK) - the gap between what you save and what happens. [now]
18. Watchlist on a saved topic, envelope from saves each run (SCHED). [now]
19. Digest over stored radar runs, briefing.py (SCHED). [now]
20. Quiet-topic check (ASK) - envelope with few rows still valid; "the radar has this, the world does not". [now]
21. Widen-and-retry loop when terms match nothing (OFFER) - script exits clean; broaden terms and rerun. [now]
22. Competitors plan from two saved-author envelopes (ASK). [tweak]
23. HTML emit for a private share (ASK) - remember saves are private. [now]
24. Context emit for feeding another model your radar slice (ASK). [now]
25. Envelope plus --corpus at the same time (ASK) - your saves plus your notes in one brief. [now]

## B3. Free-standing carve modes (no engine; fieldtheory + hiring + sem + triage)

1. Keyword search across saves (ASK) - "what did I save about X". [now]
2. FTS5 AND / OR / NOT / "exact phrase" (ASK) - precise recall. [now]
3. --author filter (ASK) - one author's saved history. [now]
4. --after / --before date bounds (ASK) - time-boxed recall. [now]
5. --limit tuning (ASK) - 20 default, raise for a sweep. [now]
6. --json output (ASK) - pipe into other steps. [now]
7. list --category swipe (ASK) - walk one category. [now]
8. list --folder swipe (ASK) - walk one folder. [now]
9. stats overview (ASK/OFFER) - corpus health. [now]
10. categories distribution (ASK) - where your attention went. [now]
11. domains distribution (ASK) - which outlets dominate your saves. [now]
12. folders distribution (ASK) - folder balance. [now]
13. viz dashboard (ASK) - visual pattern read. [now]
14. show one bookmark in detail (ASK). [now]
15. recent files for "that file" references (AUTO) - resolves your references to real files. [now]
16. classify whole corpus with an LLM (ASK) - category and domain pass, needs claude or codex CLI. [now]
17. classify-domains (ASK) - subject domain labels. [now]
18. model switch for classification (ASK). [now]
19. index rebuild (maintenance) - after big syncs. [now]
20. sync --since (ASK/SCHED) - pull new bookmarks. [now]
21. auth / status / path housekeeping (ASK). [now]
22. fieldtheory find (ASK) - search your written note titles. [now]
23. fieldtheory grep (ASK) - search inside your notes' markdown. [now]
24. fieldtheory ls / tree (ASK) - browse the library tree. [now]
25. fieldtheory cat / head / meta (ASK) - read or inspect a note. [now]
26. fieldtheory open / panel (ASK) - open a note or get its panel link. [now]
27. hiring search --search NAME (ASK) - saved searches over the corpus. [now]
28. hiring search --live (ASK) - the same searches against the live pipe. [now]
29. hiring watchlist add / run (ASK/SCHED) - standing watch. [now]
30. hiring ctl.py list / add / run (SCHED) - manage scheduled searches. [now]
31. triage.py over hits (ASK) - shortlist the good ones. [now]
32. sem.py conceptual search (ASK) - finds saves that match by meaning. [now]
33. TwitterBookmarkWeeklyScan task (SCHED) - the existing weekly job. [now]
34. Science results into the library via sciencemadereadable open links (ASK) - file found papers as notes for later. [now]

---

# PART C: last30days x personal_context (R3)

## C1. The corpus hook (first-class engine source)

1. --corpus "my notes" (ASK/AUTO) - brief fuses your thinking with the public conversation; corpus appears in available_sources. [now]
2. --corpus "my projects" (ASK) - specs and plans sit beside market reality. [now]
3. --corpus "context_docs" (ASK) - your essays and answers vs the field. [now]
4. --corpus cold-email folders (ASK) - angle material beside prospect chatter. [now]
5. --corpus website copy (ASK) - your public claims vs live reception. [now]
6. Repeat the flag to stack folders in one run (ASK). [now]
7. --corpus-all-time (ASK) - include old notes; default favors recency. [now]
8. md / txt / pdf files are read; check the help text for the exact set (md, txt, pdf). [now]

## C2. Engine modes over corpus

1. Quick brief with corpus (ASK). [now]
2. Deep brief with corpus (ASK). [now]
3. x,corpus-only run (ASK) - your pull plus your notes, nothing else. [now]
4. Registers exec / dev / creator / eli5 (ASK) - four framings. [now]
5. Emits html / md / json / context / brief (ASK) - five output shapes. [now]
6. --store corpus runs (ASK) - which notes matched which topics. [now]
7. --drill a note's topic (ASK). [now]
8. --discover-shallow from note keywords (OFFER). [now]
9. --as-of with corpus (ASK) - "this idea, six months later". [now]
10. --days tuning with corpus (ASK) - 7 day pulse or 90 day arc. [now]
11. Watchlist theme with corpus each run (SCHED). [now]
12. Digest over stored corpus runs (SCHED). [now]
13. One folder per run, A/B across projects (ASK/OFFER). [now]
14. --hiring-signals plus corpus (ASK) - market demand vs your skill notes. [now]
15. --github-repo plus corpus (ASK) - spec vs repo reality. [now]
16. --polymarket-keywords plus corpus (ASK). [now]
17. --subreddits plus corpus (ASK). [now]

## C3. Reverse direction: briefs land back in personal_context

1. Save the brief to the notes pipeline as a dated note (ASK/AUTO). [now]
2. Update a project's status note with the brief's findings (ASK). [now]
3. Add evidence links to an application answer draft (ASK). [now]
4. Add proof points to a cold-email angle file (ASK). [now]
5. Fill FAQ and talking points for a website page (ASK). [now]
6. Gather deck slide source material (ASK). [now]
7. Back a resume claim with links (ASK). [now]
8. Back grant-fit answers with evidence (ASK). [now]
9. Turn a brief into a reading list note (ASK). [now]
10. Build a people-to-follow list from the live lane (ASK). [now]
11. Log contrarian angles where notes and public consensus conflict (OFFER). [now]
12. Collect quote bank material from top posts (ASK). [now]
13. Queue threads worth replying to, with receipts (ASK). [now]
14. Weekly roundup note (SCHED). [now]
15. Competitor watch note (SCHED). [now]
16. Groom the ideas backlog using brief findings (ASK). [now]
17. Write the brief into the fieldtheory Library and index it (ASK). [now]
18. Mirror to the Obsidian vault (ASK) - obsidian-vault skill. [now]
19. Keep the notes chronology updated in "my notes" (SCHED). [now]
20. Archive raw envelopes next to the notes for audit (OFFER). [now]

## C4. Triggers

1. AUTO when drafting essays or applications: the skill routes to corpus without being named. (AUTO)
2. OFFER when a topic matches folder names it noticed. (OFFER)
3. ASK variants: "use my notes while you research". (ASK)
4. SCHED: weekly note-folder sweep with the new window. (SCHED)

---

# PART D: sciencemadereadable x live scraper (R1)

## D1. Claim intake modes (read the pull, extract claims)

1. One viral claim in one post (ASK) - verify that single sentence.
2. A thread's key claims (ASK) - walk them, one query each.
3. Quote-tweet dispute (ASK) - both sides' claims side by side.
4. Top-N posts ranked by engagement, claims extracted (ASK) - what spread the most.
5. Claim inside a linked blog or substack (ASK) - fetch page, extract, query.
6. Claim inside a linked video (ASK) - yt-dlp transcript, then claim, then query.
7. Screenshot chart claim (ASK) - numbers in image read out, then checked.
8. Poll-driven claim, "90 percent of devs" (ASK).
9. Prediction claim from the Polymarket lane (ASK).
10. Health or fitness claim (ASK).
11. AI benchmark claim (ASK).
12. Nutrition claim (ASK).
13. Hiring-signal empirical claim, "everyone is hiring for RAG" (ASK).
14. "Studies show" with no study linked (ASK) - hunt the study.
15. Contradictory claims across accounts (ASK) - adjudicate.
16. Effect-size question, "how big is the effect really" (ASK).
17. Causation from correlation (ASK).
18. Replication status of a famous result (ASK).
19. Novelty claim, "this is new" (ASK) - is it?.
20. Consensus claim, "experts agree" (ASK) - do they?.

## D2. Science service query modes

1. Plain question to the web view with k results (ASK). [now]
2. Exact phrase in quotes (ASK) - pin terminology. [now]
3. AND / OR / NOT (ASK) - boolean narrowing. [now]
4. k tuning 4 to 20 (ASK) - breadth choice. [now]
5. year_from / year_to (ASK) - recency window. [now]
6. type=review (ASK) - reviews only. [now]
7. open_access=true (ASK) - readable papers only. [now]
8. abstracts=false (ASK) - summary-first rendering. [now]
9. JSON endpoint for piping (ASK). [now]
10. Plain-language links in results (ASK) - readable summaries. [now]
11. llms.txt guide for exact syntax (ASK). [now]
12. Budget discipline, 30 requests per minute (constraint). [now]
13. Jargon mapping before the query (AUTO) - translate lay claim into field terms. [now]
14. Zero-hit refine loop (OFFER) - loosen, retry. [now]

## D3. Scenario pairs (live claim in, evidence out)

1. Viral claim, verify, reply with paper links (ASK).
2. Thread critique: each claim checked, then a correction draft (ASK).
3. Newsletter idea: check evidence before writing (ASK).
4. Pre-share check on a post you are about to amplify (ASK).
5. Product decision: find the best evidence (ASK).
6. Briefing claim: paper check before the brief goes out (AUTO inside Part A runs).
7. Labor claim from hiring chatter: check with labor economics (ASK).
8. Benchmark claim: check against meta-analysis of benchmarks (ASK).
9. Controversy: pull both sides' literature (ASK).
10. Folk wisdom in the feed: find reviews (ASK).
11. Dose questions: dose-response studies (ASK).
12. Talk prep: literature scan of the talk's claims (ASK).
13. Essay claim: citation gathering (ASK).
14. Debate prep: strongest counter-evidence (ASK).
15. Trend-vs-evidence gap report (ASK).
16. Prediction market vs literature (ASK).
17. Popular framing vs literature framing (ASK).
18. Non-English claims: check against English literature (ASK).
19. Screenshot statistic: find the source (ASK).
20. "Clinically proven" in product copy found on X: verify (ASK).
21. Retracted paper check when someone cites an author (ASK).
22. Sample-size sanity check of a quoted study (ASK).
23. Significance vs effect size explainer for a hot dispute (ASK).
24. Single study vs meta-analysis check (ASK).
25. Consensus position summary with reviews (ASK).
26. Replication crisis angle on a trending classic (ASK).
27. Funding or conflict angle if a debate gets heated (ASK).
28. "What would change my mind" evidence list for a claim (OFFER).

---

# PART E: sciencemadereadable x bookmarks (R2)

1. Claim hunt in saves: search "study", "research shows", "paper" (ASK) - find checkable saves.
2. Verify a saved claim (ASK).
3. Reading list build: saves turned into papers, deduped (ASK).
4. Pre-reshare check on a saved thread (ASK).
5. Counter-evidence hunt for a saved opinion piece (ASK).
6. Saved "X causes Y" check (ASK).
7. Saved AI benchmark claims check (ASK).
8. Saved nutrition claims check (ASK).
9. Saved health claims check (ASK).
10. Saved economics claims check (ASK).
11. Find the study a saved post references but does not link (ASK).
12. Compare claims across authors in your saves (ASK).
13. "What the evidence says" summary of your save pile on one topic (ASK).
14. Curate the top narrowly defensible claims from saves (ASK).
15. Annual "what I learned", saves plus citations (ASK).
16. Saved podcast or video claim, transcript then check (ASK).
17. Saved stat, "70 percent of" provenance check (ASK).
18. Reviews for a saved contrarian take (ASK).
19. Map saved books to their paper base (ASK).
20. Pre-purchase check on something recommended in saves (ASK).
21. Health decision from saves (ASK).
22. Debate prep from saves (ASK).
23. Cold-email or grant claims your saves already support (ASK).
24. Turn ten saves into a literature map (ASK).
25. What changed since the save, newer studies check (ASK).
26. Replication check for saved classics (ASK).
27. Meta-analysis sweep for a saved topic (ASK).
28. Zero-hit broaden loop on a fussy phrase (OFFER).
29. fieldtheory search for claim keywords, --json export feeding the science queries (ASK).
30. Saved-domain check: are you saving one-manufactured-consensus outlets (ASK).
31. Save found papers as notes so the next check starts from your side (ASK).

---

# PART F: sciencemadereadable x personal_context (R3)

1. Essay claims, evidence pack before publishing (AUTO when writing) (ASK).
2. Application answers, citations added (ASK).
3. Grant-fit claims, reviews attached (ASK).
4. Cold-email proof points, verified (ASK).
5. Resume bullets, backing stats found (ASK).
6. Deck claims, studies fetched (ASK).
7. Website copy claims, evidence checked (ASK).
8. Book outline, literature map (ASK).
9. A question in notes, answered with papers (ASK).
10. Project spec assumptions, evidence check (ASK).
11. Health questions in notes, literature scan (ASK).
12. Ideas backlog, triaged by existing evidence (ASK).
13. Novelty check, "is this idea already done" (ASK).
14. Contrarian essay, strongest opposing evidence surfaced (OFFER).
15. FAQ answers, citations added (ASK).
16. Humanized or edited text: keep numbers and named claims true (ASK).
17. Podcast notes, claims checked (ASK).
18. Reading list gaps filled from reviews (ASK).
19. Thesis sections, sources found (ASK).
20. Prospect research: their public claim, literature context (ASK).
21. Interview answers, evidence-backed (ASK).
22. Course lessons, sources found (ASK).
23. Newsletter issues, citations added (ASK).
24. Long-form article, full evidence base (ASK).
25. Personal supplement or training decision, evidence scan (ASK).
26. Fact-check your own old notes, self-corrections (ASK).
27. Quote accuracy check across your writing (ASK).
28. Statistic provenance for a number you repeat (ASK).
29. Build a citation library note from results (ASK).
30. Science-informed angle generation: engine brief with corpus, then claims inside it checked (ASK).
31. Contradiction surfacing: your notes vs the literature, flagged (OFFER).
32. Territory map: which of your ideas have reviews available and which are untested (ASK).

---

# PART G: both skills x all three resources

1. Topic to live envelope, brief, then every claim in the brief checked (ASK).
2. Bookmark topic to envelope, brief, then science pass, then a reply draft (ASK).
3. Corpus topic, brief, then science pass on the brief's claims (ASK).
4. Trend plus claim combo in one session (ASK) - Part A plus Part D.
5. Weekly pipeline: watchlist topic, live envelope, store, science check of claims, digest note (SCHED).
6. Person of interest dossier: live posts, claims extracted, papers they cite and papers they miss (ASK).
7. Competitor claims audit: their marketing vs the evidence (ASK).
8. Pre-republish check for a launch: live pulse, saved context, evidence check (ASK).
9. Fact-check post with receipts for a debated topic: X posts plus papers in one output (ASK).
10. Essay pipeline: corpus angle, live reaction, paper base (ASK).
11. Application answer pipeline: corpus proof, public trend, evidence (ASK).
12. Grant pipeline: literature map, trend relevance, your notes (ASK).
13. Newsletter pipeline: saved radar, live pulse, verification, issue draft (ASK).
14. Thread drafting with receipts: claims only you can back (ASK).
15. Decision memo: saves, pulse, notes, papers, one page (ASK).
16. Market check plus evidence: ticker lane brief, then literature on the industry (ASK).
17. Hiring trend plus labor papers (ASK).
18. Product idea check: saves plus corpus plus papers (ASK).
19. Anti-slop pass: humanized text's numbers checked against both live data and papers (ASK).
20. Annual review: saves, notes, papers (ASK).
21. Debate prep full stack (ASK).
22. Content calendar from trends, each item verified (OFFER).
23. Pre-reply guard: before replying to a claim in your feed, one science query (ASK).
24. Book chapter research stack (ASK).
25. Due diligence on an influencer: live behavior, saved history, claim record (ASK).
26. Podcast prep with evidence (ASK).
27. Health decision full stack: saves, corpus notes, studies, live sentiment (ASK).
28. Policy claim check: live debate, your notes, studies (ASK).
29. Course creation stack: saves, notes, papers (ASK).
30. Winning angle finder: gaps between live conversation, your saves, your notes, and the literature (ASK).

---

# Appendix: one-time items and known ceilings

1. [done 2026-10-15] AUTH_TOKEN and CT0 were copied into C:\Users\rotim\.config\last30days\.env. The engine now reports x as an available source with backend bird, and a live X-only quick run fetched 6 posts with no envelope. The envelope remains the richer route for deep or filtered pulls.
2. [blocked] brightdata install would unlock --amazon-query; not installed on purpose, it is paid.
3. Envelope ceiling: one topic lane per envelope; 500 rows per call, 1000 total, 20 calls, fresh within 6 hours, window must cover the engine run. Comparisons and handle lanes need the [tweak] items in A2.
4. The engine treats the envelope as the whole X source for that run. Do not also expect its own X backend to add rows; that is the [config] item above.
5. Bookmarks are private. Think before an HTML emit or a shared brief.
6. Science service limit: 30 requests per minute; batch claims, do not spam.
