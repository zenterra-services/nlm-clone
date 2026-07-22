#!/usr/bin/env python3
"""
nlm-clone — Copy a NotebookLM notebook (sources + notes) between Google accounts.

Uses the `nlm` CLI (notebooklm-tools) with its per-command --profile support,
so no global profile switching is needed.

Commands:
    export  Dump a notebook (metadata, sources, raw content, notes) to a folder.
    import  Rebuild a notebook from an export folder into another profile.
    clone   export + import in one step.

Examples:
    python nlm_clone.py export "My Notebook" --profile default
    python nlm_clone.py import exports/my-notebook --profile work
    python nlm_clone.py clone "My Notebook" --from default --to work

Prerequisite: each Google account needs an nlm auth profile, created by an
interactive browser login. Profile names are the only account identifiers this
tool handles — credentials are owned entirely by the `nlm` CLI and stored in
~/.notebooklm-mcp-cli/, outside this repository. Nothing here reads, writes,
logs, or transmits them.

    nlm login                 # first account -> profile "default"
    nlm login -p work         # second account -> profile "work"

Local output (exports/, logs) contains your notebook content — see README.
"""

import argparse
import json
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)

# Source types that are re-added by URL (NotebookLM fetches them fresh).
URL_TYPES = {"web_page", "website", "web"}
YOUTUBE_TYPES = {"youtube_video", "youtube"}
# Everything else (pdf, uploaded_file, pasted_text, generated_text, image,
# google_docs, ...) is re-imported from the extracted raw content as a text
# file upload, which preserves the text but not original formatting/images.

MAX_NOTE_CHUNK = 25000  # note content goes on the command line; stay under Windows limits


def log(msg):
    print(msg, flush=True)


def run_nlm(args, profile=None, timeout=900, check=True):
    cmd = ["nlm"] + args
    if profile:
        cmd += ["--profile", profile]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=timeout,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"nlm {' '.join(args[:3])}... failed (exit {proc.returncode}):\n"
            f"{proc.stdout}\n{proc.stderr}"
        )
    return proc


def run_nlm_json(args, profile=None, timeout=900):
    proc = run_nlm(args + ["--json"], profile=profile, timeout=timeout)
    return json.loads(proc.stdout)


def slugify(text, maxlen=60):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return text[:maxlen] or "notebook"


def resolve_notebook(id_or_title, profile):
    """Accept a notebook UUID or an (exact, case-insensitive) title."""
    if UUID_RE.fullmatch(id_or_title.strip()):
        return id_or_title.strip(), None
    notebooks = run_nlm_json(["notebook", "list"], profile=profile)
    matches = [n for n in notebooks if n["title"].lower() == id_or_title.lower()]
    if not matches:
        matches = [n for n in notebooks if id_or_title.lower() in n["title"].lower()]
    if len(matches) != 1:
        titles = "\n  ".join(f'{n["id"]}  {n["title"]}' for n in (matches or notebooks))
        raise SystemExit(
            f"Could not uniquely resolve notebook '{id_or_title}' "
            f"({len(matches)} matches). Candidates:\n  {titles}"
        )
    return matches[0]["id"], matches[0]["title"]


# ---------------------------------------------------------------- export ----

def cmd_export(args):
    notebook_id, title = resolve_notebook(args.notebook, args.profile)
    if title is None:
        notebooks = run_nlm_json(["notebook", "list"], profile=args.profile)
        title = next((n["title"] for n in notebooks if n["id"] == notebook_id), notebook_id)

    out_dir = Path(args.out) if args.out else Path("exports") / slugify(title)
    content_dir = out_dir / "content"
    content_dir.mkdir(parents=True, exist_ok=True)
    log(f"Exporting '{title}' ({notebook_id}) -> {out_dir}")

    sources = run_nlm_json(["source", "list", notebook_id, "--full"], profile=args.profile)
    log(f"  {len(sources)} sources")

    for i, src in enumerate(sources, 1):
        stype = (src.get("type") or "").lower()
        src["strategy"] = "url" if stype in URL_TYPES else (
            "youtube" if stype in YOUTUBE_TYPES else "text")
        src["content_file"] = None
        # NotebookLM's API returns url=None for some sources (notably YouTube).
        # Recover the URL from the title when the title *is* a URL; otherwise
        # fall back to importing the extracted transcript as text so the source
        # is never silently lost.
        if src["strategy"] != "text" and not src.get("url"):
            t = (src.get("title") or "").strip()
            if t.startswith(("http://", "https://")):
                src["url"] = t
            else:
                src["strategy"] = "text"
                src["url_lost"] = True
        if src["strategy"] != "text" and not args.fetch_all:
            log(f"  [{i}/{len(sources)}] {src['title'][:70]}  (will re-add by URL)")
            continue
        fname = f"{i:03d}-{slugify(src['title'], 50)}.txt"
        try:
            # nlm's own --output flag writes with the OS default codepage and
            # crashes on non-ASCII content (Windows); fetch JSON and write UTF-8.
            data = run_nlm_json(["source", "content", src["id"]], profile=args.profile)
            if isinstance(data.get("value"), dict):
                data = data["value"]
            content = data.get("content") or ""
            if content.strip():
                fpath = content_dir / fname
                fpath.write_text(content, encoding="utf-8")
                src["content_file"] = f"content/{fname}"
                log(f"  [{i}/{len(sources)}] {src['title'][:70]}  ({len(content)} chars)")
            else:
                log(f"  [{i}/{len(sources)}] {src['title'][:70]}  WARNING: empty content")
        except Exception as e:
            log(f"  [{i}/{len(sources)}] {src['title'][:70]}  ERROR: {e}")

    notes_raw = run_nlm_json(["note", "list", notebook_id], profile=args.profile)
    notes = notes_raw.get("notes", notes_raw) if isinstance(notes_raw, dict) else notes_raw
    log(f"  {len(notes)} notes")

    manifest = {
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_profile": args.profile,
        "notebook": {"id": notebook_id, "title": title},
        "sources": sources,
        "notes": notes,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"Export complete: {out_dir / 'manifest.json'}")
    return out_dir


