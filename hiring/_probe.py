"""Probe each configured provider once and report latency plus error."""
import time

import research

for name, base, key, model in research.providers():
    t0 = time.time()
    text, err = research._ScanRoot([(name, base, key, model)],
                                   root=research._ROOT).ask(
        "Reply with the single word ok", max_tokens=8)
    took = time.time() - t0
    print(f"{name:16} {took:6.1f}s  {(text or '')[:40]!r}  {err or ''}")
