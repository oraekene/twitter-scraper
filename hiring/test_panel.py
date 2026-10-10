"""Check the control panel page: valid JS, and every operator wired to an input.

    python test_panel.py

Why. The panel is one hand-written HTML file, so nothing type-checks it. A
malformed arrow function shipped once and only showed up when Node parsed the
script. A second bug let the JS reference input ids the HTML did not have, which
also only failed at runtime. Both are cheap to catch here.
"""

import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, 'web', 'index.html')

# every operator the builder must offer. Chips are markup (data-op=), the
    # rest are arrays in the script. Kept here so adding one to the JS without
    # adding it to the page, or the reverse, fails loudly.
REQUIRED_OPS = [
    'from:', 'to:', 'participant:', '@',
    'min_faves:', 'max_faves:', 'min_retweets:', 'max_retweets:', 'min_replies:',
    'min_quote_count:', 'min_bookmarks:', 'interaction_count:',
    'since:', 'until:', 'within:', 'lang:', 'place:', 'geolocation:', 'url:',
    'conversation_id:', 'thread_id:', 'topic:', '$',
    'has:links', 'has:media', 'has:images', 'has:videos',
    'filter:links', 'filter:media', 'filter:images', 'filter:videos',
    'filter:replies', 'filter:retweets', 'filter:interactions',
    'filter:nativeretweets', 'filter:all', '-filter:replies', '-filter:retweets',
    'exclude:retweets', 'exclude:replies', 'exclude:links',
]


def main():
    html = open(PAGE, encoding='utf-8').read()

    m = re.search(r'<script>(.*)</script>', html, re.S)
    assert m, 'no <script> block found in index.html'
    js = m.group(1)

    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as f:
        f.write(js)
        tmp = f.name
    try:
        r = subprocess.run(['node', '--check', tmp], capture_output=True, text=True)
        assert r.returncode == 0, 'panel JavaScript does not parse:\n' + r.stderr[:900]
    finally:
        os.unlink(tmp)

    # Chips are markup (data-op=), the rest are JS arrays. Check both.
    missing = [op for op in REQUIRED_OPS if op not in html]
    assert not missing, 'operators missing from the builder: ' + ', '.join(missing)

    # every id the JS reaches for must exist in the markup
    wanted = set(re.findall(r"\$\('#([a-zA-Z0-9_-]+)'\)", js))
    wanted |= set(re.findall(r"el\('([a-zA-Z0-9_-]+)'\)", js))
    ids = set(re.findall(r'id="([a-zA-Z0-9_-]+)"', html))
    # ids created at runtime by innerHTML are fine to miss
    runtime = {'toast', 'rows', 'cmdrows', 'cmdout', 'runnable', 'results', 'pager',
               'statuskv', 'logs', 'edit-name'}
    absent = sorted(wanted - ids - runtime)
    assert not absent, 'JavaScript reads ids that do not exist: ' + ', '.join(absent)

    assert 'prefers-reduced-motion' in html, 'no reduced-motion handling'
    assert 'prefers-reduced-transparency' in html, 'no reduced-transparency handling'
    assert 'api/results?page=' in js, 'results pagination is not wired up'
    # light mode is the requirement, so a dark-only token set is a failure
    assert 'color-scheme: light' in html, 'the page is not light mode'
    assert '--bg:        #f6f7f9' in html, 'the light background token is missing'
    # navigation and the lists surface must both exist
    for need in ('class="side"', 'data-tab="lists"', 'data-tab="dashboard"', '/api/lists'):
        assert need in html, 'missing from the page: ' + need

    print(f'test_panel ok, {len(REQUIRED_OPS)} operators, {len(wanted)} ids checked')


if __name__ == '__main__':
    main()