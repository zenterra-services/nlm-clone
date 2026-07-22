#!/usr/bin/env python3
"""Compare source counts between a source and a target account.

    python verify.py <src-profile> <dst-profile> [titles.txt]

Without a titles file, every notebook whose title exists in both accounts is
compared. With one (one title per line, '#' comments allowed), only those are
checked and any missing from the target are reported as PENDING.

NOTE: matching counts are necessary but NOT sufficient. A web source whose
re-fetch was served a Cloudflare/reCAPTCHA/403 page still counts as a source,
so a notebook can verify "perfect" while holding a challenge page instead of
the article. Run scan_blocked.py and fidelity.py before trusting a clone.
"""
import sys
from pathlib import Path

from nlmutil import notebooks


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    src_profile, dst_profile = sys.argv[1], sys.argv[2]

    src = {n["title"]: n["source_count"] for n in notebooks(src_profile)}
    dst = {n["title"]: n["source_count"] for n in notebooks(dst_profile)}

    if len(sys.argv) > 3:
        titles = [ln.split("#")[0].strip()
                  for ln in Path(sys.argv[3]).read_text(encoding="utf-8-sig").splitlines()
                  if ln.split("#")[0].strip()]
    else:
        titles = sorted(set(src) & set(dst))
        if not titles:
            sys.exit("No notebook titles are present in both accounts.")

    done = pending = mismatch = 0
    for t in titles:
        s, d = src.get(t), dst.get(t)
        if s is None:
            print(f"NOT IN SOURCE  {t}")
        elif d is None:
            print(f"PENDING        {t}  ({s} sources)")
            pending += 1
        elif s == d:
            print(f"OK             {t}  {d}/{s}")
            done += 1
        else:
            print(f"MISMATCH       {t}  {d}/{s}")
            mismatch += 1

    print(f"\n{done} complete, {pending} pending, {mismatch} mismatched "
          f"(of {len(titles)})")
    print("Counts only — run scan_blocked.py and fidelity.py for real fidelity.")
    return 1 if mismatch else 0


if __name__ == "__main__":
    sys.exit(main())
