import os

roots = [
    r"C:\Users\rotim\.fieldtheory",
    r"C:\Users\rotim\Documents\twitter scraper",
    r"C:\Users\rotim\Documents\twitter-cli",
    r"C:\Users\rotim\.twitter-cli",
    r"C:\Users\rotim\Documents\fieldtheory",
]
for root in roots:
    if not os.path.isdir(root):
        continue
    for r, ds, fs in os.walk(root):
        ds[:] = [d for d in ds if d not in ('.git', 'node_modules', 'venv', '.venv')]
        for f in fs:
            if f.endswith(('.py', '.ts', '.js', '.go', '.rs')):
                p = os.path.join(r, f)
                try:
                    t = open(p, encoding='utf-8', errors='ignore').read()
                except Exception:
                    continue
                if 'synced_at' in t and ('insert' in t.lower() or 'upsert' in t.lower() or 'sync_bookmarks' in t.lower()):
                    print(p)