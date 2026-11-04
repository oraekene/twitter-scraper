import os

base = r"C:\Users\rotim\AppData\Local\hermes\node\node_modules\fieldtheory\dist"
hits = []
for root, ds, fs in os.walk(base):
    ds[:] = [d for d in ds if d not in ("node_modules",)]
    for f in fs:
        if f.endswith((".js", ".mjs", ".cjs")):
            p = os.path.join(root, f)
            try:
                t = open(p, encoding="utf-8", errors="ignore").read()
            except Exception:
                continue
            if "synced_at" in t and ("INSERT" in t or "VALUES" in t or "run(" in t):
                hits.append(p)
for h in hits:
    print(h)
if not hits:
    print("none")