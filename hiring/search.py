"""Search for hiring posts and job openings.

Three modes, all sharing the same classifier:

    python search.py --query '"hiring" OR "open role"'   bookmarks, the default mode
    python search.py --query '"hiring" OR "open role"' --json out.json
    python search.py --live --search hiring-live         X itself, not your bookmarks
    python search.py --watch aakashgupta                 read one account's posts
    python search.py --selfcheck                          check every pattern and query

There is no built-in phrase set. Every query is named in searches.json and is
read from there, so the panel and ctl.py run the same thing this does. Use
--query to pass one by hand, --search to name a saved one.

Bookmarks come from the Field Theory SQLite index. Live mode shells out to the
twitter CLI. Watch mode reads one account, which is the only live path that
works right now because `twitter search` returns HTTP 404 on this machine.

Every pattern carries a probe string, so a broken pattern stops the run instead
of silently returning nothing. See pat.py for why that guard exists.
"""

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pat import pat, groups, fts_query, selfcheck as pat_selfcheck

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.expandvars(r'%USERPROFILE%\.fieldtheory\bookmarks\bookmarks.db')
OUTDIR = os.path.join(os.path.dirname(HERE), 'out')
DEFAULT_MD = os.path.join(OUTDIR, 'hiring_bookmarks.md')
CONFIG = os.path.join(HERE, 'searches.json')

# Every pattern lives in patterns.json, one probe and regex per pair, and every
# one is proved against its probe at import. Nothing here is hardcoded except the
# ROLE template, which is built from the TITLE_WORDS list in that file, and the
# order the groups are tested in, which is a decision rather than a setting.
PATTERNS = os.path.join(HERE, 'patterns.json')
G = groups(PATTERNS)

OFFER = G['OFFER']              # someone is offering a role
APPLY_CTA = G['APPLY_CTA']      # how to apply, feeds the apply column
LAYOFF = G['LAYOFF']            # cuts and reorgs
LISTY = G['LISTY']              # roundups, boards, hiring partners
ADVICE = G['ADVICE']            # how to search, interview, negotiate
CRAFT = G['CRAFT']              # hiring market and process talk
MISC = G['MISC']                # recruiting that is not hiring, checked first
MONEY = G['MONEY']              # a salary figure
PERIOD = G['PERIOD']            # a pay rate per unit of time
HIRING_VERB = G['HIRING_VERB']  # the word that opens the door
LOCATION = G['LOCATION']        # where the role is
LINK = G['LINK']                # an application link
PAST = G['PAST']                # a word before the hiring word, so it is history
TITLE_WORDS = G['TITLE_WORDS']  # job titles, plain words not regexes

ROLE = pat(
    "hiring a Founding Product Designer",
    rf"\b(?:(?:senior|sr\.?|staff|principal|junior|jr\.?|lead|associate|contract|freelance|"
    rf"entry[- ]level|graduate|new grad|head of|chief)\s+){{0,2}}"
    rf"(?:{'|'.join(TITLE_WORDS)})"
    rf"(?:\s+(?:engineer|engineering|developer|designer|scientist|manager|recruiter|architect|"
    rf"specialist|analyst|writer|officer|teacher|accountant))?\b"
)


def classify(text):
    """Bucket one tweet. Order matters: specific before general."""
    if MISC.search(text):
        return 'misc'
    if LAYOFF.search(text) and not OFFER.search(text):
        return 'layoff'
    if LISTY.search(text) and not OFFER.search(text):
        return 'list'
    if OFFER.search(text):
        return 'opening'
    m = HIRING_VERB.search(text)
    if m and m.start() < 150 and not PAST.search(text[max(0, m.start() - 14):m.start()]) \
            and (ROLE.search(text) or MONEY.search(text) or PERIOD.search(text)):
        return 'opening'
    if ADVICE.search(text):
        return 'advice'
    if CRAFT.search(text):
        return 'craft'
    return 'other'


