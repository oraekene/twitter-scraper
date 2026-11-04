"""Snowball the paid-AI-gig vocabulary out of the bookmark database.

    python gig_snowball.py                     # 3 rounds, writes out\\gig-terms.md
    python gig_snowball.py --rounds 5 --min-df 3
    python gig_snowball.py --selftest          # check the harvester, no database

Why a snowball instead of a word list. A hand-written list only finds the
tweets its author already imagined, which is how the two known gig roundups
stayed invisible for months. This starts from the platforms and phrases in
those tweets, finds every bookmark holding one of them, harvests the words in
what it found, and repeats. Every round can only widen the vocabulary, and the
report prints how many tweets each term reaches, so the GIG group in
patterns.json gets written from evidence instead of from a guess.

A term that matches more than `max_df` tweets is too broad to widen anything
("ai", "work", "people"), so it is reported but not followed.
"""
import argparse
import json
import os
import re
import sqlite3
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), 'out')
DB = os.path.expandvars(r'%USERPROFILE%\.fieldtheory\bookmarks\bookmarks.db')

# The two roundup tweets this started from, plus the platforms they name and
# the phrases the whole class is advertised with.
SEEDS = [
    'mercor', 'ethos', 'dataannotation', 'alignerr', 'prolific', 'appen',
    'oneforma', 'labelbox', 'innodata', 'clickworker', 'welocalize',
    'objectways', 'rws', 'telus', 'outlier', 'surge', 'snorkel', 'toloka',
    'remotasks', 'turing', 'expert knowledge', 'per hour', 'per study',
    'annotation', 'annotator', 'data labeling', 'ai training', 'rlhf',
]

# Words that never name a kind of work. 'per' is deliberately absent: "per hour"
# and "per study" are the two phrases the whole class is advertised with.
STOP = set("""
a an the and or but if then than that this these those it its it's i me my mine
you your yours he she they them their we us our ours is are was were be been
being am do does did doing have has had having will would shall should can
could may might must not no nor so as at by for from in into of off on onto
out over to up with within without about after before again all also any
because both each few more most other some such only own same too very just
now here there when where which who whom whose what how why while during
rt via amp https http tco co com www get got make makes made want wants need
needs new now one two three first last next day days week weeks month months
year years today yesterday tomorrow time times people person work works working
ai llc inc ltd free join link links comment comments thread follow following
check dm pm am pm info update updates post posted share shared read list lists
""".split())

_URL = re.compile(r'https?://\S+|\bt\.co/\S+|\bx\.com/\S+')
_MENTION = re.compile(r'@\w+')
_WORD = re.compile(r"[a-z][a-z0-9']{1,}")


def candidates(text):
    """Unigrams and bigrams worth measuring. Pure, so --selftest can prove it."""
    text = _MENTION.sub(' ', _URL.sub(' ', (text or '').lower()))
    words = _WORD.findall(text)
    out = set(words)
    for a, b in zip(words, words[1:]):
        if a not in STOP and b not in STOP:
            out.add(f'{a} {b}')
    return {w for w in out if w not in STOP}


def pattern(term):
    return re.compile(r'(?<![a-z0-9])' + re.escape(term) + r'(?![a-z0-9])')


def load_rows(db):
    con = sqlite3.connect(db)
    try:
        rows = con.execute(
            "SELECT tweet_id, text FROM bookmarks "
            "WHERE text IS NOT NULL AND length(text) > 20").fetchall()
    finally:
        con.close()
    return [(tid, text) for tid, text in rows]


def global_counts(rows, terms):
    """How many tweets hold each term, across the whole corpus.

    One pass for every pending term. A raw count is not enough to rank with:
    "like" appears in 10,000 tweets and "annotator" in 30, so the most common
    candidate is always the least useful one. The count is what turns a
    frequency into a lift, and the lift is what picks a term out of the noise.
    """
    counts = Counter()
    pending = set(terms)
    for _, text in rows:
        for c in candidates(text) & pending:
            counts[c] += 1
    return counts


