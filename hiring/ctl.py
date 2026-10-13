"""Control plane for your own searches.

One config file, one runner, one local web page. No server, no database, no
dependencies beyond the Python standard library.

    python ctl.py list                      show every search
    python ctl.py add --name x --source live --query "hiring" --every-days 3
    python ctl.py edit x --query "hiring OR \"open role\""   change one
    python ctl.py rm x                                       delete one
    python ctl.py add --name y --source watchlist --handle aakashgupta
    python ctl.py add --name z --source list --list-id 1908587200419422252
    python ctl.py run --all                 run everything now
    python ctl.py run --name hiring-live    run one now
    python ctl.py run --due                 run only what is due today
    python ctl.py serve                     open http://127.0.0.1:8765

Schedule is deliberately dumb. Each search has every_days and a time. One
Windows scheduled task runs `run --due` once a day and this decides what is
due, rather than registering a task per search, which Windows makes painful.

The config is JSON rather than YAML or TOML because the standard library can
read and write JSON. tomllib can only read, and there is no standard YAML.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import search as S

CONFIG = os.path.join(HERE, 'searches.json')
LISTS = os.path.join(HERE, 'lists.json')
STATE = os.path.join(HERE, 'searches-state.json')
OUTDIR = os.path.join(os.path.dirname(HERE), 'out', 'searches')
SOURCES = ('bookmarks', 'live', 'watchlist', 'list', 'concept')


# ---------- config ----------
def load():
    if not os.path.exists(CONFIG):
        return {'searches': []}
    with open(CONFIG, encoding='utf-8') as f:
        return json.load(f)


def save(cfg):
    with open(CONFIG, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        f.write('\n')


def load_lists():
    if not os.path.exists(LISTS):
        return {'lists': []}
    with open(LISTS, encoding='utf-8') as f:
        return json.load(f)


def save_lists(cfg):
    with open(LISTS, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        f.write('\n')


def find_list(name):
    for l in load_lists()['lists']:
        if l['name'] == name:
            return l
    return None


def load_state():
    if not os.path.exists(STATE):
        return {}
    with open(STATE, encoding='utf-8') as f:
        return json.load(f)


def save_state(st):
    with open(STATE, 'w', encoding='utf-8') as f:
        json.dump(st, f, indent=2)


def find(cfg, name):
    for s in cfg['searches']:
        if s['name'] == name:
            return s
    return None


def check(s):
    """Catch a broken config before it costs a network call or a silent zero."""
    if s.get('source') not in SOURCES:
        raise ValueError(f"{s['name']}: source must be one of {SOURCES}, got {s.get('source')!r}")
    # Nothing is hardcoded, so a search with no query searches for nothing. Both
    # query sources need one, and a bookmarks query must also be something FTS5
    # can parse. Live queries are left to X, which understands operators FTS5
    # does not, such as from: and min_faves:.
    if s['source'] in ('bookmarks', 'live') and not (s.get('query') or '').strip():
        raise ValueError(f"{s['name']}: source {s['source']} needs a query. Quoted phrases "
                         f"with OR. Set it in the panel, or in searches.json.")
    if s['source'] == 'bookmarks' and (s.get('query') or '').strip():
        S.fts_query(s['query'], s['name'])
    if s['source'] == 'list':
        if s.get('list') and not find_list(s['list']):
            raise ValueError(f"{s['name']}: no list named {s['list']!r} in lists.json")
        if not s.get('list') and not s.get('list_id'):
            raise ValueError(f"{s['name']}: source list needs a list name or a list_id")
    if s['source'] == 'watchlist' and not (s.get('list') or s.get('handles') or s.get('handles_file')):
        raise ValueError(f"{s['name']}: source watchlist needs a list, handles, or handles_file")
    if s['source'] == 'watchlist' and s.get('list') and not find_list(s['list']):
        raise ValueError(f"{s['name']}: no list named {s['list']!r} in lists.json")
    # A concept is a sentence, not search syntax, so it must NOT go through
    # fts_query. That check exists to catch a saved query FTS5 cannot parse, and
    # a concept never reaches FTS5 as a query: sem.py expands it into one.
    if s['source'] == 'concept':
        c = (s.get('concept') or s.get('query') or '').strip()
        if not c:
            raise ValueError(f"{s['name']}: source concept needs a concept. A sentence in "
                             f"plain English, such as 'tweets hinting at a Series A raise'. "
                             f"Not keywords.")
        if len(c) > 200:
            raise ValueError(f"{s['name']}: concept is {len(c)} characters, keep it under 200")
        if c.lower() in ('hiring', 'layoff', 'advice'):
            raise ValueError(f"{s['name']}: a concept of one word is what the query sources "
                             f"are for. Say what the tweets are about.")
    if int(s.get('every_days', 1)) < 1:
        raise ValueError(f"{s['name']}: every_days must be 1 or more")
    if not re.fullmatch(r'\d{2}:\d{2}', s.get('time', '09:00')):
        raise ValueError(f"{s['name']}: time must look like 09:30")


# ---------- running ----------
def run_concept(s, limit, since):
    """Run sem.py for a concept and reshape its candidates into the same rows
    every other source produces, so classify, extract and the markdown writer all
    keep working unchanged.

    The concept's own verdict wins over the regex buckets when it says hit,
    because a sentence and a pattern disagree about what counts and the model is
    the better judge of that. Everything it is unsure about still falls through
    to the regex tiers, so nothing is lost by trusting it.
    """
    import json as _json
    import sem
    concept = (s.get('concept') or s.get('query') or '').strip()
    source = 'x' if s.get('concept_source', 'bookmarks') == 'x' else 'bookmarks'

    # A scheduled run must not depend on a model being reachable. If no seed is
    # configured, reuse a phrase set from patterns.json so the daily job still
    # returns something when the model key is empty or out of credit.
    seed = [q.strip() for q in (s.get('seed') or '').split(',') if q.strip()]
    if not seed and s.get('seed_group'):
        pj = os.path.join(HERE, 'patterns.json')
        try:
            with open(pj, encoding='utf-8') as f:
                groups = _json.load(f)['groups']
            for g in s['seed_group'].split(','):
                g = g.strip().upper()
                if g not in groups:
                    raise ValueError(f'patterns.json has no group {g!r}. It has: '
                                     f'{", ".join(sorted(groups))}')
                e = groups[g]
                seed += e['words'] if 'words' in e else [p[0] for p in e['patterns']]
        except FileNotFoundError:
            raise ValueError(f'{s["name"]}: patterns.json is missing, so seed_group '
                             f'{s["seed_group"]!r} cannot be read')

    log = []
    cands = sem.run(
        sem.connect(), concept, source, limit, since,
        int(s.get('min_likes', 0)), days_back=int(s.get('days_back', 7)),
        rubric=int(s.get('rubric', 1)), n_queries=int(s.get('queries', 60)),
        pool_size=int(s.get('pool', 300)), frontier_top=int(s.get('frontier', 0)),
        seed=seed or None, fresh=True, quiet=True, log=log)
    rows = []
    for c in cands:
        rows.append({
            'id': c['id'], 'url': c.get('url', ''), 'text': c.get('text', ''),
            'author_handle': c.get('handle', ''), 'author_name': '',
            'posted_at': c.get('posted_at', ''),
            'like_count': c.get('likes', 0) or 0, 'repost_count': c.get('reposts', 0) or 0,
            'reply_count': c.get('replies', 0) or 0,
            # kept so the markdown can show why the classifier decided
            'concept_verdict': c.get('verdict') or 'unjudged',
            'concept_score': c.get('prob'),
            'concept_why': c.get('reason') or '',
            'found_by_queries': c.get('found_by', 0),
        })
    # sem.run's own lines go in as coverage, so an empty report says why instead
    # of just showing a zero.
    notes = [f'concept {concept!r} over {source}']
    if seed:
        notes.append(f'{len(seed)} fixed queries from '
                     f'{s.get("seed_group") or "seed"}, so this run costs no model call')
    notes += log
    if not cands:
        notes.append('NOTHING FOUND. If there is no model key, set seed_group so the run '
                     'has queries to work from.')
    return rows, notes


def run_one(s):
    check(s)
    limit = int(s.get('limit', 50))
    since = datetime.now(timezone.utc) - timedelta(days=int(s.get('days_back', 7)))
    src = s['source']

    if src == 'bookmarks':
        rows = S.fetch(S.DB, S.fts_query(s['query'], s['name']), since)
        notes = ['local database, no network']
    elif src == 'concept':
        rows, notes = run_concept(s, limit, since)
    elif src == 'live':
        rows, notes = S.fetch_live_chunked(s['query'], limit, since,
                                           int(s.get('min_likes', 0)), ('retweets',),
                                           float(s.get('pause', 3.0)))
    elif src == 'watchlist':
        handles = list(s.get('handles') or [])
        if s.get('list'):
            entry = find_list(s['list'])
            if not entry:
                raise ValueError(f"no list named {s['list']!r}")
            if entry['kind'] != 'handles':
                raise ValueError(f"{entry['name']} is an X list, not a handles list")
            handles += entry.get('handles', [])
        hf = s.get('handles_file')
        if hf:
            path = hf if os.path.isabs(hf) else os.path.join(HERE, hf)
            handles += [l.split('#', 1)[0].strip().lstrip('@')
                        for l in open(path, encoding='utf-8')
                        if l.split('#', 1)[0].strip()]
        rows, notes = S.fetch_handles(handles, limit, float(s.get('pause', 2.0)))
    else:
        list_id = s.get('list_id')
        if s.get('list'):
            entry = find_list(s['list'])
            if not entry:
                raise ValueError(f"no list named {s['list']!r}")
            if entry['kind'] != 'xlist':
                raise ValueError(f"{entry['name']} is a handles list, not an X list")
            list_id = entry.get('list_id')
        rows, notes = S.fetch_list(list_id, limit, float(s.get('pause', 0.0)))

    for r in rows:
        r.update(S.extract(r))
        # A concept hit is an opening by definition of the concept, so the regex
        # tiers do not get to overrule it. Anything the model was unsure about
        # falls through to them unchanged.
        r['bucket'] = ('opening' if r.get('concept_verdict') == 'hit'
                       else S.classify(r.get('text') or ''))
        r['dt'] = S.when(r.get('posted_at') or '')

    os.makedirs(OUTDIR, exist_ok=True)
    stamp = datetime.now().strftime('%Y-%m-%d_%H%M')
    base = os.path.join(OUTDIR, f"{s['name']}-{stamp}")
    payload = {
        'name': s['name'], 'source': src, 'ran_at': datetime.now(timezone.utc).isoformat(),
        'since': since.isoformat(), 'coverage': notes,
        'counts': {}, 'openings': 0,
        'tweets': sorted(rows, key=lambda r: r['dt'] or S.EPOCH, reverse=True),
    }
    # 'dt' is a datetime, used for sorting and for the day count in the
    # markdown. JSON cannot hold it, so keep the original posted_at and drop it.
    payload['tweets'] = [{k: v for k, v in r.items() if k != 'dt'} for r in payload['tweets']]
    from collections import Counter
    payload['counts'] = dict(Counter(r['bucket'] for r in rows))
    payload['openings'] = payload['counts'].get('opening', 0)
    with open(base + '.json', 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    with open(base + '.md', 'w', encoding='utf-8') as f:
        f.write(markdown(s, payload, rows))

    st = load_state()
    st[s['name']] = {'last_run': stamp, 'rows': len(rows), 'openings': payload['openings']}
    save_state(st)
    return payload


def markdown(s, p, rows):
    L = [f"# {s['name']}", '',
         f"Source: {p['source']}. Ran {p['ran_at'][:19].replace('T', ' ')} UTC, "
         f"since {p['since'][:10]}. **{len(p['tweets'])}** tweets, "
         f"**{p['openings']}** openings.", '']
    if p['coverage']:
        L += ['Coverage:', ''] + [f'- {n}' for n in p['coverage']] + ['']
    L += ['| Group | Tweets |', '|---|---|']
    for k in ('opening', 'layoff', 'list', 'advice', 'craft', 'other', 'misc'):
        if p['counts'].get(k):
            L.append(f"| {k} | {p['counts'][k]} |")
    L.append('')
    for b in ('opening', 'layoff', 'advice', 'craft', 'list'):
        sel = [r for r in rows if r['bucket'] == b]
        if not sel:
            continue
        L += [f"## {b}", '']
        for r in sel:
            bits = []
            if r['roles']:
                bits.append('roles: ' + ', '.join(r['roles'][:3]))
            if r['pay']:
                bits.append('pay: ' + ' '.join(r['pay'][:2]))
            # A concept run records why the classifier decided, so the report is
            # auditable rather than a list you have to take on faith.
            if r.get('concept_verdict') and r.get('concept_verdict') != 'unjudged':
                sc = r.get('concept_score')
                bits.append(f"concept {r['concept_verdict']}"
                            + (f' {sc:.2f}' if isinstance(sc, (int, float)) else ''))
            head = f"- **@{r['author_handle']}**"
            if r['dt']:
                head += f" {(datetime.now(timezone.utc) - r['dt']).days}d"
            L.append(head + (f" — {' | '.join(bits)}" if bits else ''))
            L.append(f"  {S.snip(r['text'])}")
            if r.get('concept_why'):
                L.append(f"  why: {r['concept_why']}")
            L.append(f"  <{r['url']}>")
        L.append('')
    return '\n'.join(L)


def due(s, now=None):
    """Is this search due? Uses last run date, so a missed day does not skip it."""
    if not s.get('enabled', True):
        return False
    st = load_state().get(s['name'])
    every = int(s.get('every_days', 1))
    if not st:
        return True
    try:
        last = datetime.strptime(st['last_run'].rsplit('_', 1)[0], '%Y-%m-%d %H%M').date()
    except Exception:
        return True
    return (now or datetime.now()).date() - last >= timedelta(days=every)


# ---------- CLI ----------
def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[1])
    sub = ap.add_subparsers(dest='cmd', required=True)

    sub.add_parser('list', help='show every search')

    p = sub.add_parser('add', help='add a search')
    p.add_argument('--name', required=True)
    p.add_argument('--source', required=True, choices=SOURCES)
    p.add_argument('--query', default='')
    p.add_argument('--concept', default='',
                   help='source concept only. A sentence in plain English, not keywords.')
    p.add_argument('--seed', default='',
                   help='source concept only. Comma separated queries to use instead of '
                        'generating them, so a scheduled run costs no model call.')
    p.add_argument('--seed-group', default='',
                   help='source concept only. Comma separated patterns.json groups to use '
                        'as the fixed query set, for example OFFER,APPLY_CTA.')
    p.add_argument('--concept-source', default='bookmarks', choices=('bookmarks', 'x'))
    p.add_argument('--handle', action='append', default=[], help='repeatable')
    p.add_argument('--list', help='a named list from lists.json')
    p.add_argument('--list-id')
    p.add_argument('--every-days', type=int, default=1)
    p.add_argument('--time', default='09:00')
    p.add_argument('--days-back', type=int, default=7)
    p.add_argument('--limit', type=int, default=50)
    p.add_argument('--min-likes', type=int, default=0)
    p.add_argument('--disabled', action='store_true')

    ep = sub.add_parser('edit', help='change a saved search')
    ep.add_argument('name')
    ep.add_argument('--query')
    ep.add_argument('--concept')
    ep.add_argument('--seed')
    ep.add_argument('--seed-group')
    ep.add_argument('--notes')
    ep.add_argument('--every-days', type=int)
    ep.add_argument('--time')
    ep.add_argument('--days-back', type=int)
    ep.add_argument('--limit', type=int)
    ep.add_argument('--min-likes', type=int)
    ep.add_argument('--enable', action='store_true')
    ep.add_argument('--disable', action='store_true')

    rp = sub.add_parser('rm', help='delete a saved search')
    rp.add_argument('name')

    lp = sub.add_parser('lists', help='show every list')
    lap = sub.add_parser('mklist', help='create a list')
    lap.add_argument('--name', required=True)
    lap.add_argument('--kind', default='handles', choices=('handles', 'xlist'))
    lap.add_argument('--handle', action='append', default=[])
    lap.add_argument('--list-id')
    lap.add_argument('--note', default='')

    lcp = sub.add_parser('rmlist', help='delete a list')
    lcp.add_argument('name')

    sub.add_parser('serve', help='local browser control panel').add_argument(
        '--port', type=int, default=8765,
        help='8765 unless something else already holds it')
    sub.add_parser('check', help='validate the config without running anything')

    # Every subparser must be registered before parse_args is called, or the
    # ones registered after it are rejected as invalid choices.
    r = sub.add_parser('run', help='run searches')
    r.add_argument('--name', action='append', default=[])
    r.add_argument('--all', action='store_true')
    r.add_argument('--due', action='store_true')

    args = ap.parse_args()

    cfg = load()

    if args.cmd == 'list':
        st = load_state()
        print(f"{'name':28} {'source':10} {'every':>5} {'time':>5} {'enabled':>7}  last run")
        for s in cfg['searches']:
            last = st.get(s['name'], {}).get('last_run', 'never')
            print(f"{s['name']:28} {s['source']:10} {s.get('every_days', 1):>5} "
                  f"{s.get('time', '09:00'):>5} {str(s.get('enabled', True)):>7}  {last}")
        return

    if args.cmd == 'check':
        bad = 0
        for s in cfg['searches']:
            try:
                check(s)
                print(f"ok    {s['name']}")
            except ValueError as e:
                bad += 1
                print(f"BAD   {e}")
        sys.exit(1 if bad else 0)

    if args.cmd == 'add':
        if find(cfg, args.name):
            sys.exit(f"a search called {args.name!r} already exists")
        s = {
            'name': args.name, 'source': args.source, 'enabled': not args.disabled,
            'every_days': args.every_days, 'time': args.time,
            'days_back': args.days_back, 'limit': args.limit, 'min_likes': args.min_likes,
            'notes': 'added by ctl.py',
        }
        if args.query:
            s['query'] = args.query
        if args.concept:
            s['concept'] = args.concept
        if args.seed:
            s['seed'] = args.seed
        if args.seed_group:
            s['seed_group'] = args.seed_group
        if args.source == 'concept':
            s['concept_source'] = args.concept_source
        if args.handle:
            s['handles'] = args.handle
        if args.list:
            s['list'] = args.list
        if args.list_id:
            s['list_id'] = args.list_id
        try:
            check(s)
        except ValueError as e:
            sys.exit(str(e))
        cfg['searches'].append(s)
        save(cfg)
        print(f'added {s["name"]}')
        return

    if args.cmd == 'edit':
        s = find(cfg, args.name)
        if not s:
            sys.exit(f"no search called {args.name!r}")
        for key in ('query', 'notes', 'time', 'concept', 'seed', 'seed_group'):
            v = getattr(args, key)
            if v is not None:
                s[key] = v
        for key in ('every_days', 'days_back', 'limit', 'min_likes'):
            v = getattr(args, key)
            if v is not None:
                s[key] = v
        if args.enable and args.disable:
            sys.exit('give --enable or --disable, not both')
        if args.enable:
            s['enabled'] = True
        if args.disable:
            s['enabled'] = False
        try:
            check(s)
        except ValueError as e:
            sys.exit(str(e))
        save(cfg)
        print(f'edited {s["name"]}')
        return

    if args.cmd == 'rm':
        before = len(cfg['searches'])
        cfg['searches'] = [s for s in cfg['searches'] if s['name'] != args.name]
        if len(cfg['searches']) == before:
            sys.exit(f"no search called {args.name!r}")
        save(cfg)
        print(f'deleted {args.name}')
        return

    if args.cmd == 'lists':
        rows = load_lists()['lists']
        print(f"{'name':30} {'kind':9} {'size':>6}  detail")
        for l in rows:
            n = len(l.get('handles', [])) if l['kind'] == 'handles' else 0
            detail = ', '.join(l.get('handles', [])[:4]) if l['kind'] == 'handles' \
                else 'list ' + str(l.get('list_id'))
            if n > 4:
                detail += f' +{n - 4} more'
            print(f"{l['name']:30} {l['kind']:9} {n or '-':>6}  {detail}")
        return

    if args.cmd == 'mklist':
        lc = load_lists()
        if find_list(args.name):
            sys.exit(f'a list called {args.name!r} already exists')
        entry = {'name': args.name, 'kind': args.kind, 'note': args.note}
        if args.kind == 'handles':
            entry['handles'] = [h.lstrip('@') for h in args.handle]
            if not entry['handles']:
                sys.exit('give at least one --handle, or create it in the browser')
        else:
            entry['list_id'] = args.list_id
            if not entry['list_id']:
                sys.exit('give --list-id, taken from the list URL')
        lc['lists'].append(entry)
        save_lists(lc)
        print(f'created list {entry["name"]}')
        return

    if args.cmd == 'rmlist':
        lc = load_lists()
        before = len(lc['lists'])
        lc['lists'] = [l for l in lc['lists'] if l['name'] != args.name]
        if len(lc['lists']) == before:
            sys.exit(f'no list called {args.name!r}')
        save_lists(lc)
        print(f'deleted list {args.name}')
        return

    if args.cmd == 'run':
        if args.all or not args.name:
            todo = [s for s in cfg['searches'] if s.get('enabled', True)]
        elif args.due:
            todo = [s for s in cfg['searches'] if due(s)]
        else:
            todo = [s for s in cfg['searches'] if s['name'] in args.name]
            missing = set(args.name) - {s['name'] for s in todo}
            if missing:
                sys.exit(f'no such search: {", ".join(sorted(missing))}')
        for s in todo:
            print(f"running {s['name']} ({s['source']})")
            try:
                p = run_one(s)
                print(f"  {len(p['tweets'])} tweets, {p['openings']} openings")
                for n in p['coverage']:
                    print(f"    {n}")
            except Exception as e:
                print(f"  FAILED: {type(e).__name__}: {e}")
        return

    if args.cmd == 'serve':
        import serve
        serve.run(CONFIG, load, save, load_state, run_one, load_lists, save_lists,
                  args.port, check=check)


if __name__ == '__main__':
    main()