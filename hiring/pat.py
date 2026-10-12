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

__all__ = ['pat', 'pat_any', 'pat_fts', 'fts_query', 'groups', 'selfcheck']


def groups(path):
    """Compile every pattern group in a JSON config, probe check included.

    The config is the one place a pattern can be typed by a person, so every
    pair goes through the same guard as a pattern in code: probe first, then
    regex, and the regex has to match the probe or this raises. A group holding
    plain words instead of patterns is returned as a list, because some of them
    are not regexes.

    Fails loudly on purpose. A missing or broken file means nothing in the search
    can run, and that has to be a message naming the group and the probe rather
    than an ImportError or, worse, an empty result.
    """
    import json

    def no_dupes(pairs):
        # json.load takes the last of two identical keys and says nothing. For a
        # hand-edited file that means a group of patterns vanishes silently.
        out = {}
        for k, v in pairs:
            if k in out:
                raise ValueError(f'{path}: the key {k!r} appears twice. The second copy '
                                 f'would win silently, so delete one.')
            out[k] = v
        return out

    try:
        with open(path, encoding='utf-8') as f:
            doc = json.load(f, object_pairs_hook=no_dupes)
    except FileNotFoundError:
        raise ValueError(
            f'{path} is missing. It holds every pattern the hiring search uses. '
            f'Restore it from git: git checkout -- hiring/patterns.json')
    except json.JSONDecodeError as e:
        raise ValueError(f'{path} is not valid JSON: {e}\n'
                         f'  a lone backslash is the usual cause. Write \\\\b, not \\b.')
    out = {}
    for name, entry in doc.get('groups', {}).items():
        if 'words' in entry:
            out[name] = entry['words']
            continue
        pairs = [(p, rx) for p, rx in entry.get('patterns', [])]
        if not pairs:
            raise ValueError(f'{path}: group {name} has no patterns')
        # Prove each pair on its own first. Handing the whole list to
        # pat_any_build reports the joined regex, which is 1000 characters of
        # noise when one of 77 lines is wrong, so the refusal has to name the
        # line that is wrong.
        for i, (probe, alt) in enumerate(pairs, 1):
            try:
                pat(probe, alt)
            except AssertionError as e:
                raise ValueError(f'{path}: group {name}, pattern {i} of {len(pairs)}.\n  {e}')
        out[name] = pat_any_build(pairs)
    if not out:
        raise ValueError(f'{path} has no groups')
    return out


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