def fetch(db_path, phrase, since=None):
    """One pass over the index.

    Join on rowid, never on b.id. bookmarks.id is declared TEXT PRIMARY KEY, so
    `b.id = f.rowid` compares text to integer, matches nothing, and turns this
    query into a full-table scan. Measured on 2026-10-09: 382 seconds for zero
    rows, against 0.19 seconds for the rowid join that returns 3819 rows. That
    wrong join is what made the first attempt at this search time out.

    The database has no follower_count or is_verified column, so those are not
    in the output. The JSONL has them but only inside nested author objects with
    no index, so getting them means a 155 MB scan. Say so before paying for it.
    """
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = con.execute("""
    SELECT b.id, b.url, b.text, b.author_handle, b.author_name, b.posted_at,
           b.like_count, b.repost_count, b.reply_count
    FROM bookmarks_fts f JOIN bookmarks b ON b.rowid = f.rowid
    WHERE bookmarks_fts MATCH ?
    """, (phrase,)).fetchall()
    con.close()
    out = [dict(r) for r in rows]
    return [r for r in out if not since or (when(r['posted_at']) or EPOCH) >= since]


def run_twitter(args_list):
    """Shell out to the twitter CLI with credentials from .env."""
    here = os.path.dirname(HERE)
    if here not in sys.path:
        sys.path.insert(0, here)
    from sync_bookmarks import load_env
    load_env()
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    p = subprocess.run(['twitter'] + args_list, capture_output=True, text=True,
                       encoding='utf-8', env=env)
    return json.loads(p.stdout or '{}')


def fetch_live(query, limit=200, since=None, min_likes=0, exclude=('retweets',)):
    """Search X. Broken before 2026-10-09, see fix-twitter-cli.js."""
    args = ['search', query, '-n', str(limit), '--json']
    for e in exclude:
        args += ['--exclude', e]
    if min_likes:
        args += ['--min-likes', str(min_likes)]
    if since:
        args += ['--since', since.strftime('%Y-%m-%d')]
    payload = run_twitter(args)
    if not payload.get('ok'):
        return [], payload.get('error', {}).get('message', 'unknown error')
    return normalise_live(payload.get('data') or []), None


def chunk_phrases(pattern, cap=440):
    """Split an OR chain into batches X will accept.

    X rejects a raw query over 512 characters with PipelineFailure. The full
    phrase set is 81 phrases and 1329 characters, so it has to go out in pieces.
    """
    parts = [p.strip() for p in pattern.split(' OR ') if p.strip()]
    out, cur = [], []
    for p in parts:
        if cur and len(' OR '.join(cur + [p])) > cap:
            out.append(' OR '.join(cur))
            cur = [p]
        else:
            cur.append(p)
    if cur:
        out.append(' OR '.join(cur))
    return out


def fetch_live_chunked(phrase_set, limit=200, since=None, min_likes=0,
                       exclude=('retweets',), pause=3.0, cap=440):
    """Search X for every phrase, in batches, and merge the results.

    This is the live equivalent of what the database does with one MATCH. Using
    only a few hand-picked phrases throws away most of the recall for no reason.
    """
    import time
    batches = chunk_phrases(phrase_set, cap)
    rows, seen, notes = [], set(), []
    for i, b in enumerate(batches, 1):
        if i > 1:
            time.sleep(pause)
        got, err = fetch_live(b, limit, since, min_likes, exclude)
        if err:
            notes.append(f'batch {i} of {len(batches)} FAILED: {err.strip()[:120]}')
            continue
        fresh = 0
        for r in got:
            if r['id'] in seen:
                continue
            seen.add(r['id'])
            rows.append(r)
            fresh += 1
        notes.append(f'batch {i} of {len(batches)}: {len(got)} tweets, {fresh} new')
    return rows, notes


def fetch_watch(handle, limit=200):
    """Read one account's own posts. This live path works today."""
    payload = run_twitter(['user-posts', handle, '-n', str(limit), '--json'])
    if not payload.get('ok'):
        return [], payload.get('error', {}).get('message', 'unknown error')
    return normalise_live(payload.get('data') or []), None


