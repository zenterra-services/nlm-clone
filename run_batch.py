#!/usr/bin/env python3
"""Batch driver: clone a list of notebooks sequentially, paced, with retries.

    python run_batch.py <src-profile> <dst-profile> <list.txt> [gap-seconds]

<list.txt> holds one notebook ID per line; '#' starts a comment. Progress goes
to stdout — redirect it to a log file and tail that.

PACING MATTERS. NotebookLM invalidates the session after roughly 550-650
sources written in one stretch, after which every call fails with HTTP 400 and
only an interactive `nlm login -p <profile> --force` recovers it. Schedule one
large notebook (250-300 sources) per run, or a handful of small ones. The
default 120s gap between notebooks is a floor, not a fix.

Each clone is resumable, so a retry continues rather than duplicating work.
Two consecutive failures abort the run: that pattern means the session died,
and grinding through the rest just wastes time and muddies the logs.
"""
import subprocess
import sys
import time
from pathlib import Path

RETRIES = 2
RETRY_PAUSE = 30


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    src_profile, dst_profile, list_path = sys.argv[1], sys.argv[2], sys.argv[3]
    gap = int(sys.argv[4]) if len(sys.argv) > 4 else 120

    # utf-8-sig: PowerShell's `Out-File -Encoding utf8` prepends a BOM, which
    # would otherwise become part of the first notebook ID and match nothing.
    ids = [ln.split("#")[0].strip()
           for ln in Path(list_path).read_text(encoding="utf-8-sig").splitlines()
           if ln.split("#")[0].strip()]
    if not ids:
        sys.exit(f"No notebook IDs found in {list_path}")

    results = []
    for i, nid in enumerate(ids, 1):
        print(f"\n===== [{i}/{len(ids)}] {nid} =====", flush=True)
        ok = False
        for attempt in range(1 + RETRIES):
            if attempt:
                print(f"--- retry {attempt}/{RETRIES} ---", flush=True)
                time.sleep(RETRY_PAUSE)
            proc = subprocess.run(
                [sys.executable, "nlm_clone.py", "clone", nid,
                 "--from", src_profile, "--to", dst_profile],
                cwd=Path(__file__).parent)
            if proc.returncode == 0:
                ok = True
                break
        results.append((nid, ok))
        print(f"===== [{i}/{len(ids)}] {'OK' if ok else 'FAILED'} =====", flush=True)

        if len(results) >= 2 and not results[-1][1] and not results[-2][1]:
            print("ABORT: two consecutive failures — the session is probably "
                  f"dead. Check with: nlm notebook list -p {dst_profile}", flush=True)
            break

        if i < len(ids):
            time.sleep(gap)

    print("\n########## BATCH SUMMARY ##########", flush=True)
    for nid, ok in results:
        print(f"{'OK    ' if ok else 'FAILED'} {nid}", flush=True)
    skipped = len(ids) - len(results)
    if skipped:
        print(f"NOT ATTEMPTED: {skipped} (run aborted early)", flush=True)
    print("ALL DONE", flush=True)
    return 1 if any(not ok for _, ok in results) or skipped else 0


if __name__ == "__main__":
    sys.exit(main())
