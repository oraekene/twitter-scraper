# Searching From Every Control Plane

Three ways to search. Pick by who is doing the thinking.

## A. You in PowerShell

You want to look at something yourself, fast, no agent involved.

Open PowerShell anywhere. Paste a command. Done.

```powershell
# What did I bookmark about RL?
fieldtheory search "reinforcement learning" --limit 10

# What has this person posted that I saved?
fieldtheory search "distillation" --author natolambert

# Everything I saved in the last week from verified people, newest first
fieldtheory list --after 2026-09-25 --limit 30

# Just one bookmark, full text
fieldtheory show 2107974143086068209

# What have I been bookmarking a lot? (opens a visual dashboard)
fieldtheory viz

# Save results to a file so you can read them later
fieldtheory search "kubernetes" --limit 50 --json > "$HOME\Desktop\k8s.json"
```

Things to remember. `ft` does not work, it is PowerShell's Format-Table alias, so type
`fieldtheory` in full. Search is OR by default, so `rust async` finds either word. Add `AND`
for both, or wrap in quotes for an exact phrase. Search caps at 20 results unless you raise
`--limit`.

One caveat on this machine. `fieldtheory` 1.3.22 breaks OR because it quotes the word OR instead
of treating it as an operator, and it fails silently. If a count looks far too low, run
`node "C:\Users\rotim\Documents\twitter scraper\hiring\fix-fieldtheory.js"` and try again. Section 9 of
`COMMANDS.md` has the full explanation.

## B. You in OpenCode

You want the agent to search and then explain, compare, or write something from what it finds.

You do not run commands yourself. You ask in plain English and let the agent run them.

```
# You type this to the agent:

Search my bookmarks for anything about retrieval augmented generation,
then group the findings into the distinct approaches people are using.

Search the fork_readmes folder for OAuth implementations and tell me
which ones are worth reading.

I bookmarked a lot about AI agents. Write me a short brief on what
I seem to be most interested in, with the top 5 tweets you'd actually
send to a friend.

What's trending in my bookmarks that I have not acted on? Look for
hiring posts and product launches and tell me which ones I should reply to.
```

What the agent does behind the scenes. For your bookmarks it runs
`fieldtheory search "<terms>" --json` or opens the SQLite database directly. For your files it
uses grep, which scans the markdown and JSONL files. For anything requiring a judgment call
it reads the full text of what it found and reasons over it.

You can also be explicit if you want to steer it:

```
Run fieldtheory search "scaling laws" --limit 30 --json and tell me
which 5 are worth my time and why.

Cross-search: find tweets in my bookmarks that mention tools also
mentioned in C:\Users\rotim\Documents\cloudflare scrapers\fork_readmes
```

## C. You in Claude Code

Same as OpenCode, and slightly better, because the Field Theory skill is already installed there.
You can use the slash command.

```
/fieldtheory

# or in plain English, same as section B
```

I installed the skill at `C:\Users\rotim\.claude\commands\fieldtheory.md` and
`C:\Users\rotim\.codex\instructions\fieldtheory.md`. Codex also has it.

## Where the agent looks

| Question about | Agent searches this |
|---|---|
| Your bookmarks | `.fieldtheory\bookmarks\bookmarks.jsonl`, or `fieldtheory search` |
| Your bookmark markdown | `.fieldtheory\library\`, 94,410 files |
| Fork READMEs | `Documents\cloudflare scrapers\fork_readmes\`, one README per file |
| Pulled threads and accounts | `Documents\twitter scraper\out\` |
| Your scripts | `Documents\twitter scraper\*.py` |

The JSONL is 155 MB but greps in under a second, so the agent can scan all of it cheaply.