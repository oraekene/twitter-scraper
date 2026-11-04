import json

seen = json.load(open(r"C:\Users\rotim\.fieldtheory\bookmarks\bookmarks-backfill-state.json"))["lastSeenIds"]
want = set(seen)
path = r"C:\Users\rotim\.fieldtheory\bookmarks\bookmarks.jsonl"
pos = {}
prev_posted = None
inversions = 0
for i, line in enumerate(open(path, encoding="utf-8")):
    if i < 6000:
        r = json.loads(line)
        if prev_posted and r["postedAt"] > prev_posted:
            inversions += 1
        prev_posted = r["postedAt"]
    tid = json.loads(line)["tweetId"] if False else None
for i, line in enumerate(open(path, encoding="utf-8")):
    tid = json.loads(line)["tweetId"]
    if tid in want and tid not in pos:
        pos[tid] = i
    if len(pos) == len(want):
        break
print("inversions in first 6000 postedAt:", inversions)
print("positions of the 20 last-seen ids:", sorted(pos.values()))
