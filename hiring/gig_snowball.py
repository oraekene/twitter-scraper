"""Snowball the paid-AI-gig vocabulary out of the bookmark database.

    python gig_snowball.py                     # 3 rounds, writes out\\gig-terms.md
    python gig_snowball.py --rounds 5 --min-relevance 0.5
    python gig_snowball.py --selftest          # check the harvester, no database

Why a snowball instead of a word list. A hand-written list only finds the
tweets its author already imagined, which is how the known gig roundups stayed
invisible. This starts from the platforms and phrases in one gig tweet, finds
every bookmark holding one of them, harvests the words in what it found, and
repeats. Every round can only widen the vocabulary.

What keeps it on subject, and why the first version drifted. Ranking by "lift",
the share of a set holding a term against the share of the archive, rewards a
term that appears only inside the set with `df / set size * archive size`, so
`data annotation` scored 1,661 and `quantization` outranked `mercor`. Lift is
therefore gone.

A term is followed now when two things hold, and neither is a blocklist:

- it appears in at least two tweets that look like a gig ad, and
- it appears in no more than `max_df` tweets overall.

The anchor is the classifier's own definition, reused from patterns.json: GIG
or GIG_RATE, which is a rate per hour, week, study or task, or gig wording such
as "expert knowledge". That first gate removes a topic: `quantization` is
discussed in many tweets that never quote a rate, so it has almost no anchored
tweets and is dropped. The second gate removes a generic word: `hour`, `pay`
and `expert` do sit beside rates, but they sit beside them in hundreds of
tweets, which is not what a platform name looks like. `mercor`, `turing` and
`mindrift` pass both and are followed. A seed is held to the same rule, so a
bad one removes itself.
"""
import argparse
import os
import re
import sqlite3
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), 'out')
DB = os.path.expandvars(r'%USERPROFILE%\.fieldtheory\bookmarks\bookmarks.db')

# The platforms and phrases one known gig tweet and one known gig roundup name.
SEEDS = [
    'mercor', 'ethos', 'dataannotation', 'alignerr', 'prolific', 'appen',
    'oneforma', 'labelbox', 'innodata', 'clickworker', 'welocalize',
    'objectways', 'rws', 'telus', 'outlier', 'toloka', 'remotasks', 'turing',
    'expert knowledge', 'per hour', 'per study', 'annotation', 'annotator',
    'data labeling',
]

