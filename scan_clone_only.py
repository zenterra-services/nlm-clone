#!/usr/bin/env python3
"""Check a single account's notebooks for block-page sources.

    python scan_clone_only.py <profile> [title-prefix]

Use when the original notebook no longer exists, so the original-vs-clone
comparison in scan_blocked.py cannot run. Without an original to compare
against, a source titled "Just a moment..." might genuinely have been that way
before — this reports candidates, not proven losses.
"""
import sys

from nlmutil import looks_blocked, notebooks, sources


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    profile = sys.argv[1]
    prefix = sys.argv[2] if len(sys.argv) > 2 else ""

    nbs = [n for n in notebooks(profile) if n["title"].startswith(prefix)]
    if not nbs:
        sys.exit(f"No notebooks in '{profile}' matching prefix {prefix!r}.")

    total = 0
    for n in sorted(nbs, key=lambda x: x["title"]):
        ss = sources(n["id"], profile, strict=False)
        if ss is None:
            print(f"{n['title'][:55]:<55} READ FAILED")
            continue
        hits = [s for s in ss if looks_blocked(s.get("title"))]
        total += len(hits)
        print(f"{n['title'][:55]:<55} {len(hits)} blocked of {len(ss)}")
        for s in hits:
            print(f"     ! {s['title'][:60]}  {(s.get('url') or '-')[:60]}")
    print(f"\n{total} block-page sources found")


if __name__ == "__main__":
    main()
