"""Local control panel for the whole twitter scraper tool. Standard library only.

Bound to 127.0.0.1 on purpose. Running anything here uses your .env credentials
and writes to your real database, so it must not be reachable from the network.
Nothing leaves this machine.

Safety. There is no arbitrary command runner. /api/run takes a key that must
appear in RUNNABLE below, and that table is the complete list of what a browser
request can start. Everything else in the UI is text to copy. Credentials are
write-only: /api/env reports whether each key is set, never its value, and
PUT /api/env writes the file without ever returning it.
"""

import json
import os
import re
import shutil
import subprocess
import threading
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PAGE = os.path.join(HERE, 'web', 'index.html')

# The complete list of what the page is allowed to start. Nothing else runs.
RUNNABLE = {
    'fieldtheory-status':  ['fieldtheory', 'status'],
    'fieldtheory-index':   ['fieldtheory', 'index'],
    'fieldtheory-stats':   ['fieldtheory', 'stats'],
    'fieldtheory-folders': ['fieldtheory', 'folders'],
    'sync-bookmarks':      ['python', os.path.join(ROOT, 'sync_bookmarks.py')],
    'crawl-threads':       ['python', os.path.join(ROOT, 'crawl_tweets.py'),
                            'threads', '--limit', '200', '--top', '20'],
    'tests':               ['python', '-c', 'import subprocess,sys;'
                            'r=[subprocess.run([sys.executable,f],capture_output=True).returncode'
                            ' for f in ["test_sync.py","test_crawl.py","test_weekly.py"]];'
                            'print("exit codes:",r);sys.exit(max(r))'],
    'fix-fieldtheory':     ['node', os.path.join(HERE, 'fix-fieldtheory.js')],
    'fix-twitter-cli':     ['node', os.path.join(HERE, 'fix-twitter-cli.js')],
}

# Keys whose presence matters in .env. Values are never sent to the browser.
ENV_KEYS = ('TWITTER_AUTH_TOKEN', 'TWITTER_CT0')

# Detect each patch by its real signature, not by a marker comment. The
# fieldtheory fix has no comment in it, so a marker check reported a working
# patch as lost and would have told you to re-run a fix you already had.
PATCH_FILES = {
    'fieldtheory': (os.path.expandvars(r'%LOCALAPPDATA%\hermes\node\node_modules'
                                      r'\fieldtheory\dist\bookmarks-db.js'),
                    r'/^(AND|OR|NOT|NEAR)$/i.test(term)'),
    'twitter-cli': (os.path.expandvars(r'%APPDATA%\uv\tools\twitter-cli\Lib\site-packages'
                                       r'\twitter_cli\client.py'),
                    'PATCHED: logged-out HTML'),
}


def env_path():
    """Where .env lives. FT_ENV_FILE overrides it so tests never touch the real one.

    On 2026-10-10 a credential test wrote to the real .env and destroyed the
    auth_token, because the path was hardcoded and the backup never happened.
    Point FT_ENV_FILE at a temp file and the same test is harmless.
    """
    return os.environ.get('FT_ENV_FILE') or os.path.join(ROOT, '.env')


def read_env(path):
    vals = {}
    if not os.path.exists(path):
        return vals
    for line in open(path, encoding='utf-8'):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            vals[k.strip()] = v.strip()
    return vals


def write_env(path, updates):
    """Merge updates into .env, keeping every comment and unknown line intact."""
    lines = open(path, encoding='utf-8').read().splitlines() if os.path.exists(path) else []
    seen = set()
    for i, line in enumerate(lines):
        s = line.strip()
        if s and not s.startswith('#') and '=' in s:
            k = s.split('=', 1)[0].strip()
            if k in updates:
                lines[i] = f"{k}={updates[k]}"
                seen.add(k)
    for k, v in updates.items():
        if k not in seen:
            lines.append(f'{k}={v}')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


def parse_commands():
    """Read COMMANDS.md so the page never drifts from the file."""
    path = os.path.join(ROOT, 'COMMANDS.md')
    if not os.path.exists(path):
        return []
    out, section = [], None
    for raw in open(path, encoding='utf-8'):
        line = raw.rstrip('\n')
        if line.startswith('## '):
            section = line[3:].strip()
            continue
        m = re.match(r'^\|\s*`([^`]+)`\s*\|\s*(.+?)\s*\|\s*$', line)
        if m:
            cmd, why = m.group(1), re.sub(r'\*\*|`', '', m.group(2))
            out.append({'section': section, 'command': cmd, 'why': why,
                        'runnable': cmd.split()[0] in ('python', 'fieldtheory', 'node', 'pwsh')})
    return out


