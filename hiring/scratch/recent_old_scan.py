import json, re

rows = json.load(open("hiring/scratch/recent_old.json", encoding="utf-8"))
PAT = re.compile(
    r"(hackathons?|hack ?sprints?|build ?athons?|scholarships?|bursar(y|ies)|fellowships?|"
    r"grants?|funding|fund(ed|s)?|accelerators?|incubators?|residency|cohorts?|prizes?|awards?|"
    r"competitions?|contests?|bount(y|ies)|stipends?|tuition|applications?|apply|applying|"
    r"deadline|submissions?|demo day|open calls?|challenges?|bootcamps?|credits|"
    r"program(me)?s?|fully funded|no equity|equity[- ]free)",
    re.I,
)
MONEY = re.compile(r"[$£€₦]\s?\d|\d+\s?[kK]\b|million", re.I)
CALL = re.compile(r"\b(apply|submit|enter|deadline|closes|ends|open to|applications|register)\b", re.I)

hits = [r for r in rows if PAT.search(r["text"] or "") or (MONEY.search(r["text"] or "") and CALL.search(r["text"] or ""))]
print("pool", len(rows), "hits", len(hits))
out = open("hiring/scratch/recent_old_hits.txt", "w", encoding="utf-8")
for r in hits:
    t = " ".join((r["text"] or "").split())
    out.write(f"{r['tweet_id']} @{r['author_handle']} {r['posted_at'][:16]}\n   {t[:400]}\n")
out.close()
json.dump(hits, open("hiring/scratch/recent_old_hits.json", "w", encoding="utf-8"), indent=1)
