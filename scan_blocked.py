#!/usr/bin/env python3
"""Find cloned web sources whose re-fetch returned a bot-block or error page.

    python scan_blocked.py <src-profile> <dst-profile> [report.md]

Notebooks are matched by title between the two accounts. For every URL source
present in both, the clone's title is checked against BLOCK_MARKERS: if the
clone looks like a challenge page and the original did not, the content was
lost even though the source count still matches.

This is the check that source-count verification cannot do. The original
account still holds the real content for every source listed.

The report contains notebook titles and URLs from the account being scanned —
treat it as private and keep it out of version control.
"""
import sys
from pathlib import Path

from nlmutil import looks_blocked, notebooks, sources


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    src_profile, dst_profile = sys.argv[1], sys.argv[2]
    out = Path(sys.argv[3] if len(sys.argv) > 3 else "blocked_sources.md")

    dst_by_title = {n["title"]: n for n in notebooks(dst_profile)}
    pairs = [(s, dst_by_title[s["title"]])
             for s in notebooks(src_profile) if s["title"] in dst_by_title]
    if not pairs:
        sys.exit("No notebook titles are present in both accounts — nothing to compare.")
    print(f"scanning {len(pairs)} cloned notebooks...\n", flush=True)

    report, total = [], 0
    for i, (s, d) in enumerate(pairs, 1):
        ss = sources(s["id"], src_profile, strict=False)
        ds = sources(d["id"], dst_profile, strict=False)
        if ss is None or ds is None:
            # Never let an unreadable notebook look like a clean one.
            print(f"[{i}/{len(pairs)}] {s['title'][:55]:<55} READ FAILED", flush=True)
            report.append((s["title"], None, [], True))
            continue
        src_by_url = {x["url"]: x for x in ss if x.get("url")}
        hits = []
        for x in ds:
            if x.get("url") and looks_blocked(x.get("title")):
                orig = src_by_url.get(x["url"])
                if orig is not None and not looks_blocked(orig.get("title")):
                    hits.append((orig["title"], x["title"], x["url"]))
        total += len(hits)
        print(f"[{i}/{len(pairs)}] {s['title'][:55]:<55} "
              f"{f'{len(hits)} blocked' if hits else 'clean'}", flush=True)
        report.append((s["title"], d["id"], hits, False))

    failed = [r for r in report if r[3]]
    with out.open("w", encoding="utf-8") as f:
        f.write("# Web sources that lost content in the clone\n\n")
        f.write("These sources exist in both accounts and the counts match, but the\n")
        f.write("clone holds a bot-block/error page rather than the article. The\n")
        f.write("original notebook still has the real content.\n\n")
        f.write(f"**{total} affected sources across "
                f"{sum(1 for r in report if r[2])} notebooks.**\n\n")
        if failed:
            f.write(f"> WARNING: {len(failed)} notebook(s) could not be read and were "
                    f"NOT checked: {', '.join(r[0] for r in failed)}\n\n")
        for title, _, hits, _ in sorted(report, key=lambda r: -len(r[2])):
            if not hits:
                continue
            f.write(f"## {title} — {len(hits)}\n\n")
            for o, n, u in hits:
                f.write(f"- **{o}**\n  - now: `{n}`\n  - {u}\n")
            f.write("\n")
        clean = [r[0] for r in report if not r[2] and not r[3]]
        f.write(f"## Clean ({len(clean)})\n\n")
        for t in clean:
            f.write(f"- {t}\n")

    print(f"\n{total} affected sources across "
          f"{sum(1 for r in report if r[2])} of {len(pairs)} notebooks")
    if failed:
        print(f"WARNING: {len(failed)} notebook(s) could not be read and were NOT checked")
    print(f"report: {out}  (contains private titles/URLs — do not commit)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
