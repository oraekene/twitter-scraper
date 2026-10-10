"""Local browser control panel for ctl.py. Standard library only, loopback only.

Bound to 127.0.0.1 on purpose. It holds your X session cookies indirectly, since
running a search here uses your .env, so it must not be reachable from the
network. Nothing leaves this machine.
"""

import json
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, 'web', 'index.html')


def run(config, load, save, load_state, run_one):
    host, port = '127.0.0.1', 8765
    lock = threading.Lock()
    running = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype='application/json'):
            raw = body.encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            path = self.path.split('?')[0]
            if path in ('/', '/index.html'):
                return self._send(200, open(PAGE, encoding='utf-8').read(), 'text/html; charset=utf-8')
            if path == '/api/searches':
                with lock:
                    return self._send(200, json.dumps(
                        {'searches': load()['searches'], 'state': load_state()}, ensure_ascii=False))
            if path == '/api/results':
                out = os.path.join(os.path.dirname(HERE), 'out', 'searches')
                try:
                    files = sorted(f for f in os.listdir(out) if f.endswith('.json'))[-60:]
                except FileNotFoundError:
                    files = []
                items = []
                for fn in reversed(files):
                    try:
                        d = json.load(open(os.path.join(out, fn), encoding='utf-8'))
                    except Exception:
                        continue
                    items.append({'file': fn, 'name': d.get('name'), 'source': d.get('source'),
                                  'ran_at': d.get('ran_at'), 'counts': d.get('counts', {}),
                                  'openings': d.get('openings', 0),
                                  'tweets': d.get('tweets', [])[:200]})
                return self._send(200, json.dumps({'results': items}, ensure_ascii=False))
            return self._send(404, '{"error":"not found"}')

        def do_POST(self):
            n = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(n) or b'{}')
            path = self.path.split('?')[0]

            if path == '/api/add':
                with lock:
                    cfg = load()
                    if any(s['name'] == body.get('name') for s in cfg['searches']):
                        return self._send(400, '{"error":"name already exists"}')
                    entry = {k: v for k, v in body.items() if v not in ('', None, [], {})}
                    entry.setdefault('enabled', True)
                    cfg['searches'].append(entry)
                    save(cfg)
                return self._send(200, json.dumps({'ok': True}))

            if path == '/api/toggle':
                with lock:
                    cfg = load()
                    for s in cfg['searches']:
                        if s['name'] == body.get('name'):
                            s['enabled'] = not s.get('enabled', True)
                    save(cfg)
                return self._send(200, json.dumps({'ok': True}))

            if path == '/api/delete':
                with lock:
                    cfg = load()
                    cfg['searches'] = [s for s in cfg['searches'] if s['name'] != body.get('name')]
                    save(cfg)
                return self._send(200, json.dumps({'ok': True}))

            if path == '/api/run':
                name = body.get('name')
                with lock:
                    cfg = load()
                    target = [s for s in cfg['searches'] if s['name'] == name]
                if not target:
                    return self._send(400, '{"error":"no such search"}')
                if name in running:
                    return self._send(409, '{"error":"already running"}')

                def work():
                    running.append(name)
                    try:
                        run_one(target[0])
                    finally:
                        running.remove(name)

                threading.Thread(target=work, daemon=True).start()
                return self._send(200, json.dumps({'ok': True, 'started': name}))

            return self._send(404, '{"error":"not found"}')

    srv = ThreadingHTTPServer((host, port), Handler)
    print(f'control panel on http://{host}:{port}   (ctrl-c to stop)')
    webbrowser.open(f'http://{host}:{port}')
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('\nstopped')