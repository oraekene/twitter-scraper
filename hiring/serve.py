"""Local control panel for the whole twitter scraper tool. Standard library only.

Bound to 127.0.0.1 on purpose. Running anything here uses your .env credentials
and writes to your real database, so it must not be reachable from the network.
Nothing leaves this machine.

Safety. There is no arbitrary command runner. /api/run takes a key that must
appear in RUNNABLE below, and that table is the complete list of what a browser
request can start. Everything else in the UI is text to copy. Credentials are
write-only: /api/env reports whether each key is set, never its value, and
PUT /api/env writes the file without ever returning it.

/api/fetch is the same idea with parameters. It takes a key from FETCH below and
builds an argv list from it. Every value the browser sends is checked by
build_argv against the field that declared it, and the result is handed to
subprocess as a list, so there is no shell and no way to splice in a new
command. Adding a flag to crawl_tweets.py means adding one line to FETCH.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
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
    'tests':               ['python', '-c', 'import subprocess,sys;'
                            'jobs=[("test_sync.py",),("test_crawl.py",),("test_weekly.py",),'
                            '("hiring/pat.py",),("hiring/sem.py","selftest")];'
                            'r=[subprocess.run([sys.executable,*j],capture_output=True).returncode'
                            ' for j in jobs];'
                            'print("exit codes:",r);sys.exit(max(r))'],
    'sem-selftest':        [sys.executable, os.path.join(HERE, 'sem.py'), 'selftest'],
    'fix-fieldtheory':     ['node', os.path.join(HERE, 'fix-fieldtheory.js')],
    'fix-twitter-cli':     ['node', os.path.join(HERE, 'fix-twitter-cli.js')],
}

# Section 1 of COMMANDS.md as data, so the page cannot drift from the scripts.
#
# base     the argv after "python", without ROOT. The first element is the
#          script name, the rest are fixed subcommand words.
# quick    show this one on the dashboard as well as on the Fetch tab.
# fields   every parameter the command accepts. kind is text, int, float or
#          flag. flag names the argparse option when it is not --<name>, and
#          positional marks the one value that is a bare word. A field whose
#          flag is absent and which is not positional still gets --<name>,
#          so adding a parameter cannot silently become a stray argument.
#          Leave a value blank to drop the parameter and use the script default.
FETCH = {
    'sync-bookmarks': {
        'label': 'Pull new bookmarks',
        'why': 'Repeat until it stops saying "max runtime reached".',
        'base': ['sync_bookmarks.py'],
        'quick': True,
        'fields': [
            {'name': 'max-minutes', 'label': 'Minutes per pass', 'kind': 'int',
             'default': 240, 'min': 1, 'max': 1440,
             'help': 'Fieldtheory stops here and saves a cursor, so run it again.'},
            {'name': 'count', 'label': 'Bookmarks to fetch from X', 'kind': 'int',
             'default': 100000, 'min': 1, 'max': 200000,
             'help': 'How many to ask twitter-cli for in one go.'},
            {'name': 'target-adds', 'label': 'Stop after N new bookmarks', 'kind': 'int',
             'default': '', 'min': 1, 'max': 100000,
             'help': 'Gentler on rate limits than a time limit. Leave blank for no limit.'},
            {'name': 'max-pages', 'label': 'Max pages per pass', 'kind': 'int',
             'default': '', 'min': 1, 'max': 100000,
             'help': 'Blank means no page cap.'},
            {'name': 'delay-ms', 'label': 'Milliseconds between requests', 'kind': 'int',
             'default': '', 'min': 0, 'max': 60000,
             'help': 'Fieldtheory uses 600. Raise it if X starts answering 429.'},
            {'name': 'gaps', 'label': 'Backfill gaps', 'kind': 'flag', 'default': False,
             'help': 'Fetches quoted tweets, truncated articles, and linked article text.'},
            {'name': 'folders', 'label': 'Also sync X folder tags', 'kind': 'flag', 'default': False,
             'help': 'Needed before fieldtheory list --folder shows anything.'},
            {'name': 'folder', 'label': 'Only this folder', 'kind': 'text',
             'default': '', 'pattern': r'[^<>:"/\\|?*]{1,80}',
             'placeholder': 'AI stuff',
             'help': 'Leave blank for every folder.'},
            {'name': 'classify', 'label': 'Classify after syncing', 'kind': 'flag', 'default': False,
             'help': 'Runs the LLM classifier. Costs tokens.'},
            {'name': 'engine', 'label': 'LLM engine', 'kind': 'text',
             'default': '', 'pattern': r'[A-Za-z0-9_-]{1,40}',
             'placeholder': 'claude or codex'},
            {'name': 'media', 'label': 'Download images and video', 'kind': 'flag', 'default': False,
             'help': 'Off by default because it is slow. Existing media is not deleted.'},
            {'name': 'media-max-bytes', 'label': 'Media size cap in bytes', 'kind': 'int',
             'default': '', 'min': 1, 'max': 2147483647,
             'help': 'Per asset. Fieldtheory default is 200 MB. Blank uses its default.'},
            {'name': 'skip-profile-images', 'label': 'Skip profile pictures', 'kind': 'flag',
             'default': False},
            {'name': 'skip-md', 'label': 'Skip the markdown export', 'kind': 'flag', 'default': False,
             'help': 'Stops after the database sync. fieldtheory md --changed is the fast way back.'},
            {'name': 'rebuild', 'label': 'Full re-crawl, discard the cursor', 'kind': 'flag',
             'default': False, 'destructive': True,
             'help': 'Re-downloads every bookmark from scratch. Slow, and your cursor is gone.'},
        ],
    },
    'crawl-threads': {
        'label': 'Expand every bookmarked thread',
        'why': 'Expand full threads behind every bookmarked tweet. Resumable.',
        'base': ['crawl_tweets.py', 'threads'],
        'quick': True,
        'fields': [
            {'name': 'limit', 'label': 'Threads this run', 'kind': 'int',
             'default': 200, 'min': 1, 'max': 5000,
             'help': 'out\\threads-index.json remembers what is done, so rerun for the next batch.'},
            {'name': 'top', 'label': 'Replies kept per thread', 'kind': 'int',
             'default': 20, 'min': 0, 'max': 500},
            {'name': 'max', 'flag': '-n', 'label': 'Tweets fetched per thread', 'kind': 'int',
             'default': 100, 'min': 1, 'max': 1000},
            {'name': 'delay', 'label': 'Seconds between calls', 'kind': 'float',
             'default': 1.5, 'min': 0, 'max': 60,
             'help': 'X answers 429 when calls come too fast. 1.5 is safe.'},
        ],
    },
    'crawl-account': {
        'label': "Pull every tweet from an account",
        'why': "Pull every tweet from an account, yours or anyone's.",
        'base': ['crawl_tweets.py', 'account'],
        'quick': True,
        'fields': [
            {'name': 'handle', 'label': 'Handle', 'kind': 'text', 'positional': True,
             'default': '', 'required': True, 'pattern': r'[A-Za-z0-9_]{1,15}',
             'placeholder': 'AScully789'},
            {'name': 'max', 'flag': '-n', 'label': 'Tweets to pull', 'kind': 'int',
             'default': 2000, 'min': 1, 'max': 100000},
        ],
    },
    'crawl-replies': {
        'label': 'Top replies to one tweet',
        'why': 'Top N replies to one tweet, ranked by engagement.',
        'base': ['crawl_tweets.py', 'replies'],
        'fields': [
            {'name': 'tweet_id', 'label': 'Tweet id', 'kind': 'text', 'positional': True,
             'default': '', 'required': True, 'pattern': r'\d{5,25}',
             'placeholder': '2108246041548018053'},
            {'name': 'top', 'label': 'Replies to keep', 'kind': 'int',
             'default': 10, 'min': 1, 'max': 500},
            {'name': 'max', 'flag': '-n', 'label': 'Replies fetched', 'kind': 'int',
             'default': 200, 'min': 1, 'max': 1000},
            {'name': 'save', 'label': 'Save to out\\', 'kind': 'flag', 'default': True},
        ],
    },
    'crawl-replies-all': {
        'label': 'Top replies to every bookmark',
        'why': 'Same batch pass as threads, but ranked by engagement. Resumable.',
        'base': ['crawl_tweets.py', 'replies-all'],
        'quick': True,
        'fields': [
            {'name': 'limit', 'label': 'Tweets this run', 'kind': 'int',
             'default': 200, 'min': 1, 'max': 5000,
             'help': 'out\\replies-index.json remembers what is done, so rerun for the next batch. '
                     'Separate from the thread index, so the two passes never block each other.'},
            {'name': 'top', 'label': 'Replies kept per tweet', 'kind': 'int',
             'default': 10, 'min': 1, 'max': 500},
            {'name': 'max', 'flag': '-n', 'label': 'Replies fetched', 'kind': 'int',
             'default': 200, 'min': 1, 'max': 1000},
            {'name': 'delay', 'label': 'Seconds between calls', 'kind': 'float',
             'default': 1.5, 'min': 0, 'max': 60,
             'help': 'X answers 429 when calls come too fast. 1.5 is safe.'},
            {'name': 'redo', 'label': 'Ignore the index and start again', 'kind': 'flag',
             'default': False,
             'help': 'Turn it on when the last run kept fewer replies than you want now.'},
        ],
    },
    'crawl-thread': {
        'label': 'Full thread behind one tweet',
        'why': 'Full thread behind one tweet.',
        'base': ['crawl_tweets.py', 'thread'],
        'fields': [
            {'name': 'tweet_id', 'label': 'Tweet id', 'kind': 'text', 'positional': True,
             'default': '', 'required': True, 'pattern': r'\d{5,25}',
             'placeholder': '2108246041548018053'},
            {'name': 'max', 'flag': '-n', 'label': 'Tweets fetched', 'kind': 'int',
             'default': 100, 'min': 1, 'max': 1000},
            {'name': 'top', 'label': 'Replies to keep', 'kind': 'int',
             'default': 20, 'min': 0, 'max': 500},
            {'name': 'save', 'label': 'Save to out\\', 'kind': 'flag', 'default': True},
        ],
    },
    'sem-search': {
        'label': 'Concept search',
        'why': 'Search a concept you can describe in words, with no embeddings. '
               'Offline against your bookmarks by default, live against X on request.',
        'base': ['hiring/sem.py', 'search'],
        'fields': [
            {'name': 'concept', 'label': 'Concept in plain English', 'kind': 'text',
             'positional': True, 'default': 'tweets remotely hinting at hiring',
             'required': True, 'pattern': r'[^<>:"/\\|?*]{3,120}',
             'placeholder': 'accounts complaining about Cursor performance',
             'help': 'Never a keyword list. A sentence works best.'},
            {'name': 'source', 'label': 'Search where', 'kind': 'text', 'default': 'bookmarks',
             'pattern': r'bookmarks|x',
             'help': 'bookmarks is free and offline. x spends rate limit on live search.'},
            {'name': 'seed-group', 'label': 'Seed from patterns.json', 'kind': 'text',
             'default': '', 'pattern': r'[A-Za-z,]{0,60}',
             'placeholder': 'OFFER,APPLY_CTA',
             'help': 'Blank generates queries with a model. A group name reuses the '
                     'hand-written phrase set instead, which is the apples to apples '
                     'comparison against the existing module.'},
            {'name': 'limit', 'label': 'Rows per query', 'kind': 'int',
             'default': 200, 'min': 1, 'max': 1000},
            {'name': 'pool', 'label': 'Tweets sent to the classifier', 'kind': 'int',
             'default': 300, 'min': 1, 'max': 2000,
             'help': 'The classifier reads this many. Each one is one Jev call.'},
            {'name': 'queries', 'label': 'Queries to generate', 'kind': 'int',
             'default': 60, 'min': 5, 'max': 200,
             'help': 'More is better up to the rate limit. Agreement between queries is '
                     'the whole ranking signal, so a small number finds nothing.'},
            {'name': 'frontier', 'label': 'Rerank N unclear with a big model', 'kind': 'int',
             'default': 0, 'min': 0, 'max': 200,
             'help': 'Zero skips it. Needs a chat model key in .env, which Jev is not.'},
            {'name': 'n', 'label': 'Rows to show', 'kind': 'int',
             'default': 20, 'min': 1, 'max': 200},
            {'name': 'since', 'label': 'Days back (bookmarks only)', 'kind': 'int',
             'default': '', 'min': 1, 'max': 3650,
             'help': 'Counts from when you saved it, not when it was posted.'},
            {'name': 'min-likes', 'label': 'Minimum likes', 'kind': 'int',
             'default': 0, 'min': 0, 'max': 1000000},
            {'name': 'fresh', 'label': 'Only what this run found', 'kind': 'flag',
             'default': False,
             'help': 'Off shows everything ever found for the concept. On shows today only.'},
        ],
    },
    'sem-eval': {
        'label': 'Is the model better than the regex?',
        'why': 'The adversarial suite. Fourteen tweets that a regex cannot separate, so '
               'it is the cheapest test that can say whether the model layer earns its cost.',
        'base': ['hiring/sem.py', 'eval'],
        'fields': [
            {'name': 'concept', 'label': 'Concept', 'kind': 'text', 'positional': True,
             'default': 'hiring', 'required': True, 'pattern': r'[^<>:"/\\|?*]{1,120}'},
            {'name': 'suite', 'label': 'Suite', 'kind': 'text', 'default': 'adversarial',
             'pattern': r'gold|adversarial',
             'help': 'adversarial needs no labels. gold scores a run against labels '
                     'you recorded with: python sem.py gold <id> hit'},
        ],
    },
    'sem-rerank': {
        'label': 'Rerank the unclear band',
        'why': 'Send only the tweets Jev would not commit to, to a big chat model, and '
               'promote whatever it likes. No retrieval, so it costs nothing but the call.',
        'base': ['hiring/sem.py', 'rerank'],
        'fields': [
            {'name': 'concept', 'label': 'Concept', 'kind': 'text', 'positional': True,
             'default': 'hiring', 'required': True, 'pattern': r'[^<>:"/\\|?*]{1,120}'},
            {'name': 'n', 'label': 'Unclear tweets to rerank', 'kind': 'int',
             'default': 20, 'min': 1, 'max': 200},
            {'name': 'run', 'label': 'Run number', 'kind': 'int',
             'default': '', 'min': 1, 'max': 1000000,
             'help': 'Blank uses the most recent run for this concept.'},
        ],
    },
    'sem-queries': {
        'label': 'Which queries paid off',
        'why': 'The scoreboard. Every query with how many top results it has produced, so '
               'the dead ones are visible and can be retired.',
        'base': ['hiring/sem.py', 'queries'],
        'fields': [
            {'name': 'concept', 'label': 'Concept', 'kind': 'text', 'positional': True,
             'default': 'hiring', 'required': True, 'pattern': r'[^<>:"/\\|?*]{1,120}'},
        ],
    },
}

# Keys whose presence matters in .env. Values are never sent to the browser.
ENV_KEYS = ('TWITTER_AUTH_TOKEN', 'TWITTER_CT0', 'TYPESAFE_API_KEY')

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


class BadValue(ValueError):
    """A field value the browser sent that the field will not accept."""


def build_argv(job, params):
    """Turn a FETCH entry plus browser values into an argv list.

    Nothing here is ever joined into a string for a shell. Every value is
    matched against the field that declared it: a text field against its
    pattern, a number against its bounds. A value that does not fit raises
    BadValue and the caller answers 400, so the subprocess never starts.

    A blank value means "leave the parameter off", which is how you get the
    script's own default rather than the panel's.
    """
    base = list(job['base'])
    argv = [sys.executable, os.path.join(ROOT, base[0])] + base[1:]
    for f in job['fields']:
        name = f['name']
        if f['kind'] == 'flag':
            raw = params.get(name, False)
            # A flag only has two states. Anything else is a broken client, and
            # ignoring it would start a run with the flag silently off, which is
            # the one mistake here that would touch the wrong data.
            if raw in (True, 'true', 'on', '1'):
                argv.append(f.get('flag') or '--' + name)
            elif raw not in (False, '', None, 'false', 'off', '0', 0):
                raise BadValue(f"{f['label']} must be on or off")
            continue
        raw = str(params.get(name, '')).strip()
        if not raw:
            if f.get('required'):
                raise BadValue(f"{f['label']} is required")
            continue
        if f['kind'] == 'text':
            value = raw.lstrip('@')
            if not re.fullmatch(f['pattern'], value):
                raise BadValue(f"{f['label']} is not a valid {f['label'].lower()}")
        else:
            try:
                value = int(raw) if f['kind'] == 'int' else float(raw)
            except ValueError:
                raise BadValue(f"{f['label']} must be a number")
            if value < f.get('min', value) or value > f.get('max', value):
                raise BadValue(f"{f['label']} must be between {f.get('min')} and {f.get('max')}")
            # argparse takes 3.0 for a float field, but print it as 3 anyway.
            value = str(int(value)) if f['kind'] == 'float' and value == int(value) else str(value)
        if f.get('positional'):
            argv.append(value)
        else:
            argv += [f.get('flag') or '--' + name, value]
    return argv


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


def run(config, load, save, load_state, run_one, load_lists, save_lists, port=8765,
        check=None):
    host = '127.0.0.1'
    lock = threading.Lock()
    jobs = {}

    def start(key, argv, timeout=7200):
        """Run argv in the background and stream its output into jobs[key].

        Shared by /api/command and /api/fetch so both behave the same way. The
        old version waited for the whole process before showing anything, which
        on a 200 thread crawl meant minutes of a blank panel with no way to tell
        a slow run from a stuck one. Lines are appended as they arrive and the
        last 400 are kept, because the crawl prints one line per thread.
        """
        def work():
            jobs[key] = {'state': 'running', 'output': ['starting...'], 'argv': argv}
            try:
                env = dict(os.environ, PYTHONIOENCODING='utf-8')
                # Resolve argv[0] first. fieldtheory and twitter are .CMD shims
                # on Windows, and CreateProcess will not run those by bare name,
                # so every command on the panel died with FileNotFoundError
                # until this line went in. which() finds the real path.
                exe = shutil.which(argv[0]) or argv[0]
                p = subprocess.Popen([exe, *argv[1:]], cwd=ROOT, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True,
                                     encoding='utf-8', errors='replace', env=env)
                deadline = time.monotonic() + timeout
                for line in p.stdout:
                    with lock:
                        j = jobs[key]
                        j['output'] = (j['output'] + [line.rstrip('\n')])[-400:]
                    if time.monotonic() > deadline:
                        p.kill()
                        with lock:
                            jobs[key]['output'].append('killed after the time limit')
                        break
                p.wait()
                with lock:
                    jobs[key]['state'] = 'done' if p.returncode == 0 else 'failed'
            except Exception as e:
                with lock:
                    jobs[key] = {'state': 'failed', 'output': [f'{type(e).__name__}: {e}'],
                                 'argv': argv}
        threading.Thread(target=work, daemon=True).start()

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
            if path == '/api/lists':
                with lock:
                    return self._send(200, {'lists': load_lists()['lists']})
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
            if path == '/api/fetch':
                return self._send(200, {'jobs': [{'key': k, **j} for k, j in FETCH.items()]})
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
                    if check:
                        try:
                            check(entry)
                        except ValueError as e:
                            return self._send(400, {'error': str(e)})
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
                            if check:
                                try:
                                    check(s)
                                except ValueError as e:
                                    return self._send(400, {'error': str(e)})
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
                start(key, RUNNABLE[key])
                return self._send(200, {'ok': True, 'started': key})

            if path == '/api/fetch':
                key = body.get('key')
                job = FETCH.get(key)
                if not job:
                    return self._send(400, {'error': 'that fetch is not on the allowlist'})
                if jobs.get(key, {}).get('state') == 'running':
                    return self._send(409, {'error': 'already running'})
                params = body.get('params') or {}
                # A destructive flag has to be confirmed here, not in the page.
                # Anything that reaches the browser can be edited or replayed
                # with curl, so a confirm dialog on its own is a suggestion.
                risky = [f['label'] for f in job['fields']
                         if f.get('destructive') and params.get(f['name']) in
                         (True, 'true', 'on', '1')]
                if risky and body.get('confirm') is not True:
                    return self._send(428, {'error': 'confirm required', 'confirm': risky})
                try:
                    argv = build_argv(job, params)
                except BadValue as e:
                    return self._send(400, {'error': str(e)})
                start(key, argv)
                return self._send(200, {'ok': True, 'started': key, 'argv': argv})

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

            if path == '/api/list/add':
                with lock:
                    lc = load_lists()
                    name = (body.get('name') or '').strip()
                    kind = body.get('kind', 'handles')
                    if not name:
                        return self._send(400, {'error': 'name is required'})
                    if any(l['name'] == name for l in lc['lists']):
                        return self._send(400, {'error': 'that name already exists'})
                    if kind not in ('handles', 'xlist'):
                        return self._send(400, {'error': 'kind must be handles or xlist'})
                    entry = {'name': name, 'kind': kind, 'note': body.get('note', '')}
                    if kind == 'handles':
                        hs = body.get('handles')
                        if isinstance(hs, str):
                            hs = [h.strip().lstrip('@') for h in hs.replace('\n', ',').split(',')]
                        entry['handles'] = [h.strip().lstrip('@') for h in (hs or []) if h.strip()]
                    else:
                        lid = (body.get('list_id') or '').strip()
                        if not lid:
                            return self._send(400, {'error': 'an X list needs its id'})
                        if not lid.isdigit():
                            return self._send(400, {'error': 'a list id is the number in the list URL'})
                        entry['list_id'] = lid
                    lc['lists'].append(entry)
                    save_lists(lc)
                return self._send(200, {'ok': True, 'name': name})

            if path == '/api/list/edit':
                with lock:
                    lc = load_lists()
                    name = body.get('name')
                    for l in lc['lists']:
                        if l['name'] != name:
                            continue
                        if 'note' in body:
                            l['note'] = body['note']
                        if 'handles' in body:
                            hs = body['handles']
                            if isinstance(hs, str):
                                hs = [h.strip().lstrip('@') for h in hs.replace('\n', ',').split(',')]
                            l['handles'] = [h.strip().lstrip('@') for h in hs if h.strip()]
                        if 'list_id' in body and body['list_id']:
                            l['list_id'] = str(body['list_id']).strip()
                        save_lists(lc)
                        return self._send(200, {'ok': True})
                return self._send(404, {'error': 'no such list'})

            if path == '/api/list/delete':
                with lock:
                    lc = load_lists()
                    before = len(lc['lists'])
                    lc['lists'] = [l for l in lc['lists'] if l['name'] != body.get('name')]
                    if len(lc['lists']) == before:
                        return self._send(404, {'error': 'no such list'})
                    save_lists(lc)
                return self._send(200, {'ok': True})

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
    if port == 8765:
        webbrowser.open(f'http://{host}:{port}')
    else:
        print(f'not opening a browser, non-default port. open http://{host}:{port} yourself')
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('\nstopped')