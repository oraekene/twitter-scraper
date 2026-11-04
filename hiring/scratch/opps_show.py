import json, sys

rows = json.load(open("hiring/scratch/opps_raw.json", encoding="utf-8"))
out = open("hiring/scratch/opps_raw.txt", "w", encoding="utf-8")
for i, r in enumerate(rows):
    t = " ".join((r["text"] or "").split())
    out.write(f"[{i}] {r['date']} @{r['handle']} {r['url']}\n    {t[:450]}\n")
    if r["quoted"]:
        out.write("   Q: " + " ".join(r["quoted"].split())[:300] + "\n")
    if r["links"]:
        out.write("   L: " + str(r["links"][:3]) + "\n")
out.close()
print("wrote", len(rows))