def fetch_handles(handles, limit=200, pause=2.0):
    """Read a list of accounts, one pause apart.

    The pause is not optional. Nineteen accounts back to back returns HTTP 429
    from the eighth onwards, so without it a run silently covers half the list
    and reports it as success.
    """
    import time
    rows, seen, notes = [], set(), []
    for i, h in enumerate(handles):
        if i:
            time.sleep(pause)
        got, err = fetch_watch(h, limit)
        if err:
            notes.append(f'@{h} FAILED: {err.strip()}')
            continue
        for r in got:
            if r['id'] in seen:
                continue
            seen.add(r['id'])
            rows.append(r)
        notes.append(f'@{h}: {len(got)} posts')
    return rows, notes


def fetch_watchlist(path, limit=200, pause=2.0):
    """Read every account in a watchlist file, one handle per line."""
    handles = []
    for line in open(path, encoding='utf-8'):
        line = line.split('#', 1)[0].strip().lstrip('@')
        if line:
            handles.append(line)
    return fetch_handles(handles, limit, pause)


def fetch_list(list_id, limit=200, pause=2.0):
    """Read one X list by numeric id.

    X refuses cookie auth on every list-enumeration endpoint, verified 2026-10-10:
    /i/api/1.1/lists/list.json returns 401 and /i/api/2/lists/created.json
    returns 403. So ids have to come from the list URL, x.com/i/lists/<id>.
    """
    payload = run_twitter(['list', str(list_id), '-n', str(limit), '--json'])
    if not payload.get('ok'):
        return [], payload.get('error', {}).get('message', 'unknown error')
    got = normalise_live(payload.get('data') or [])
    return got, [f'list {list_id}: {len(got)} tweets']


def normalise_live(items):
    """Map twitter-cli tweet objects onto the same shape the database returns.

    Three things this gets wrong if you are careless, all found on 2026-10-09:

    - `isRetweet` must be dropped. A retweet carries the ORIGINAL author, so a
      founder who retweets one job ad brings in that advertiser's whole feed of
      spam. Nineteen watched accounts returned 193 posts that way.
    - counts live in a nested `metrics` dict, not at the top level. Reading the
      top level gives zeros and silently sorts everything as engagement 0.
    - the author handle lives in a nested `author` dict, not `user`.
    """
    rows = []
    for t in items:
        if not isinstance(t, dict) or t.get('isRetweet'):
            continue
        text = t.get('text') or t.get('full_text') or ''
        if not text:
            continue
        author = t.get('author') or t.get('user') or {}
        m = t.get('metrics') or {}
        handle = author.get('screenName') or author.get('handle') or ''
        if not handle:
            continue
        rows.append({
            'id': str(t.get('id') or ''),
            'url': f"https://x.com/{handle}/status/{t.get('id')}",
            'text': text,
            'author_handle': handle,
            'author_name': author.get('name') or '',
            'posted_at': t.get('createdAt') or t.get('createdAtISO') or '',
            'like_count': m.get('likes') or 0,
            'repost_count': m.get('retweets') or 0,
            'reply_count': m.get('replies') or 0,
        })
    return rows


def extract(r):
    t = r['text'] or ''
    roles, seen = [], set()
    for m in ROLE.finditer(t):
        v = re.sub(r'\s+', ' ', m.group(0)).strip().lower()
        if 4 <= len(v) <= 40 and v not in seen:
            seen.add(v)
            roles.append(v)
    return {
        'roles': roles[:5],
        'pay': [m.group(0).strip() for m in MONEY.finditer(t)][:4],
        'loc': sorted({m.group(1).lower() for m in LOCATION.finditer(t)})[:4],
        'link': (LINK.search(t).group(0) if LINK.search(t) else None),
        'eng': (r['like_count'] or 0) + 2 * (r['repost_count'] or 0) + (r['reply_count'] or 0),
        'date': r['posted_at'],
    }


EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def when(s):
    try:
        return datetime.strptime(s, '%a %b %d %H:%M:%S %z %Y')
    except Exception:
        return None


