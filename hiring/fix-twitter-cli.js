// Re-applies the twitter-cli search fix after `npm -g upgrade` or `uv tool upgrade`.
// Idempotent: safe to run any time, exits 0 if already patched.
//
//   node fix-twitter-cli.js
//
// Why. twitter-cli 0.8.5 builds the x-client-transaction-id header by fetching
// https://x.com and scraping the ondemand.s chunk out of the page. It fetches
// that page WITHOUT the auth cookies, so X serves the logged-out shell. The
// logged-out shell has no chunk manifest, so scraping returns None, so the
// transaction id is never generated, so the header is never sent.
//
// X now returns HTTP 404 for SearchTimeline without that header. Every endpoint
// the CLI uses for you (UserTweets, Bookmarks) keeps working, which is why the
// failure looks like "search is broken" rather than "auth is broken".
//
// Fix: put auth_token and ct0 on the session before fetching the homepage.
// Verified 2026-10-09: search returns tweets before and after this patch.

const fs = require('fs');
const path = require('path');
const os = require('os');

const TARGET = path.join(
    process.env.APPDATA || path.join(os.homedir(), '.config'),
    'uv', 'tools', 'twitter-cli', 'Lib', 'site-packages',
    'twitter_cli', 'client.py'
);

const ANCHOR = '            cffi_session = _get_cffi_session()\n            ct_headers = _gen_ct_headers()\n';
const PATCHED = ANCHOR +
    '            # PATCHED: logged-out HTML has no ondemand manifest, so no txn id, so search 404s\n' +
    '            for _n, _v in (("auth_token", self._auth_token), ("ct0", self._ct0)):\n' +
    '                if _v:\n' +
    '                    cffi_session.cookies.set(_n, _v, domain=".x.com")\n';

if (!fs.existsSync(TARGET)) {
    console.error('not found: ' + TARGET);
    process.exit(1);
}

const src = fs.readFileSync(TARGET, 'utf8');

if (src.includes('PATCHED: logged-out HTML has no ondemand manifest')) {
    console.log('already patched');
    process.exit(0);
}
if (!src.includes(ANCHOR)) {
    console.error('_ensure_client_transaction does not look the way this patch expects.');
    console.error('The package was probably rewritten upstream. Read it, then fix by hand:');
    console.error(TARGET);
    process.exit(2);
}

fs.writeFileSync(TARGET, src.replace(ANCHOR, PATCHED), 'utf8');
console.log('patched: ' + TARGET);
console.log('delete the cached transaction if it already failed:');
console.log('  del "%USERPROFILE%\\.twitter-cli\\transaction_cache.json"');
console.log('check it:  twitter search "hiring" -n 5 --json');