def patch_status():
    out = {}
    for name, (path, marker) in PATCH_FILES.items():
        if not os.path.exists(path):
            out[name] = {'installed': False, 'patched': False, 'path': path}
            continue
        try:
            out[name] = {'installed': True, 'patched': marker in open(path, encoding='utf-8').read(),
                         'path': path}
        except Exception as e:
            out[name] = {'installed': True, 'patched': None, 'path': path, 'error': str(e)}
    return out


def status():
    info = {'time': datetime.now().isoformat(timespec='seconds')}
    db = os.path.expandvars(r'%USERPROFILE%\.fieldtheory\bookmarks\bookmarks.db')
    js = os.path.expandvars(r'%USERPROFILE%\.fieldtheory\bookmarks\bookmarks.jsonl')
    info['bookmarks'] = {
        'db_exists': os.path.exists(db),
        'db_mb': round(os.path.getsize(db) / 1048576, 1) if os.path.exists(db) else 0,
        'jsonl_exists': os.path.exists(js),
        'jsonl_mb': round(os.path.getsize(js) / 1048576, 1) if os.path.exists(js) else 0,
    }
    info['patches'] = patch_status()
    env = read_env(env_path())
    info['credentials'] = {k: bool(env.get(k)) for k in ENV_KEYS}
    info['env_writable'] = os.environ.get('FT_ALLOW_ENV_WRITE') == '1'
    info['tools'] = {}
    for tool in ('fieldtheory', 'twitter', 'node', 'python'):
        info['tools'][tool] = shutil.which(tool) is not None
    try:
        r = subprocess.run(['schtasks', '/Query', '/FO', 'CSV', '/NH'],
                           capture_output=True, text=True, timeout=20)
        tasks = []
        for line in r.stdout.splitlines():
            # schtasks emits  "name","status","status",...  with the name quoted
            # and prefixed by a backslash. Take the first field, not the second.
            if not line.startswith('"'):
                continue
            name = line.split('","', 1)[0].lstrip('"\\')
            if name:
                tasks.append(name)
        info['tasks'] = [t for t in tasks
                         if 'twitter' in t.lower() or 'hiring' in t.lower() or 'bookmark' in t.lower()]
    except Exception:
        info['tasks'] = []
    return info


def tail(path, n=25):
    if not os.path.exists(path):
        return []
    return open(path, encoding='utf-8', errors='replace').read().splitlines()[-n:]


