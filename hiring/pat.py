r"""Regex helper that cannot be committed broken.

Every pattern is checked against a probe string at build time. If the pattern
does not match the probe, this raises immediately instead of silently returning
zero rows.

    HIRING = pat("we're hiring two engineers", r"\bhiring\b", r"\bhire\b")

Why this exists. On 2026-10-09 a search run returned garbage because patterns
were written with Python's verbose flag, re.X. Verbose mode deletes literal
spaces from the pattern for readability, so "join our team" was compiled as
"joinourteam" and matched nothing. No error, zero results, hours wasted.

Run the self check with: python pat.py
"""

import re

__all__ = ['pat', 'pat_any', 'pat_fts', 'selfcheck']


def _build(alts, flags, group='(?:'):
    if not alts:
        raise ValueError('pat() needs at least one alternative')
    for a in alts:
        if not a:
            raise ValueError('pat() got an empty alternative')
    return re.compile('|'.join(f'{group}{a})' for a in alts), flags)


def pat(probe, *alts, flags=re.I, group='(?:'):
    """Regex from phrase alternatives, verified against probe.

    probe must be a real string the pattern is meant to match. It is a required
    argument on purpose, so a pattern cannot be written without a test.

    group='(' emits plain groups instead of non-capturing ones. SQLite FTS5
    rejects the (?: form, so a pattern bound to a MATCH query needs group='('.
    Use pat_fts for that.
    """
    rx = _build(alts, flags, group)
    if not rx.search(probe):
        raise AssertionError(
            f'pattern does not match its own probe.\n  probe: {probe!r}\n'
            f'  pattern: {rx.pattern!r}\n'
            f'  flags: {flags}\n'
            f'  cause: a literal space is being eaten by re.X, or a word is misspelled.'
        )
    return rx


def pat_fts(probe, *phrases, flags=re.I):
    """Build a pattern for `bookmarks_fts MATCH ?`, verified against probe.

    SQLite FTS5 is not a regex engine. It accepts bare words, "quoted phrases",
    OR / AND / NOT / NEAR, a trailing * for prefix, and column:term. It rejects
    \\b, (?:, and every other regex metacharacter. So this takes plain phrases
    and quotes them, which is all a recall query needs.

    probe is checked twice: once as plain text, then again by running the built
    pattern against a real FTS5 table holding probe. That second check is what
    catches metacharacters FTS5 will not parse.
    """
    import sqlite3
    if not phrases:
        raise ValueError('pat_fts() needs at least one phrase')
    for p in phrases:
        if re.search(r'[\\^$(){}[\]+?|]', p):
            raise ValueError(
                f'pat_fts() got regex syntax, FTS5 will not parse it: {p!r}. '
                f'Pass plain words, FTS5 quotes them for you.'
            )

    hit = False
    for p in phrases:
        rx = re.compile(r'\b' + r'[\s/]+'.join(re.escape(w) for w in p.split()) + r'\b', flags)
        if rx.search(probe):
            hit = True
            break
    if not hit:
        raise AssertionError(
            f'none of the phrases match their own probe.\n  probe: {probe!r}\n  phrases: {phrases!r}'
        )

    # FTS5 spells OR as a keyword. It has no | operator.
    body = ' OR '.join(f'"{p}"' for p in phrases)
    con = sqlite3.connect(':memory:')
    try:
        con.execute('CREATE VIRTUAL TABLE t USING fts5(x)')
        con.execute('INSERT INTO t VALUES (?)', (probe,))
        try:
            rows = con.execute('SELECT count(*) FROM t WHERE t MATCH ?', (body,)).fetchone()[0]
        except sqlite3.OperationalError as e:
            raise AssertionError(f'FTS5 rejected the built pattern: {e}\n  {body!r}')
        if rows != 1:
            raise AssertionError(
                f'pattern matched {rows} rows against a probe that contains it.\n'
                f'  probe: {probe!r}\n  fts: {body!r}'
            )
    finally:
        con.close()
    return body


def pat_any(*probes_and_alts, flags=re.I, group='(?:'):
    r"""Build from alternating probe, alternative, probe, alternative.

    For patterns with several independent cases worth proving:
        OPEN = pat_any(
            "we're hiring engineers", r"\bhiring\b",
            "join our team",       r"\bjoin\s+our\s+team\b",
        )
    """
    if len(probes_and_alts) % 2:
        raise ValueError('pat_any() needs alternating probe and alternative')
    probes, alts = probes_and_alts[::2], probes_and_alts[1::2]
    return pat_any_build(list(zip(probes, alts)), flags, group)


def pat_any_build(pairs, flags=re.I, group='(?:'):
    alts = [a for _, a in pairs]
    rx = _build(alts, flags, group)
    for probe, _ in pairs:
        if not rx.search(probe):
            raise AssertionError(
                f'pattern does not match its own probe.\n  probe: {probe!r}\n'
                f'  pattern: {rx.pattern!r}'
            )
    return rx


def selfcheck():
    """Proves the guard works. Fails loudly if it ever stops working."""
    # 1. A good pattern is accepted.
    pat("we're hiring two engineers", r"\bhiring\b", r"\bhires\b")

    # 2. A pattern with a swallowed space is rejected. This is the exact bug
    #    from 2026-10-09, reproduced here so a regression cannot pass.
    for bad, why in (
        (lambda: pat("join our team", r"\bjoin our team\b", flags=re.I | re.X),
         're.X ate the spaces'),
        (lambda: pat("we are hiring", r"\bhire\b"),
         'word misspelled, pattern matches something else'),
    ):
        try:
            bad()
        except AssertionError:
            pass
        else:
            raise AssertionError(f'guard failed to catch: {why}')

    # 3. pat_any proves several cases at once.
    pat_any(
        "we're hiring engineers", r"\bhiring\b",
        "join our team", r"\bjoin\s+our\s+team\b",
        "3 open roles", r"\bopen\s+roles?\b",
    )

    # 3b. pat_fts emits FTS5-safe quoted phrases. Regex syntax is rejected by
    #     both this guard and FTS5 itself, which is how it was found today.
    import sqlite3
    con = sqlite3.connect(':memory:')
    try:
        fts = pat_fts('we are hiring two engineers today', 'we are hiring', 'now hiring')
        con.execute('CREATE VIRTUAL TABLE t USING fts5(x)')
        con.execute("INSERT INTO t VALUES ('we are hiring two engineers today')")
        assert con.execute('SELECT count(*) FROM t WHERE t MATCH ?', (fts,)).fetchone()[0] == 1
    finally:
        con.close()
    try:
        pat_fts('we are hiring', r'\bhiring\b')
    except ValueError:
        pass
    else:
        raise AssertionError('pat_fts accepted regex syntax that FTS5 cannot parse')

    # 4. A deliberately wrong probe is still rejected, so a lazy probe
    #    cannot be slipped in by copying.
    try:
        pat("this sentence has no openings in it", r"\bhiring\b")
    except AssertionError:
        pass
    else:
        raise AssertionError('guard accepted a pattern that misses its probe')

    return 'selfcheck ok'


if __name__ == '__main__':
    print(selfcheck())