# ---------------------------------------------------------------- import ----

def load_state(out_dir):
    state_file = out_dir / "import_state.json"
    if state_file.exists():
        return json.loads(state_file.read_text(encoding="utf-8"))
    return {"notebook_id": None, "done_sources": [], "done_notes": []}


def save_state(out_dir, state):
    (out_dir / "import_state.json").write_text(
        json.dumps(state, indent=2), encoding="utf-8")


def cmd_import(args):
    out_dir = Path(args.export_dir)
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    title = args.title or manifest["notebook"]["title"]
    sources = manifest["sources"]
    notes = manifest["notes"]
    state = load_state(out_dir)

    log(f"Importing '{title}' into profile '{args.profile}' "
        f"({len(sources)} sources, {len(notes)} notes)")
    if args.dry_run:
        for s in sources:
            log(f"  would add [{s['strategy']}] {s['title'][:70]}")
        for n in notes:
            log(f"  would add note: {(n.get('title') or 'Untitled')[:70]}")
        return

    if state["notebook_id"]:
        notebook_id = state["notebook_id"]
        log(f"  resuming into existing notebook {notebook_id}")
    else:
        proc = run_nlm(["notebook", "create", title], profile=args.profile)
        m = UUID_RE.search(proc.stdout + proc.stderr)
        if not m:
            raise RuntimeError(f"Could not parse new notebook id from:\n{proc.stdout}")
        notebook_id = m.group(0)
        state["notebook_id"] = notebook_id
        save_state(out_dir, state)
        log(f"  created notebook {notebook_id}")

    skipped, failed = [], []

    # URL-type sources: batch re-add (NotebookLM fetches fresh copies).
    for flag, strategy in (("--url", "url"), ("--youtube", "youtube")):
        pending = [s for s in sources
                   if s["strategy"] == strategy and s.get("url")
                   and s["id"] not in state["done_sources"]]
        for chunk_start in range(0, len(pending), 10):
            chunk = pending[chunk_start:chunk_start + 10]
            cmd = ["source", "add", notebook_id]
            for s in chunk:
                cmd += [flag, s["url"]]
            try:
                run_nlm(cmd, profile=args.profile)
                for s in chunk:
                    state["done_sources"].append(s["id"])
                    log(f"  + [{strategy}] {s['title'][:70]}")
            except Exception as e:
                failed += [(s, str(e)) for s in chunk]
                log(f"  ! batch of {len(chunk)} {strategy} sources failed: {e}")
            save_state(out_dir, state)

    # Content-based sources: upload extracted text as a file.
    pending = [s for s in sources
               if s["strategy"] == "text" and s["id"] not in state["done_sources"]]
    for i, s in enumerate(pending, 1):
        if not s.get("content_file"):
            skipped.append(s)
            log(f"  - skipped (no content): {s['title'][:70]}")
            continue
        fpath = out_dir / s["content_file"]
        try:
            proc = run_nlm(["source", "add", notebook_id, "--file", str(fpath),
                            "--title", s["title"]], profile=args.profile)
            # The upload takes the filename as title; rename to the original.
            m = UUID_RE.search(proc.stdout.split("Source ID:")[-1])
            if m:
                run_nlm(["source", "rename", m.group(0), s["title"],
                         "--notebook", notebook_id], profile=args.profile)
            state["done_sources"].append(s["id"])
            log(f"  + [text {i}/{len(pending)}] {s['title'][:70]}")
        except Exception as e:
            failed.append((s, str(e)))
            log(f"  ! failed: {s['title'][:70]}: {e}")
        save_state(out_dir, state)

    # Notes.
    for n in notes:
        nid = n.get("id") or n.get("title") or ""
        if nid in state["done_notes"]:
            continue
        ntitle = n.get("title") or "Untitled note"
        content = n.get("content") or n.get("text") or ""
        chunks = [content[i:i + MAX_NOTE_CHUNK]
                  for i in range(0, max(len(content), 1), MAX_NOTE_CHUNK)]
        try:
            for ci, chunk in enumerate(chunks):
                ct = ntitle if len(chunks) == 1 else f"{ntitle} (part {ci + 1}/{len(chunks)})"
                run_nlm(["note", "create", notebook_id, "--title", ct,
                         "--content", chunk or " "], profile=args.profile)
            state["done_notes"].append(nid)
            log(f"  + note: {ntitle[:70]}")
        except Exception as e:
            failed.append((n, str(e)))
            log(f"  ! note failed: {ntitle[:70]}: {e}")
        save_state(out_dir, state)

    # Title fixup pass: an upload that was still processing when we renamed it
    # can keep the temp filename as its title; retry those now.
    wanted = {Path(s["content_file"]).stem: s["title"]
              for s in sources if s.get("content_file")}
    new_sources = run_nlm_json(["source", "list", notebook_id], profile=args.profile)
    for ns in new_sources:
        stem = ns["title"].removesuffix(".txt")
        if stem in wanted and ns["title"] != wanted[stem]:
            try:
                run_nlm(["source", "rename", ns["id"], wanted[stem],
                         "--notebook", notebook_id], profile=args.profile)
                log(f"  ~ fixed title: {wanted[stem][:70]}")
            except Exception as e:
                log(f"  ! title fixup failed for {ns['title'][:50]}: {e}")

    # Summary.
    new_sources = run_nlm_json(["source", "list", notebook_id], profile=args.profile)
    log("")
    log(f"Done. Notebook '{title}' in profile '{args.profile}': "
        f"{len(new_sources)}/{len(sources)} sources, "
        f"{len(state['done_notes'])}/{len(notes)} notes.")
    # Never drop a source silently: account for every one in the manifest.
    handled = set(state["done_sources"]) | {s["id"] for s in skipped} \
        | {s.get("id") for s, _ in failed}
    unhandled = [s for s in sources if s["id"] not in handled]
    if unhandled:
        log(f"UNACCOUNTED FOR: {len(unhandled)} source(s) neither added nor "
            f"reported — this is a bug, please investigate:")
        for s in unhandled:
            log(f"  ? {s['title'][:70]} [{s.get('type')}] url={s.get('url')}")

    lost = [s for s in sources if s.get("url_lost") and s["id"] in state["done_sources"]]
    if lost:
        log(f"Imported as text only (original URL not exposed by the API): {len(lost)}")
        for s in lost:
            log(f"  ~ {s['title'][:70]} [{s.get('type')}]")

    if skipped:
        log(f"Skipped (no exportable content): {len(skipped)}")
        for s in skipped:
            log(f"  - {s['title'][:70]} [{s.get('type')}]")
    if failed:
        log(f"Failed: {len(failed)} (re-run the same import command to retry)")
        for s, err in failed[:10]:
            log(f"  ! {(s.get('title') or '?')[:70]}: {err.splitlines()[0][:100]}")
    log(f"Open it: https://notebooklm.google.com/notebook/{notebook_id}")