def run(config, load, save, load_state, run_one):
    host, port = '127.0.0.1', 8765
    lock = threading.Lock()
    jobs = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, obj, ctype='application/json'):
            raw = (obj if isinstance(obj, (bytes, str)) else json.dumps(obj, ensure_ascii=False)).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _body(self):
            n = int(self.headers.get('Content-Length', 0))
            return json.loads(self.rfile.read(n) or b'{}')

        def do_GET(self):
            path, _, qs = self.path.partition('?')
            query = parse_qs(qs)
            if path in ('/', '/index.html'):
                return self._send(200, open(PAGE, encoding='utf-8').read(), 'text/html; charset=utf-8')
            if path == '/api/searches':
                with lock:
                    return self._send(200, {'searches': load()['searches'], 'state': load_state()})
            if path == '/api/results':
                out = os.path.join(ROOT, 'out', 'searches')
                try:
                    files = sorted(f for f in os.listdir(out) if f.endswith('.json'))
                except FileNotFoundError:
                    files = []
                files.reverse()
                try:
                    page = max(1, int(query.get('page', ['1'])[0]))
                    size = min(50, max(1, int(query.get('size', ['10'])[0])))
                except ValueError:
                    page, size = 1, 10
                total = len(files)
                pages = max(1, (total + size - 1) // size)
                page = min(page, pages)
                items = []
                for fn in files[(page - 1) * size:page * size]:
                    try:
                        d = json.load(open(os.path.join(out, fn), encoding='utf-8'))
                    except Exception:
                        continue
                    items.append({'file': fn, 'name': d.get('name'), 'source': d.get('source'),
                                  'ran_at': d.get('ran_at'), 'counts': d.get('counts', {}),
                                  'openings': d.get('openings', 0),
                                  'tweets': d.get('tweets', [])[:200]})
                return self._send(200, {'results': items, 'page': page, 'pages': pages,
                                        'total': total, 'size': size})
            if path == '/api/commands':
                return self._send(200, {'commands': parse_commands(),
                                        'runnable': sorted(RUNNABLE),
                                        'outdir': os.path.join(ROOT, 'out')})
            if path == '/api/status':
                return self._send(200, status())
            if path == '/api/settings':
                wl = os.path.join(HERE, 'watchlist.txt')
                return self._send(200, {
                    'watchlist': open(wl, encoding='utf-8').read() if os.path.exists(wl) else '',
                    'env_writable': os.environ.get('FT_ALLOW_ENV_WRITE') == '1',
                    'credentials': {k: bool(read_env(env_path()).get(k))
                                    for k in ENV_KEYS},
                    'env_path': env_path(),
                })
            if path == '/api/logs':
                d = os.path.join(ROOT, 'out', 'searches')
                try:
                    files = sorted((os.path.join(d, f) for f in os.listdir(d) if f.endswith('.log')),
                                   key=os.path.getmtime)[-8:]
                except FileNotFoundError:
                    files = []
                return self._send(200, {'logs': [{'file': os.path.basename(f), 'lines': tail(f, 40)}
                                                for f in reversed(files)]})
            if path == '/api/job':
                key = self.path.split('job=')[-1] if 'job=' in self.path else ''
                with lock:
                    j = jobs.get(key, {'state': 'idle', 'output': []})
                return self._send(200, j)
            return self._send(404, {'error': 'not found'})

        def do_POST(self):
            body = self._body()
            path = self.path.split('?')[0]

            if path == '/api/add':
                with lock:
                    cfg = load()
                    if any(s['name'] == body.get('name') for s in cfg['searches']):
                        return self._send(400, {'error': 'name already exists'})
                    entry = {k: v for k, v in body.items() if v not in ('', None, [], {})}
                    entry.setdefault('enabled', True)
                    cfg['searches'].append(entry)
                    save(cfg)
                return self._send(200, {'ok': True})

            if path == '/api/edit':
                with lock:
                    cfg = load()
                    for i, s in enumerate(cfg['searches']):
                        if s['name'] == body.get('name'):
                            patch = {k: v for k, v in body.get('patch', {}).items()
                                     if v not in ('', None)}
                            s.update(patch)
                            cfg['searches'][i] = s
                            save(cfg)
                            return self._send(200, {'ok': True})
                return self._send(404, {'error': 'no such search'})

            if path in ('/api/toggle', '/api/delete'):
                with lock:
                    cfg = load()
                    if path == '/api/delete':
                        cfg['searches'] = [s for s in cfg['searches']
                                           if s['name'] != body.get('name')]
                    else:
                        for s in cfg['searches']:
                            if s['name'] == body.get('name'):
                                s['enabled'] = not s.get('enabled', True)
                    save(cfg)
                return self._send(200, {'ok': True})

            if path == '/api/run':
                name = body.get('name')
                with lock:
                    cfg = load()
                    target = [s for s in cfg['searches'] if s['name'] == name]
                if not target:
                    return self._send(400, {'error': 'no such search'})
                if name in jobs and jobs[name]['state'] == 'running':
                    return self._send(409, {'error': 'already running'})

                def work():
                    jobs[name] = {'state': 'running', 'output': []}
                    try:
                        p = run_one(target[0])
                        jobs[name] = {'state': 'done',
                                      'output': [f"{len(p['tweets'])} tweets, "
                                                 f"{p['openings']} openings"] + list(p['coverage'])}
                    except Exception as e:
                        jobs[name] = {'state': 'failed', 'output': [f'{type(e).__name__}: {e}']}

                threading.Thread(target=work, daemon=True).start()
                return self._send(200, {'ok': True, 'started': name})

            if path == '/api/command':
                key = body.get('key')
                if key not in RUNNABLE:
                    return self._send(400, {'error': 'that command is not on the allowlist'})
                if jobs.get(key, {}).get('state') == 'running':
                    return self._send(409, {'error': 'already running'})

                def work():
                    jobs[key] = {'state': 'running', 'output': ['starting...']}
                    try:
                        env = dict(os.environ, PYTHONIOENCODING='utf-8')
                        r = subprocess.run(RUNNABLE[key], cwd=ROOT, capture_output=True,
                                           text=True, encoding='utf-8', errors='replace',
                                           timeout=3600, env=env)
                        jobs[key] = {'state': 'done' if r.returncode == 0 else 'failed',
                                     'output': (r.stdout or '').splitlines()[-60:]}
                    except Exception as e:
                        jobs[key] = {'state': 'failed', 'output': [f'{type(e).__name__}: {e}']}

                threading.Thread(target=work, daemon=True).start()
                return self._send(200, {'ok': True, 'started': key})

            if path == '/api/run-query':
                q = (body.get('query') or '').strip()
                if not q:
                    return self._send(400, {'error': 'empty query'})
                # X rejects anything over 512 characters. Say so here rather
                # than letting the run fail later with a pipeline error.
                if len(q) > 512:
                    return self._send(400, {'error':
                        f'query is {len(q)} characters. X rejects anything over 512.'})
                key = 'one-off: ' + q[:40]
                if jobs.get(key, {}).get('state') == 'running':
                    return self._send(409, {'error': 'that query is already running'})

                def work():
                    import search as S
                    from datetime import timedelta
                    jobs[key] = {'state': 'running', 'output': ['searching...']}
                    try:
                        since = datetime.now(timezone.utc) - timedelta(days=int(body.get('days_back', 7)))
                        rows, err = S.fetch_live(q, int(body.get('limit', 50)), since,
                                                 int(body.get('min_likes', 0)))
                        if err:
                            raise RuntimeError(err)
                        for r in rows:
                            r.update(S.extract(r))
                            r['bucket'] = S.classify(r.get('text') or '')
                            r['dt'] = S.when(r.get('posted_at') or '')
                        from collections import Counter
                        counts = dict(Counter(r['bucket'] for r in rows))
                        out = os.path.join(ROOT, 'out', 'searches')
                        os.makedirs(out, exist_ok=True)
                        stamp = datetime.now().strftime('%Y-%m-%d_%H%M')
                        base = os.path.join(out, f"oneoff-{stamp}")
                        payload = {'name': 'one-off', 'source': 'live', 'query': q,
                                   'ran_at': datetime.now(timezone.utc).isoformat(),
                                   'since': since.isoformat(),
                                   'coverage': [f'query: {q}'],
                                   'counts': counts, 'openings': counts.get('opening', 0),
                                   'tweets': [{k: v for k, v in r.items() if k != 'dt'} for r in rows]}
                        with open(base + '.json', 'w', encoding='utf-8') as f:
                            json.dump(payload, f, ensure_ascii=False, indent=2)
                        with open(base + '.md', 'w', encoding='utf-8') as f:
                            f.write(f"# one-off\n\n```\n{q}\n```\n\n"
                                    f"{len(rows)} tweets, {counts.get('opening', 0)} openings.\n\n"
                                    + '\n\n'.join(f"**@{r['author_handle']}**  \n{r['text']}\n"
                                                  f"<{r['url']}>" for r in rows[:100]))
                        jobs[key] = {'state': 'done',
                                     'output': [f'{len(rows)} tweets, '
                                                f"{counts.get('opening', 0)} openings",
                                                f'wrote {base}.md']}
                    except Exception as e:
                        jobs[key] = {'state': 'failed', 'output': [f'{type(e).__name__}: {e}']}

                threading.Thread(target=work, daemon=True).start()
                return self._send(200, {'ok': True, 'started': key})

            if path == '/api/watchlist':
                wl = os.path.join(HERE, 'watchlist.txt')
                with open(wl, 'w', encoding='utf-8') as f:
                    f.write(body.get('text', ''))
                return self._send(200, {'ok': True})

            if path == '/api/env':
                upd = body.get('set') or {}
                for k in upd:
                    if k not in ENV_KEYS:
                        return self._send(400, {'error': f'{k} is not a known credential'})
                # Writing credentials is OFF unless the server was started with
                # FT_ALLOW_ENV_WRITE=1. On 2026-10-10 a test POST to this path
                # overwrote a live token twice, because proving the path worked
                # required destroying the thing it protects. Now it cannot be
                # reached by accident, and the page says so.
                if os.environ.get('FT_ALLOW_ENV_WRITE') != '1':
                    return self._send(403, {'error':
                        'credential writing is disabled. restart the panel with '
                        'FT_ALLOW_ENV_WRITE=1 to turn it on.'})
                write_env(env_path(), upd)
                return self._send(200, {'ok': True, 'written': sorted(upd)})

            return self._send(404, {'error': 'not found'})

    srv = ThreadingHTTPServer((host, port), Handler)
    print(f'control panel on http://{host}:{port}   (ctrl-c to stop)')
    webbrowser.open(f'http://{host}:{port}')
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('\nstopped')