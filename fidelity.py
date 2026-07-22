#!/usr/bin/env python3
"""Report per-notebook clone fidelity from local export manifests.

    python fidelity.py [exports-dir]

Distinguishes sources recreated faithfully (re-added by URL, or text that was
already text) from those degraded to extracted text — a PDF, Word doc, image,
audio file or Drive doc becomes plain text in the clone, losing formatting,
images, and the original file itself.

Reads only local manifests; no account access, so no session required.
"""
import json
import sys
from pathlib import Path

# Types that were already plain text upstream, so re-uploading text loses nothing.
EXACT_TYPES = {"pasted_text", "generated_text"}


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "exports")
    manifests = sorted(root.glob("*/manifest.json"))
    if not manifests:
        sys.exit(f"No manifests found under {root}/ — run an export first.")

    rows = []
    for mf in manifests:
        m = json.loads(mf.read_text(encoding="utf-8"))
        exact = degraded = 0
        dtypes = {}
        for s in m["sources"]:
            stype = (s.get("type") or "?").lower()
            if s.get("url_lost"):            # YouTube etc: URL not exposed by API
                degraded += 1
                dtypes[stype] = dtypes.get(stype, 0) + 1
            elif s["strategy"] in ("url", "youtube"):
                exact += 1
            elif stype in EXACT_TYPES:
                exact += 1
            else:
                degraded += 1
                dtypes[stype] = dtypes.get(stype, 0) + 1
        rows.append((m["notebook"]["title"], len(m["sources"]), exact, degraded,
                     dtypes, len(m["notes"])))

    rows.sort(key=lambda r: (r[3] > 0, -r[1]))
    for title, total, _exact, degraded, dtypes, notes in rows:
        tag = "IDENTICAL" if degraded == 0 else f"{degraded} as text"
        detail = "" if not dtypes else "  [" + ", ".join(
            f"{k}:{v}" for k, v in sorted(dtypes.items())) + "]"
        print(f"{tag:<14} {title[:58]:<58} {total:>3} src, {notes} notes{detail}")

    identical = sum(1 for r in rows if r[3] == 0)
    print(f"\n{identical} of {len(rows)} exported notebooks reproduced with every "
          f"source in its original form.")
    print("Sources shown 'as text' cannot be turned back into the original file — "
          "keep those originals.")


if __name__ == "__main__":
    main()
