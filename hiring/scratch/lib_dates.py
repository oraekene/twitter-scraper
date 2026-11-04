import os, collections
from datetime import datetime

root = r"C:\Users\rotim\.fieldtheory\library"
counts = collections.Counter()
n = 0
for dirpath, _, files in os.walk(root):
    for f in files:
        st = os.stat(os.path.join(dirpath, f))
        counts[datetime.fromtimestamp(st.st_ctime).strftime("%Y-%m-%d")] += 1
        n += 1
print("files", n)
for d, c in sorted(counts.items(), reverse=True)[:12]:
    print(d, c)