def snowball(rows, seeds, rounds=3, min_df=4, max_df=2000, width=40, min_lift=2.0):
    """Widen the term set `rounds` times. Returns (terms, followed, skipped).

    `terms` maps a term to how many tweets hold it, its lift, and one example.
    A term is followed when at least `min_df` tweets in the matched set hold it
    and it is at least `min_lift` times as common inside that set as outside it,
    which is what keeps "like" out and "per hour" in.
    """
    known = {t.lower() for t in seeds}
    frontier = sorted(known)
    hit = set()
    terms, followed, skipped = {}, [], []
    for _ in range(rounds):
        found = []
        for term in frontier:
            rx = pattern(term)
            for i, (tid, text) in enumerate(rows):
                if i in hit:
                    continue
                if rx.search(text.lower()):
                    hit.add(i)
                    found.append(i)
                    terms.setdefault(term, {'df': 0, 'lift': None, 'example': tid})
                    terms[term]['df'] += 1
        if not found:
            break

        inside = Counter()
        for i in found:
            for c in candidates(rows[i][1]):
                if c not in known:
                    inside[c] += 1
        pool = [c for c, n in inside.items() if n >= min_df]
        if not pool:
            break

        everywhere = global_counts(rows, pool)
        outside_total = max(1, len(rows) - len(found))
        ranked = []
        for c in pool:
            if everywhere[c] > max_df:
                skipped.append((c, everywhere[c]))
                known.add(c)
                continue
            # Share of the tweets just found that hold the term, against the
            # share of the rest of the archive that holds it. A term that is
            # merely frequent scores about 1 on both sides and is dropped; a
            # term that lives here scores high.
            outside = everywhere[c] - inside[c]
            lift = (inside[c] / len(found)) / ((outside + 1) / outside_total)
            if lift >= min_lift:
                ranked.append((lift, inside[c], c))
        # Highest lift first: a term that lives inside this set rather than in
        # the whole archive. Ties go to the term that reaches more tweets.
        ranked.sort(key=lambda r: (-r[0], -r[1]))

        followed.append(list(frontier))
        frontier = []
        for lift, n, c in ranked[:width]:
            known.add(c)
            terms.setdefault(c, {'df': n, 'lift': round(lift, 2), 'example': None})
            frontier.append(c)
        if not frontier:
            break
    return terms, followed, skipped


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--db', default=DB)
    ap.add_argument('--rounds', type=int, default=3)
    ap.add_argument('--min-df', type=int, default=4)
    ap.add_argument('--max-df', type=int, default=2000)
    ap.add_argument('--min-lift', type=float, default=2.0)
    ap.add_argument('--out', default=os.path.join(OUT, 'gig-terms.md'))
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    rows = load_rows(args.db)
    terms, followed, skipped = snowball(rows, SEEDS, args.rounds, args.min_df,
                                        args.max_df, min_lift=args.min_lift)
    example = {tid: text for tid, text in rows}

    lines = ['# Paid AI gig vocabulary, by snowball', '',
             f'Scanned {len(rows):,} bookmarks in {args.db}.',
             f'{args.rounds} rounds, at least {args.min_df} tweets inside the set, '
             f'lift {args.min_lift} or more, {len(SEEDS)} seeds.', '',
             'Lift is how much more common a term is inside the tweets found so far',
             'than in the whole archive. A high lift is what makes a term specific',
             'to this subject rather than merely frequent.', '',
             '| Term | Tweets | Lift | Example |', '|---|---|---|---|']
    for term, info in sorted(terms.items(), key=lambda kv: -(kv[1]['lift'] or 0)):
        tid = info['example']
        snap = ''
        if tid and tid in example:
            snap = example[tid].replace('\n', ' ').replace('|', '/')[:90]
        lift = '-' if info['lift'] is None else info['lift']
        lines.append(f'| {term} | {info["df"]} | {lift} | {snap} |')
    if skipped:
        lines += ['', '## Too broad to follow', '',
                  '| Term | Tweets |', '|---|---|']
        lines += [f'| {t} | {n} |' for t, n in skipped]
    lines += ['', '## Rounds', '']
    for i, group in enumerate(followed, 1):
        lines.append(f'- round {i}: {len(group)} term(s) followed')
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print(f'{len(terms)} term(s) measured, {len(skipped)} too broad, wrote {args.out}')
    return 0


def selftest():
    """Prove the harvester widens, and that the noise filters hold."""
    bad = 0

    def check(label, got, want):
        nonlocal bad
        ok = got == want
        bad += 0 if ok else 1
        print(f"  {'ok ' if ok else 'BAD'} {label}: want {want!r}, got {got!r}")

    check('bigram kept', 'per hour' in candidates('we pay experts per hour'), True)
    check('stopword dropped', 'the' in candidates('the work is the same'), False)
    check('url dropped', any('t.co' in c for c in candidates('see https://t.co/abc')), False)
    # A handle is stripped, so "@mercor pays" harvests "pays" and not the name.
    # The raw text is still searched as-is, so a seed still matches a mention.
    check('mention stripped', 'mercor' in candidates('@mercor pays'), False)

    rows = [
        ('1', 'mercor pays experts per hour'),
        ('2', 'annotation work on mercor'),
        ('3', 'annotation tasks at labelbox'),
        ('4', 'mercor annotation for experts'),
        ('5', 'labelbox pays per hour for experts'),
        ('6', 'like every like people like'),
        ('7', 'like every like people like'),
        ('8', 'like every like people like'),
        ('9', 'like every like people like'),
        ('10', 'like every like people like'),
        ('11', 'like every like people like'),
        ('12', 'like every like people like'),
        ('13', 'like every like people like'),
        ('14', 'like every like people like'),
        ('15', 'like every like people like'),
        ('16', 'like every like people like'),
        ('17', 'like every like people like'),
        ('18', 'like every like people like'),
        ('19', 'like every like people like'),
        ('20', 'like every like people like'),
    ]
    terms, followed, _ = snowball(rows, ['mercor'], rounds=2, min_df=2)
    check('round 1 found the seed tweets', terms['mercor']['df'], 3)
    check('a specific term is followed', 'annotation' in terms, True)
    check('a merely frequent term is not', 'like' in terms, False)
    check('round 2 widened to a new platform', 'labelbox' in terms, True)

    # A harvested term that matches almost everything must not become a search
    # term, or the next round scans the whole archive and harvests noise.
    wide = [('1', 'mercor experts experts experts'),
            ('2', 'mercor experts experts experts'),
            ('3', 'mercor experts experts experts')]
    _, _, skipped = snowball(wide, ['mercor'], rounds=2, min_df=1, max_df=2)
    check('broad term not followed', any(t == 'experts' for t, _ in skipped), True)

    print(f'selftest: {9 - bad}/9 passed')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
