"""Check the HTTP layer: list CRUD, search creation, and every rejection path.

    python test_api.py

Why. serve.py had no test at all, so a renamed route or a dropped validation
branch would only fail in a browser. This boots the real server on a spare port,
exercises it, and asserts the status codes. Run it on its own port so a panel you
already have open does not get in the way.
"""

import json, subprocess, sys, threading, time, urllib.request, urllib.error, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8793   # not 8765, so a running panel does not block the test
sys.path.insert(0, HERE)

proc = subprocess.Popen([sys.executable, 'ctl.py', 'serve', '--port', str(PORT)], cwd=HERE,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                        encoding='utf-8', errors='replace', env=dict(os.environ, PYTHONIOENCODING='utf-8'))


def call(path, body=None, method=None):
    url = f'http://127.0.0.1:{PORT}{path}'
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method or ('POST' if data else 'GET'),
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b'{}')
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b'{}')
    except Exception as e:
        return 0, {'error': str(e)}


for _ in range(40):
    s, _b = call('/api/lists')
    if s == 200:
        break
    time.sleep(0.5)
print('server up:', s)

checks = [
    ('create list',      '/api/list/add',  {'name': 'tmp-x', 'kind': 'handles', 'handles': 'a,@b'}, 200),
    ('bad xlist id',     '/api/list/add',  {'name': 'tmp-y', 'kind': 'xlist', 'list_id': 'abc'}, 400),
    ('xlist no id',      '/api/list/add',  {'name': 'tmp-z', 'kind': 'xlist'}, 400),
    ('duplicate name',   '/api/list/add',  {'name': 'tmp-x', 'kind': 'handles', 'handles': 'q'}, 400),
    ('list no name',     '/api/list/add',  {'kind': 'handles'}, 400),
    ('unknown list edit','/api/list/edit', {'name': 'nope', 'handles': ['a']}, 404),
    ('search on list',   '/api/add',       {'name': 'tmp-s', 'source': 'watchlist', 'list': 'recruiters'}, 200),
    ('duplicate search', '/api/add',       {'name': 'tmp-s', 'source': 'live'}, 400),
    # /api/fetch over HTTP. Only values the manifest must REFUSE, because every
    # value it accepts starts a real crawl that would hit X and write to out\.
    # The accepted values are checked against build_argv itself, further down.
    ('unknown fetch',    '/api/fetch',     {'key': 'rm-rf', 'params': {}}, 400),
    ('missing handle',   '/api/fetch',     {'key': 'crawl-account', 'params': {}}, 400),
    ('handle injection', '/api/fetch',     {'key': 'crawl-account', 'params': {'handle': 'a; rm -rf'}}, 400),
    ('tweet id letters', '/api/fetch',     {'key': 'crawl-thread', 'params': {'tweet_id': 'abc123'}}, 400),
    ('tweet id missing', '/api/fetch',     {'key': 'crawl-replies', 'params': {}}, 400),
    ('limit not number', '/api/fetch',     {'key': 'crawl-threads', 'params': {'limit': 'ten'}}, 400),
    ('limit too big',    '/api/fetch',     {'key': 'crawl-threads', 'params': {'limit': 999999}}, 400),
    ('limit below min',  '/api/fetch',     {'key': 'crawl-threads', 'params': {'limit': 0}}, 400),
    ('delay not float',  '/api/fetch',     {'key': 'crawl-threads', 'params': {'delay': 'fast'}}, 400),
    ('redo needs bool',  '/api/fetch',     {'key': 'crawl-replies-all', 'params': {'redo': 'maybe'}}, 400),
    ('reply top zero',   '/api/fetch',     {'key': 'crawl-replies-all', 'params': {'top': 0}}, 400),
    # rebuild is destructive. It must be refused without an explicit confirm,
    # because a browser dialog alone can be skipped by editing the page.
    ('rebuild unconfirmed', '/api/fetch',  {'key': 'sync-bookmarks', 'params': {'rebuild': True}}, 428),
    ('rebuild as string',   '/api/fetch',  {'key': 'sync-bookmarks', 'params': {'rebuild': 'yes'}}, 400),
    # a folder name holding a path separator must not reach the ft call
    ('folder traversal',    '/api/fetch',  {'key': 'sync-bookmarks', 'params': {'folder': '../etc'}}, 400),
]
bad = 0
for label, path, body, want in checks:
    got, resp = call(path, body)
    ok = got == want
    bad += not ok
    print(f"{'ok ' if ok else 'FAIL'} {label:20} got {got} want {want}  {str(resp.get('error',''))[:60]}")