def snip(t, n=280):
    t = re.sub(r'\s+', ' ', t or '').strip()
    return t if len(t) <= n else t[:n - 1].rstrip() + '...'


def live_shape_check():
    """Proves normalise_live maps the twitter-cli payload correctly.

    Uses a real captured payload. Without this, a retweet sneaks in and a
    recruiter's spam feed looks like a founder's openings, which is exactly
    what happened on 2026-10-09.
    """
    got = normalise_live([{
        'id': '1', 'text': "we're hiring two engineers",
        'author': {'screenName': 'acme', 'name': 'Acme'},
        'metrics': {'likes': 30, 'retweets': 4, 'replies': 2},
        'createdAt': 'Fri Oct 09 04:39:47 +0000 2026',
        'isRetweet': False,
    }])
    assert len(got) == 1, 'normalise_live dropped a real post'
    assert got[0]['author_handle'] == 'acme', 'author handle not read from the nested author dict'
    assert got[0]['like_count'] == 30 and got[0]['repost_count'] == 4, \
        'counts not read from the nested metrics dict'
    assert when(got[0]['posted_at']) is not None, 'posted_at not parseable'
    assert got[0]['url'] == 'https://x.com/acme/status/1'

    dropped = normalise_live([{
        'id': '2', 'text': 'hiring spam',
        'author': {'screenName': 'JobSpamCo', 'name': 'Job Spam'},
        'metrics': {}, 'createdAt': 'Fri Oct 09 04:39:47 +0000 2026', 'isRetweet': True,
    }])
    assert dropped == [], 'normalise_live kept a retweet, so retweeted spam leaks in'


def saved_query(name):
    """Read one saved search out of searches.json and return its query."""
    with open(CONFIG, encoding='utf-8') as f:
        cfg = json.load(f)
    for s in cfg.get('searches', []):
        if s['name'] == name:
            q = (s.get('query') or '').strip()
            if not q:
                raise SystemExit(
                    f"search {name!r} has no query. Give it one in the panel's Edit "
                    f"dialog, or in {os.path.basename(CONFIG)}, then run again.")
            return q
    raise SystemExit(f"no search called {name!r} in {os.path.basename(CONFIG)}")


def config_queries_check():
    """Every saved bookmarks query must parse, or the run that needs it fails late.

    Only bookmarks queries are judged. X understands operators FTS5 does not,
    such as from: and min_faves:, so a live query is left for X to accept.
    """
    if not os.path.exists(CONFIG):
        return
    with open(CONFIG, encoding='utf-8') as f:
        cfg = json.load(f)
    for s in cfg.get('searches', []):
        if s.get('source') == 'bookmarks' and (s.get('query') or '').strip():
            fts_query(s['query'], s['name'])


