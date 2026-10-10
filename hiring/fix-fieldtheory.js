// Re-applies the fieldtheory search fix after `npm update -g fieldtheory`.
// Idempotent: safe to run any time, exits 0 if already patched.
//
//   node fix-fieldtheory.js
//
// Why. fieldtheory 1.3.22 sanitizeFtsQuery() double-quotes EVERY token as soon
// as it sees one FTS5 operator, so the word OR becomes a literal word to match.
// Proof on this machine:
//   fieldtheory search "hiring OR hire"            -> 290 results (tweets containing the word "OR")
//   same query straight against bookmarks.db        -> 1259 results (correct)
//
// Fix: leave AND / OR / NOT / NEAR unquoted so FTS5 treats them as operators.

const fs = require('fs');
const path = require('path');

const TARGET = path.join(
    process.env.LOCALAPPDATA || process.env.HOME,
    'hermes', 'node', 'node_modules', 'fieldtheory', 'dist', 'bookmarks-db.js'
);

const BROKEN = `.map((term) => \`"\${term.replace(/"/g, '')}"\`)`;
const FIXED = `.map((term) => /^(AND|OR|NOT|NEAR)$/i.test(term) ? term : \`"\${term.replace(/"/g, '')}"\`)`;

if (!fs.existsSync(TARGET)) {
    console.error('not found: ' + TARGET);
    process.exit(1);
}

const src = fs.readFileSync(TARGET, 'utf8');

if (src.includes(FIXED)) {
    console.log('already patched');
    process.exit(0);
}
if (!src.includes(BROKEN)) {
    console.error('sanitizeFtsQuery does not look the way this patch expects.');
    console.error('The package was probably rewritten upstream. Read it, then fix by hand:');
    console.error(TARGET);
    process.exit(2);
}

fs.writeFileSync(TARGET, src.replace(BROKEN, FIXED), 'utf8');
console.log('patched: ' + TARGET);
console.log('check it:  fieldtheory search "hiring OR hire" --limit 5000 --json');
