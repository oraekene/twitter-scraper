import os, glob

hits = []
for base in [r"C:\Users\rotim\.local", r"C:\Users\rotim\AppData\Local\hermes"]:
    if not os.path.isdir(base):
        continue
    for root, ds, fs in os.walk(base):
        ds[:] = [d for d in ds if d not in ("node_modules", "venv", ".venv")]
        for f in fs:
            if f.endswith((".js", ".mjs", ".cjs", ".py")):
                p = os.path.join(root, f)
                try:
                    t = open(p, encoding="utf-8", errors="ignore").read()
                except Exception:
                    continue
                if "createdAtISO" in t and ("bookmark" in p.lower()):
                    hits.append(p)
for h in hits[:15]:
    print(h)
if not hits:
    print("none")