def main():
    # Tweet text is not cp1252. Same fix weekly_scan.py uses.
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[1])
    ap.add_argument('--selfcheck', action='store_true',
                    help='check every pattern against its probe, touch nothing else')
    ap.add_argument('--live', action='store_true',
                    help='search X itself instead of your bookmarks')
    ap.add_argument('--min-likes', type=int, default=0,
                    help='live search only, drop posts below this many likes')
    ap.add_argument('--exclude', default='retweets',
                    help='live search only, comma separated: retweets,replies,links')
    ap.add_argument('--watch', metavar='HANDLE',
                    help='read one account\'s own posts instead of searching')
    ap.add_argument('--watchlist', metavar='FILE',
                    help='read every account in a watchlist file, one handle per line')
    ap.add_argument('--pause', type=float, default=2.0,
                    help='seconds between accounts in watchlist mode, avoids HTTP 429')
    ap.add_argument('--query',
                    help='search syntax: quoted phrases with OR, AND, NOT. Goes to '
                         'bookmarks_fts as a MATCH, or to X as one query.')
    ap.add_argument('--search', metavar='NAME',
                    help='use the query of a saved search in searches.json')
    ap.add_argument('--limit', type=int, default=200, help='max tweets in live or watch mode')
    ap.add_argument('--days', type=int, help='only tweets from the last N days')
    ap.add_argument('--since', help='only tweets on or after YYYY-MM-DD')
    ap.add_argument('--db', default=DB, help='path to bookmarks.db')
    ap.add_argument('--md', nargs='?', const=DEFAULT_MD, help='write the markdown report')
    ap.add_argument('--json', nargs='?', const='-',
                    help='write every match as JSON, full text, no truncation')
    args = ap.parse_args()

    pat_selfcheck()
    live_shape_check()
    config_queries_check()
    if args.selfcheck:
        print('patterns ok')
        return

    if args.query and args.search:
        sys.exit('give --query or --search, not both')
    query = args.query or (saved_query(args.search) if args.search else '')

    since = None
    if args.since:
        since = datetime.strptime(args.since, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    elif args.days:
        since = datetime.now(timezone.utc) - timedelta(days=args.days)

    source = 'bookmarks.db'
    notes = []
    if args.watchlist:
        source = f'live watchlist {args.watchlist}'
        rows, notes = fetch_watchlist(args.watchlist, args.limit, args.pause)
    elif args.watch:
        source = f'live account @{args.watch}'
        rows, err = fetch_watch(args.watch, args.limit)
        if err:
            sys.exit(f'could not read @{args.watch}: {err}')
    elif args.live:
        if not query:
            sys.exit('live search needs a query. Pass --search NAME for a saved one, '
                     'or --query "..." for a one-off.')
        # A hand-written query is never split. chunk_phrases splits on OR, so it
        # would silently change the meaning of "(a OR b) NOT c". A plain OR
        # chain of saved phrases is the one thing that is safe to batch, which is
        # what ctl.py does for a saved live search too.
        exclude = tuple(x for x in args.exclude.split(',') if x)
        if len(query) > 512:
            if re.search(r'[()]|\bAND\b|\bNOT\b', query, re.I):
                sys.exit(f'query is {len(query)} characters and uses brackets, AND or '
                         f'NOT, so it cannot be split without changing its meaning. '
                         f'Shorten it to 512 characters.')
            source = f'live X search: {len(query)} characters, sent in batches'
            rows, notes = fetch_live_chunked(query, args.limit, since, args.min_likes,
                                             exclude, args.pause)
        else:
            source = f'live X search: {query}'
            rows, err = fetch_live(query, args.limit, since, args.min_likes, exclude)
            notes = [f'1 query of {len(query)} characters']
            if err:
                sys.exit(f'live search failed: {err}\n'
                         f'If this says 404, the patch was lost. Run: node fix-twitter-cli.js')
    else:
        if not query:
            sys.exit('bookmarks mode needs a query. Pass --search NAME for a saved '
                     'one, or --query "..." for a one-off.')
        rows = fetch(args.db, fts_query(query, '--query'))
        if since:
            rows = [r for r in rows if (when(r['posted_at']) or EPOCH) >= since]

    buckets = Counter()
    for r in rows:
        r.update(extract(r))
        r['bucket'] = classify(r['text'] or '')
        r['dt'] = when(r['date'])
        buckets[r['bucket']] += 1

    openings = sorted([r for r in rows if r['bucket'] == 'opening'],
                      key=lambda r: r['dt'] or EPOCH, reverse=True)
    recent, older, cut = [], [], datetime.now(timezone.utc) - timedelta(days=150)
    for r in openings:
        (recent if r['dt'] and r['dt'] > cut else older).append(r)

    if args.json:
        payload = {
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'source': source,
            'since': since.isoformat() if since else None,
            'counts': dict(buckets),
            'openings': len(openings),
            'coverage': notes,
            'tweets': [{
                'id': r['id'], 'url': r['url'], 'author': r['author_handle'],
                'author_name': r['author_name'], 'posted_at': r['date'],
                'bucket': r['bucket'], 'roles': r['roles'], 'pay': r['pay'],
                'location': r['loc'], 'apply_link': r['link'],
                'likes': r['like_count'], 'reposts': r['repost_count'],
                'replies': r['reply_count'], 'text': r['text'],
            } for r in sorted(rows, key=lambda r: r['dt'] or EPOCH, reverse=True)],
        }
        if args.json == '-':
            json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
            sys.stdout.write('\n')
        else:
            os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
            with open(args.json, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            print('wrote', args.json)

    if args.md:
        L = []
        A = L.append
        A('# Hiring and job openings')
        A('')
        A(f'Source: `{source}`. Matched **{len(rows)}** tweets'
          + (f', since {since.date()}.' if since else '.'))
        A('')
        A('| Group | Tweets |')
        A('|---|---|')
        A(f'| Someone posting an opening | {len(openings)} |')
        A(f'| How to apply, interview, negotiate | {buckets["advice"]} |')
        A(f'| Layoffs, reorgs, headcount cuts | {buckets["layoff"]} |')
        A(f'| Roundups and job boards | {buckets["list"]} |')
        A(f'| Hiring market and process craft | {buckets["craft"]} |')
        A(f'| Other employment talk | {buckets["other"] + buckets["misc"]} |')
        A('')
        if notes:
            A('Coverage:' if args.live else 'Accounts read:')
            A('')
            for n in notes:
                A(f'- {n}')
            A('')

        def block(rs, title, note=None):
            A(f'## {title}')
            A('')
            if note:
                A(note); A('')
            for r in rs:
                bits = []
                if r['roles']:
                    bits.append('roles: ' + ', '.join(r['roles'][:4]))
                if r['pay']:
                    bits.append('pay: ' + ' '.join(r['pay'][:3]))
                if r['loc']:
                    bits.append('loc: ' + ', '.join(r['loc'][:3]))
                if r['link']:
                    bits.append('link: ' + r['link'][:60])
                head = f'- **@{r["author_handle"]}**'
                if r['dt']:
                    head += f' {(datetime.now(timezone.utc) - r["dt"]).days}d'
                A(head + (f' — {" | ".join(bits)}' if bits else ''))
                A(f'  {snip(r["text"])}')
                A(f'  <{r["url"]}>')
            A('')

        block(recent, 'Openings posted in the last 5 months', f'{len(recent)} tweets, newest first.')
        block(older, 'Older openings', f'{len(older)} tweets, newest first.')
        for key, title in (('list', 'Roundups, job boards, hiring signals'),
                           ('advice', 'How to apply, interview, and negotiate'),
                           ('craft', 'Hiring market and process craft'),
                           ('layoff', 'Layoffs, reorgs, headcount cuts')):
            sel = sorted([r for r in rows if r['bucket'] == key], key=lambda r: -r['eng'])
            block(sel, title, 'Highest engagement first.' if key in ('advice', 'craft') else None)
        block(sorted([r for r in rows if r['bucket'] in ('other', 'misc')], key=lambda r: -r['eng']),
              'Other employment talk', 'Highest engagement first.')

        A('---')
        A('')
        A('## Accounts posting the most openings')
        A('')
        A(', '.join(f'@{k} ({v})' for k, v in Counter(r['author_handle'] for r in openings).most_common(30)))
        A('')
        A('## Roles most often requested')
        A('')
        A(', '.join(f'{k} ({v})' for k, v in Counter(x for r in openings for x in r['roles']).most_common(40)))
        A('')
        A('## Openings that state pay')
        A('')
        for r in [r for r in openings if r['pay']]:
            A(f'- @{r["author_handle"]}: {" ".join(r["pay"][:3])} — {snip(r["text"], 140)}')
            A(f'  <{r["url"]}>')
            A(f'  full text in the JSON export')

        if args.md == '-':
            # Same contract as --json -: a dash means print it, not a file
            # literally called "-", which is what this used to write.
            sys.stdout.write('\n'.join(L))
        else:
            os.makedirs(os.path.dirname(os.path.abspath(args.md)), exist_ok=True)
            with open(args.md, 'w', encoding='utf-8') as f:
                f.write('\n'.join(L))
            print('wrote', args.md)

    print(f'matched {len(rows)} from {source}', dict(buckets))


if __name__ == '__main__':
    main()
