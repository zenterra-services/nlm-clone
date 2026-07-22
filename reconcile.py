#!/usr/bin/env python3
"""Reconcile a cloned notebook against its original, one-to-one.

    python reconcile.py <src-profile> <src-id> <dst-profile> <dst-id>

Matching is greedy, in priority order, because NotebookLM renames web sources
when it re-fetches them (a blocked fetch becomes "Just a moment...", so titles
are NOT stable) while URLs are:

    1. same URL          reliable for web sources
    2. same exact title  reliable for text/file sources, which have no URL

Unmatched clone sources are true extras; unmatched originals are genuinely
missing. Run this before deleting anything and require the books to balance:
    clone - extras + missing == original

Same-title sources are usually NOT duplicates: a notebook can legitimately
contain the same URL twice, and blocked re-fetches collapse many distinct
pages onto one title.
"""
import sys

from nlmutil import sources


def tkey(s):
    t = (s.get("title") or "").strip().lower()
    return t[:-4] if t.endswith(".txt") else t


def main():
    if len(sys.argv) != 5:
        sys.exit(__doc__)
    src_profile, src_id, dst_profile, dst_id = sys.argv[1:5]

    src = sources(src_id, src_profile)
    dst = sources(dst_id, dst_profile)
    print(f"original: {len(src)}    clone: {len(dst)}\n")

    unmatched_dst = list(dst)
    pass2 = []

    for s in src:  # pass 1: by URL
        if not s.get("url"):
            pass2.append(s)
            continue
        hit = next((d for d in unmatched_dst if d.get("url") == s["url"]), None)
        if hit:
            unmatched_dst.remove(hit)
        else:
            pass2.append(s)

    missing = []
    for s in pass2:  # pass 2: by title
        hit = next((d for d in unmatched_dst if tkey(d) == tkey(s)), None)
        if hit:
            unmatched_dst.remove(hit)
        else:
            missing.append(s)

    print(f"EXTRA in clone — not matched to any original ({len(unmatched_dst)}):")
    for d in unmatched_dst:
        print(f"  id={d['id']}  type={d.get('type')}")
        print(f"     title={d['title'][:70]}")
        print(f"     url={(d.get('url') or '-')[:78]}")

    print(f"\nMISSING from clone ({len(missing)}):")
    for s in missing:
        print(f"  type={s.get('type')}  title={s['title'][:70]}")
        print(f"     url={(s.get('url') or '-')[:78]}")

    balance = len(dst) - len(unmatched_dst) + len(missing)
    ok = balance == len(src)
    print(f"\nbalance: {len(dst)} - {len(unmatched_dst)} extra + {len(missing)} "
          f"missing = {balance} (original {len(src)}) {'OK' if ok else 'MISMATCH'}")
    if not ok:
        print("Books do not balance — do NOT delete anything based on this run.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