def fts_query(text, label='query'):
    """Check search syntax that came from a config file, and return it unchanged.

    A saved query is typed by hand in searches.json or in the panel, so it needs
    the same guard as a pattern in code. FTS5 itself is the judge: it accepts
    quoted phrases, OR, AND, NOT and parentheses, and rejects everything else
    with an error. Asking SQLite is cheaper and more honest than a blocklist of
    forbidden characters.

    The probe is the first quoted phrase, or the first bare word. It is inserted
    into a throwaway FTS5 table and the query must find it, so a query that
    parses but matches nothing is still rejected.
    """
    import sqlite3
    body = (text or '').strip()
    if not body:
        raise ValueError(f'{label} is empty')
    quoted = re.findall(r'"([^"]+)"', body)
    probe = (quoted[0] if quoted else body.split()[0]).strip()
    if not probe:
        raise ValueError(f'{label} has no searchable term: {text!r}')
    con = sqlite3.connect(':memory:')
    try:
        con.execute('CREATE VIRTUAL TABLE t USING fts5(x)')
        con.execute('INSERT INTO t VALUES (?)', (probe,))
        try:
            rows = con.execute('SELECT count(*) FROM t WHERE t MATCH ?', (body,)).fetchone()[0]
        except sqlite3.OperationalError as e:
            raise ValueError(
                f'{label} is not search syntax FTS5 can parse: {e}\n  {body!r}\n'
                f'  use quoted phrases with OR, AND, NOT. No regex, no backslashes.'
            )
        if rows != 1:
            raise ValueError(
                f'{label} matched {rows} rows against a row that holds its own first '
                f'term.\n  {body!r}'
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

    # 5. fts_query guards a query typed into searches.json. Valid syntax comes
    #    back untouched, regex syntax is rejected because FTS5 rejects it, and a
    #    query that finds nothing raises instead of returning zero rows later.
    import sqlite3
    assert fts_query('"hiring" OR "open role"', 'ok') == '"hiring" OR "open role"'
    assert fts_query('hiring NOT layoff', 'ok')
    assert fts_query('(hiring OR "open role") NOT spammer', 'ok')
    for bad, why in (
        ('hiring OR \\bhiring\\b', 'regex syntax, FTS5 will not parse it'),
        (r'"hiring" OR \bhire\b', 'backslash in a saved query'),
        ('', 'empty query'),
        ('   ', 'blank query'),
    ):
        try:
            fts_query(bad, 'bad')
        except ValueError:
            pass
        else:
            raise AssertionError(f'fts_query accepted {bad!r}: {why}')
    # A NOT query is judged against a row holding only its first term, not the
    # excluded one, so 'hiring NOT layoff' above is accepted rather than looking
    # like a query that matched nothing.

    # 6. groups() is the door every pattern now comes through, so prove it holds
    #    the line: a good file compiles, a broken one is refused, a missing one
    #    says what to restore, and a lone backslash is called out by name.
    import json, os, tempfile
    with tempfile.TemporaryDirectory() as tmp:
        good = os.path.join(tmp, 'good.json')
        with open(good, 'w', encoding='utf-8') as f:
            json.dump({'groups': {
                'TEST': {'patterns': [["we're hiring", r"\bwe(?:'re|\s+are)\s+hiring\b"],
                                      ['3 open roles', r"\bopen\s+roles?\b"]]},
                'WORDS': {'words': ['engineer', 'designer']},
            }}, f)
        got = groups(good)
        assert got['TEST'].search("we're hiring two engineers"), 'groups lost a pattern'
        assert not got['TEST'].search('hiring is mentioned in passing only'), \
            'groups matched text its own probe does not cover'
        assert got['WORDS'] == ['engineer', 'designer'], 'groups lost a word list'

        bad = os.path.join(tmp, 'bad.json')
        with open(bad, 'w', encoding='utf-8') as f:
            json.dump({'groups': {'TEST': {'patterns': [['we are hiring', r"\bjoinourteam\b"]]}}}, f)
        try:
            groups(bad)
        except ValueError as e:
            assert 'TEST' in str(e), 'the refusal must name the broken group'
        else:
            raise AssertionError('groups accepted a pattern that misses its probe')

        # A probe that is right and a pattern that is wrong is the real mistake,
        # and it must not compile.
        swapped = os.path.join(tmp, 'swapped.json')
        with open(swapped, 'w', encoding='utf-8') as f:
            json.dump({'groups': {'TEST': {'patterns': [['join our team', r"\bopenhiring\b"]]}}}, f)
        try:
            groups(swapped)
        except ValueError:
            pass
        else:
            raise AssertionError('groups accepted a pattern that cannot match its probe')

        try:
            groups(os.path.join(tmp, 'nothing-here.json'))
        except ValueError as e:
            assert 'git checkout' in str(e), 'a missing file must say how to restore it'
        else:
            raise AssertionError('groups accepted a missing file')

        # The backslash trap: "\b" in JSON is a backspace, not a word boundary.
        # It loads, compiles, and matches nothing, so the probe is what catches it.
        trap = os.path.join(tmp, 'trap.json')
        with open(trap, 'w', encoding='utf-8') as f:
            f.write('{"groups": {"TEST": {"patterns": [["hiring", "\\bhiring\\b"]]}}}')
        try:
            groups(trap)
        except ValueError:
            pass
        else:
            raise AssertionError('groups accepted a JSON backspace in place of \\b')

        broken = os.path.join(tmp, 'broken.json')
        with open(broken, 'w', encoding='utf-8') as f:
            f.write('{"groups": {"TEST": {"patterns": [["hiring", "\\d+"]]}}}')
        try:
            groups(broken)
        except ValueError as e:
            assert 'backslash' in str(e).lower(), 'an invalid escape must say so'
        else:
            raise AssertionError('groups accepted invalid JSON escapes silently')

        # Two groups with one name: json would keep the second and drop the first,
        # which is a whole set of patterns lost without a word.
        dupe = os.path.join(tmp, 'dupe.json')
        with open(dupe, 'w', encoding='utf-8') as f:
            f.write('{"groups": {"T": {"patterns": [["x", "x"]]}, "T": {"patterns": [["y", "y"]]}}}')
        try:
            groups(dupe)
        except ValueError as e:
            assert 'twice' in str(e), 'a duplicated key must be named as one'
        else:
            raise AssertionError('groups accepted a group name that appears twice')

        # A refusal must name the line that is wrong, not print the joined regex.
        numbered = os.path.join(tmp, 'numbered.json')
        with open(numbered, 'w', encoding='utf-8') as f:
            json.dump({'groups': {'TEST': {'patterns': [['hiring', r"\bhiring\b"],
                                                     ['later', r"\bnope\b"]]}}}, f)
        try:
            groups(numbered)
        except ValueError as e:
            assert 'pattern 2 of 2' in str(e), f'the refusal must name the line: {e}'
        else:
            raise AssertionError('groups accepted a broken second pattern')

    return 'selfcheck ok'


if __name__ == '__main__':
    print(selfcheck())
