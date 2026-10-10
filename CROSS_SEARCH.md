# Searching Across Files And Bookmarks Together

The case you asked about: one question, two sources. Your files on disk, and your 94,410
bookmarks. Here is exactly what it looks like from your side.

## The setup, once

Everything already works. Nothing to install. Confirm it in one line:

```powershell
cd "C:\Users\rotim\Documents\twitter scraper"; python test_sync.py
```

Expected output: `selftest ok`.

## Step 1. You ask the agent

Open OpenCode in any folder and type this, exactly as written:

```
Search two sources for how people implement OAuth:

1. C:\Users\rotim\Documents\cloudflare scrapers\fork_readmes
2. My twitter database, which has 94,410 bookmarks

For the READMEs, tell me which repos actually ship working OAuth code
and how they each handle token refresh.

For my bookmarks, tell me which of MY saved tweets discuss OAuth problems
I should know about, especially bugs people hit in production.

Then tell me where those two worlds agree, and where they disagree.
```

## Step 2. What the agent does

You can watch this happen if you want. The agent makes roughly these calls:

```
# Source 1: your files. Grep is fast because READMEs are small.
Grep  pattern "oauth|refresh.?token"  path="C:\Users\rotim\Documents\cloudflare scrapers\fork_readmes"
Read  the 2-3 most promising README files it found

# Source 2: your bookmarks. Either the CLI or a direct grep.
fieldtheory search "oauth token refresh" --limit 40 --json
Select-String -LiteralPath "C:\Users\rotim\.fieldtheory\bookmarks\bookmarks.jsonl" -Pattern 'oauth'
```

Then it reads the full text of what it found and reasons. On this machine the JSONL grep takes
about 0.6 seconds for 155 MB, so it never needs to ask permission or page through anything.

## Step 3. You get an answer with sources

The answer arrives in chat, and every claim carries a link or a file path. You can then verify
any single claim yourself in PowerShell:

```powershell
# Check the agent's bookmark claim yourself
fieldtheory search "oauth token refresh" --limit 10 --author <handle>

# Check the agent's file claim yourself
Select-String -LiteralPath "C:\Users\rotim\Documents\cloudflare scrapers\fork_readmes\oraekene__agentic-stack__README.md" -Pattern "oauth"
```

## Variants worth knowing

Narrow to one source. Drop item 2 from the prompt.

Search your own written notes, not bookmarks. Say "search my library notes", and the agent
uses `fieldtheory library search` instead.

Search bookmark markdown rather than raw data. Say "search the exported markdown", and it
greps `.fieldtheory\library\` instead. Same content, one file per bookmark, easier to quote.

Include the threads you pulled. Say "also search Documents\twitter scraper\out", which adds
your expanded threads and full accounts.

Ask for a written artefact. Say "save that as a brief", and the agent runs
`fieldtheory new brief "<title>"` to write it into your library so it survives the chat.

Ask it to come back later. Say "check every Friday what is new in my bookmarks about X", and
the agent sets up a scheduled run.

## The one thing that trips people up

Tell the agent the paths exactly. `C:\Users\rotim\Documents\cloudflare scrapers\fork_readmes`
has a space in it, and that folder holds about 2,000 README files, so a vague instruction like
"check my cloudflare stuff" makes the agent guess and possibly look in the wrong place. Full
path plus what you want to know about it is enough.

If you want these prompts ready to paste, they are in `SEARCHING.md` in the same folder.