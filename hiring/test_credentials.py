"""Prove the credential write path is correct, using a temp file, never the real .env.

    python test_credentials.py

Why this exists. On 2026-10-10 a manual test POSTed to /api/env while serve.py
had the real .env path hardcoded. The backup command had a wrong path, so it
silently did nothing, and the live auth_token was overwritten with a test string.
The user had to re-supply it. The fix is FT_ENV_FILE plus this check, so the same
test can no longer reach the real credentials.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

REAL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
FAKE = os.environ.get('FT_ENV_FILE')


def main():
    assert not FAKE, 'FT_ENV_FILE is already set, refusing to run: this test writes'

    with open(REAL, encoding='utf-8') as f:
        real_before = f.read()

    tmp = tempfile.NamedTemporaryFile('w', suffix='.env', delete=False, encoding='utf-8')
    tmp.write('# a comment line that must survive\n'
              'TWITTER_AUTH_TOKEN=old-token-value\n'
              'SOMETHING_ELSE=keep me\n')
    tmp.close()
    os.environ['FT_ENV_FILE'] = tmp.name

    try:
        import serve
        assert serve.env_path() == tmp.name, 'FT_ENV_FILE did not redirect the path'

        # write_env must replace in place and keep comments and unknown keys
        serve.write_env(serve.env_path(), {'TWITTER_AUTH_TOKEN': 'new-token-value'})
        got = serve.read_env(serve.env_path())
        assert got['TWITTER_AUTH_TOKEN'] == 'new-token-value', 'token was not replaced'
        assert got['SOMETHING_ELSE'] == 'keep me', 'an unrelated key was lost'
        body = open(tmp.name, encoding='utf-8').read()
        assert '# a comment line that must survive' in body, 'a comment was lost'

        # a key that was not there gets appended
        serve.write_env(serve.env_path(), {'TWITTER_CT0': 'ct0-value'})
        got = serve.read_env(serve.env_path())
        assert got['TWITTER_CT0'] == 'ct0-value', 'a missing key was not added'

        with open(REAL, encoding='utf-8') as f:
            assert f.read() == real_before, 'THE REAL .env CHANGED. This test is broken.'
    finally:
        os.environ.pop('FT_ENV_FILE', None)
        os.unlink(tmp.name)

    print('test_credentials ok, real .env untouched')


if __name__ == '__main__':
    main()