def cmd_clone(args):
    export_ns = argparse.Namespace(
        notebook=args.notebook, profile=args.src, out=args.out,
        fetch_all=args.fetch_all)
    out_dir = cmd_export(export_ns)
    import_ns = argparse.Namespace(
        export_dir=str(out_dir), profile=args.dst, title=args.title,
        dry_run=args.dry_run)
    cmd_import(import_ns)


def main():
    p = argparse.ArgumentParser(
        prog="nlm-clone",
        description="Copy a NotebookLM notebook (sources + notes) between Google accounts.")
    sub = p.add_subparsers(dest="command", required=True)

    pe = sub.add_parser("export", help="Export a notebook to a local folder")
    pe.add_argument("notebook", help="Notebook ID or title")
    pe.add_argument("--profile", default="default", help="Source nlm profile")
    pe.add_argument("--out", help="Output folder (default: exports/<slug>)")
    pe.add_argument("--fetch-all", action="store_true",
                    help="Also download raw content of URL sources (as fallback)")
    pe.set_defaults(func=cmd_export)

    pi = sub.add_parser("import", help="Rebuild a notebook from an export folder")
    pi.add_argument("export_dir", help="Folder created by 'export'")
    pi.add_argument("--profile", required=True, help="Target nlm profile")
    pi.add_argument("--title", help="Override notebook title")
    pi.add_argument("--dry-run", action="store_true")
    pi.set_defaults(func=cmd_import)

    pc = sub.add_parser("clone", help="Export from one profile and import into another")
    pc.add_argument("notebook", help="Notebook ID or title")
    pc.add_argument("--from", dest="src", default="default", help="Source profile")
    pc.add_argument("--to", dest="dst", required=True, help="Target profile")
    pc.add_argument("--out", help="Export folder (default: exports/<slug>)")
    pc.add_argument("--title", help="Override notebook title in target account")
    pc.add_argument("--fetch-all", action="store_true")
    pc.add_argument("--dry-run", action="store_true")
    pc.set_defaults(func=cmd_clone)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nInterrupted. Re-run the same command to resume.")
