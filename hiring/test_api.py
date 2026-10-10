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

proc.terminate()
try:
    proc.wait(timeout=10)
except Exception:
    proc.kill()
sys.exit(1 if bad else 0)