# Words that never name a kind of work, so a candidate token is noise. The
# anchor does the real filtering; this only stops the token list filling with
# grammar. 'per' is deliberately absent: "per hour" is a gig phrase.
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
llc inc ltd free join link links comment comments thread follow following
check dm pm info update updates post posted share shared read list lists
""".split())

_URL = re.compile(r'https?://\S+|\bt\.co/\S+|\bx\.com/\S+')
_MENTION = re.compile(r'@\w+')
_WORD = re.compile(r"[a-z][a-z0-9']{1,}")


def anchor():
    """The classifier's own gig definition, from patterns.json.

    Imported rather than retyped, so a change to what the search calls a gig
    changes what the snowball treats as relevant. That is the whole point: the
    harvester cannot drift away from the thing it is meant to feed.
    """
    sys.path.insert(0, HERE)
    from pat import groups
    g = groups(os.path.join(HERE, 'patterns.json'))
    return re.compile(f'(?:{g["GIG"].pattern})|(?:{g["GIG_RATE"].pattern})', re.I)


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


def pool_stats(rows, anchors, terms):
    """Tweets holding each term, and how many of those look like a gig ad.

    One pass for every pending term. Tokenising each tweet once and intersecting
    with the term set is what makes this cheap enough to run per round.
    """
    everywhere, anchored = Counter(), Counter()
    pending = set(terms)
    for i, (_, text) in enumerate(rows):
        for c in candidates(text) & pending:
            everywhere[c] += 1
            if anchors[i]:
                anchored[c] += 1
    return everywhere, anchored


def snowball(rows, seeds, rounds=3, min_df=4, max_df=50, width=40,
             min_anchored=2, anchor_rx=None):
    """Widen the term set `rounds` times, keeping only gig-relevant terms.

    A term is followed when it appears in at least `min_df` tweets of the set
    found so far, in at least `min_anchored` tweets that look like a gig ad, and
    in no more than `max_df` tweets overall. A seed is held to the same rule, so
    a bad seed removes itself before it can widen anything.

    Returns (terms, followed_by_round). `terms` maps a term to its tweet count,
    its anchored count, its relevance and the round it was found in, plus a
    `reason` for a term that was measured and not followed.
    """
    rx = anchor_rx or anchor()
    anchors = [bool(rx.search(text)) for _, text in rows]
    everywhere, anchored = pool_stats(rows, anchors, seeds)

    terms, known, frontier, hit = {}, set(seeds), [], set()
    for s in sorted(seeds):
        d, a = everywhere[s], anchored[s]
        terms[s] = {'df': d, 'anchored': a, 'relevance': round(a / d, 2) if d else 0.0,
                    'round': 0}
        if not d:
            terms[s]['reason'] = 'nothing in the archive'
        elif d > max_df:
            terms[s]['reason'] = 'in too many tweets to be a name'
        elif a < min(min_anchored, d):
            terms[s]['reason'] = 'never beside a gig ad'
        else:
            frontier.append(s)

    followed_by_round = []
    for n in range(1, rounds + 1):
        found = []
        for term in frontier:
            p = pattern(term)
            for i, (_, text) in enumerate(rows):
                if i in hit:
                    continue
                if p.search(text.lower()):
                    hit.add(i)
                    found.append(i)
        followed_by_round.append(list(frontier))
        if not found:
            break

        inside = Counter()
        for i in found:
            for c in candidates(rows[i][1]):
                if c not in known:
                    inside[c] += 1
        pool = [c for c, k in inside.items() if k >= min_df]
        if not pool:
            break

        everywhere, anchored = pool_stats(rows, anchors, pool)
        scored = []
        for c in pool:
            d, a = everywhere[c], anchored[c]
            rel = a / d if d else 0.0
            entry = {'df': d, 'anchored': a, 'relevance': round(rel, 2),
                     'round': n, 'inside': inside[c]}
            if d > max_df:
                entry['reason'] = 'in too many tweets to be a name'
            elif a < min(min_anchored, d):
                entry['reason'] = 'never beside a gig ad'
            if 'reason' in entry:
                terms.setdefault(c, entry)
                known.add(c)
                continue
            scored.append((a, rel, d, c, entry))

        # Most anchored tweets first: a term that keeps company with gig ads
        # beats one that merely appeared once. The cutoff is a wide net, not a
        # judgement, and everything past it stays visible in the report.
        scored.sort(key=lambda s: (-s[0], -s[1], s[2]))
        frontier = []
        for a, rel, d, c, entry in scored[:width]:
            known.add(c)
            terms.setdefault(c, entry)
            frontier.append(c)
        for a, rel, d, c, entry in scored[width:]:
            known.add(c)
            entry['reason'] = 'below the follow cutoff'
            terms.setdefault(c, entry)
        if not frontier:
            break
    return terms, followed_by_round


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--db', default=DB)
    ap.add_argument('--rounds', type=int, default=3)
    ap.add_argument('--min-df', type=int, default=4)
    ap.add_argument('--max-df', type=int, default=50,
                    help='more tweets than this and the term is a common word, not a name')
    ap.add_argument('--min-anchored', type=int, default=2,
                    help='tweets that look like a gig ad the term must appear in')
    ap.add_argument('--out', default=os.path.join(OUT, 'gig-terms.md'))
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    rows = load_rows(args.db)
    terms, rounds_run = snowball(rows, SEEDS, args.rounds, args.min_df,
                                 args.max_df, min_anchored=args.min_anchored)
    kept = {t: v for t, v in terms.items() if 'reason' not in v}
    took = {t: v for t, v in terms.items() if 'reason' in v}

    lines = ['# Paid AI gig vocabulary, by snowball', '',
             f'Scanned {len(rows):,} bookmarks in {args.db}.',
             f'{args.rounds} rounds, at least {args.min_df} tweets inside the set, '
             f'at least {args.min_anchored} beside a gig ad, at most {args.max_df} '
             f'tweets overall, {len(SEEDS)} seeds.', '',
             'A gig ad is judged by the GIG and GIG_RATE groups in patterns.json.',
             'Relevance below is the share of a term\'s tweets that are gig ads. It',
             'is shown for reading, not used as the gate: a platform name that is',
             'often mentioned without a rate would fail a ratio while a common word',
             'like "pay" would pass one.', '',
             '## Followed', '', '| Term | Gig ads | Tweets | Relevance | Round |',
             '|---|---|---|---|---|']
    for term, info in sorted(kept.items(), key=lambda kv: (-kv[1]['anchored'],
                                                           -kv[1]['relevance'],
                                                           kv[1]['df'])):
        lines.append(f'| {term} | {info["anchored"]} | {info["df"]} | '
                     f'{info["relevance"]} | {info["round"]} |')

    lines += ['', '## Measured and not followed', '',
              '| Term | Gig ads | Tweets | Relevance | Round | Why |',
              '|---|---|---|---|---|---|']
    for term, info in sorted(took.items(), key=lambda kv: (-kv[1]['anchored'],
                                                           -kv[1]['relevance'],
                                                           kv[1]['df'])):
        lines.append(f'| {term} | {info["anchored"]} | {info["df"]} | '
                     f'{info["relevance"]} | {info["round"]} | {info["reason"]} |')

    lines += ['', '## Rounds', '']
    for i, group in enumerate(rounds_run, 1):
        lines.append(f'- round {i}: {len(group)} term(s) followed')
    lines += ['', '## Seeds', '',
              '| Term | Gig ads | Tweets | Relevance | Followed |',
              '|---|---|---|---|---|']
    for s in SEEDS:
        info = terms[s]
        lines.append(f'| {s} | {info["anchored"]} | {info["df"]} | '
                     f'{info["relevance"]} | '
                     f'{"no: " + info["reason"] if "reason" in info else "yes"} |')

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print(f'{len(kept)} term(s) followed, {len(took)} measured and dropped, '
          f'wrote {args.out}')
    return 0


def selftest():
    """Prove the harvester widens and that relevance does the filtering."""
    bad = 0

    def check(label, got, want):
        nonlocal bad
        ok = got == want
        bad += 0 if ok else 1
        print(f"  {'ok ' if ok else 'BAD'} {label}: want {want!r}, got {got!r}")

    check('bigram kept', 'per hour' in candidates('we pay experts per hour'), True)
    check('stopword dropped', 'the' in candidates('the work is the same'), False)
    check('url dropped', any('t.co' in c for c in candidates('see https://t.co/abc')), False)
    check('mention stripped', 'mercor' in candidates('@mercor pays'), False)

    # The anchor is the classifier's own group. "per hour" is a gig phrase and
    # "quantization" is not, which is the whole filter in two assertions.
    rx = anchor()
    check('rate anchors', bool(rx.search('we pay $25 per hour')), True)
    check('topic does not anchor', bool(rx.search('quantization improves throughput')), False)

    rows = [
        ('1', 'mercor pays $40 per hour for annotation, throughput matters'),
        ('2', 'annotation work on mercor, paid per task, throughput'),
        ('3', 'mercor pays $50 per hour for experts'),
        ('4', 'annotation at labelbox, paid per hour'),
        ('5', 'annotation at labelbox, rate per hour'),
        ('6', 'throughput on gpus'),
        ('7', 'throughput on gpus'),
        ('8', 'throughput on gpus'),
        ('9', 'career advice for engineers'),
        ('10', 'career advice for engineers'),
        ('11', 'career advice for engineers'),
        ('12', 'career advice for engineers'),
    ]
    terms, _ = snowball(rows, ['mercor', 'career'], rounds=2, min_df=2,
                        min_anchored=3, anchor_rx=rx)
    check('gig term followed', terms['labelbox'].get('reason'), None)
    check('gig seed followed', terms['mercor'].get('reason'), None)
    check('topic seed dropped', terms['career'].get('reason'), 'never beside a gig ad')
    check('topic term dropped', terms['throughput'].get('reason'), 'never beside a gig ad')

    # A word that sits beside rates in many tweets is a common word, not a name.
    common = [(str(i), 'mercor pays per hour') for i in range(1, 7)]
    terms2, _ = snowball(common, ['mercor'], rounds=1, min_df=1, max_df=5,
                         min_anchored=1, anchor_rx=rx)
    check('common word dropped', terms2['mercor'].get('reason'),
          'in too many tweets to be a name')

    print(f'selftest: {12 - bad}/12 passed')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