s, _ = call('/api/lists')
call('/api/list/delete', {'name': 'tmp-x'})
call('/api/delete', {'name': 'tmp-s'})
s2, b2 = call('/api/lists')
print(f'lists after cleanup: {len(b2["lists"])}')
names = [x['name'] for x in b2['lists']]
print('tmp artifacts left:', [n for n in names if n.startswith('tmp')] or 'none')

# Accepted values go through build_argv directly. Over HTTP they would start a
# real crawl against X, which a test has no business doing.
import serve
argv_cases = [
    ('crawl-threads',   {'limit': 200, 'top': 20, 'max': 100, 'delay': 1.5},
     ['threads', '--limit', '200', '--top', '20', '-n', '100', '--delay', '1.5']),
    ('crawl-threads',   {'limit': 5, 'top': '', 'max': 50, 'delay': 2},
     ['threads', '--limit', '5', '-n', '50', '--delay', '2']),
    ('crawl-threads',   {'limit': '', 'top': '', 'max': '', 'delay': 3.0},
     ['threads', '--delay', '3']),
    ('crawl-threads',   {'limit': '', 'top': '', 'max': '', 'delay': 3},
     ['threads', '--delay', '3']),
    ('crawl-account',   {'handle': 'AScully789', 'max': 2000},
     ['account', 'AScully789', '-n', '2000']),
    ('crawl-account',   {'handle': '@comma_ai', 'max': ''}, ['account', 'comma_ai']),
    ('crawl-thread',    {'tweet_id': '2108246041548018053', 'max': 100, 'top': 20, 'save': True},
     ['thread', '2108246041548018053', '-n', '100', '--top', '20', '--save']),
    ('crawl-thread',    {'tweet_id': '2108246041548018053', 'max': '', 'top': '', 'save': False},
     ['thread', '2108246041548018053']),
    ('crawl-replies',   {'tweet_id': '2108246041548018053', 'top': 10, 'max': 200, 'save': True},
     ['replies', '2108246041548018053', '--top', '10', '-n', '200', '--save']),
    ('crawl-replies',   {'tweet_id': '2108246041548018053', 'top': 10, 'max': 200, 'save': False},
     ['replies', '2108246041548018053', '--top', '10', '-n', '200']),
    ('crawl-replies-all', {'limit': 200, 'top': 10, 'max': 200, 'delay': 1.5, 'redo': False},
     ['replies-all', '--limit', '200', '--top', '10', '-n', '200', '--delay', '1.5']),
    ('crawl-replies-all', {'limit': 5, 'top': '', 'max': '', 'delay': 2, 'redo': True},
     ['replies-all', '--limit', '5', '--delay', '2', '--redo']),
    ('crawl-replies-all', {'limit': '', 'top': '', 'max': '', 'delay': '', 'redo': False},
     ['replies-all']),
    ('sync-bookmarks',  {'max-minutes': 240, 'count': 100000},
     ['--max-minutes', '240', '--count', '100000']),
    ('sync-bookmarks',  {'max-minutes': 60, 'count': ''}, ['--max-minutes', '60']),
    ('sync-bookmarks',  {'max-minutes': 240, 'count': '', 'target-adds': 500, 'gaps': True},
     ['--max-minutes', '240', '--target-adds', '500', '--gaps']),
    ('sync-bookmarks',  {'max-minutes': '', 'count': '', 'rebuild': True},
     ['--rebuild']),
    ('sync-bookmarks',  {'max-minutes': '', 'count': '', 'folder': 'AI stuff', 'folders': True},
     ['--folders', '--folder', 'AI stuff']),
    ('sync-bookmarks',  {'max-minutes': 30, 'count': '', 'delay-ms': 1200, 'media': True,
                         'skip-md': True},
     ['--max-minutes', '30', '--delay-ms', '1200', '--media', '--skip-md']),
]
for key, params, want in argv_cases:
    got = serve.build_argv(serve.FETCH[key], params)[2:]
    ok = got == want
    bad += not ok
    print(f"{'ok ' if ok else 'FAIL'} argv {key:15} {' '.join(got)}")
    if not ok:
        print(f'       want: {" ".join(want)}')

# Every job must name a script that exists, or the button fails only on click.
for key, job in serve.FETCH.items():
    path = os.path.join(os.path.dirname(HERE), job['base'][0])
    ok = os.path.exists(path)
    bad += not ok
    print(f"{'ok ' if ok else 'FAIL'} script {job['base'][0]}")

proc.terminate()
try:
    proc.wait(timeout=10)
except Exception:
    proc.kill()
sys.exit(1 if bad else 0)