---
name: clone-notebook
description: Clone NotebookLM notebooks (sources + notes) between Google accounts with the nlm-clone toolkit, run paced bulk migrations, and audit clones for fidelity. Use when the user asks to clone, copy, migrate, or back up a NotebookLM notebook, e.g. "clone <notebook title>", "copy my notebooks to my other account", "run the next two", or asks whether a cloned notebook is safe to delete.
---

# Clone NotebookLM notebooks between Google accounts

Toolkit: the `nlm-clone` checkout (this skill ships inside it, at
`skill/clone-notebook/`). Run the scripts from the repository root. Everything
wraps the `nlm` CLI with a per-call `--profile`, so no global account switching
occurs and two accounts can be used in one command.

**Set `NLM_CLONE_DIR`** (or ask the user where the checkout lives) rather than
assuming a path — this skill is portable.

| Script | Purpose |
|---|---|
| `nlm_clone.py` | `export` / `import` / `clone` one notebook. Resumable. |
| `run_batch.py <src> <dst> <list.txt> [gap]` | Clone many, paced, retries, auto-abort |
| `verify.py <src> <dst> [titles.txt]` | Count parity — necessary, **not sufficient** |
| `scan_blocked.py <src> <dst> [out.md]` | Web sources that re-fetched into a bot wall |
| `fidelity.py [exports-dir]` | Sources degraded to plain text (offline) |
| `reconcile.py <src-p> <src-id> <dst-p> <dst-id>` | One-to-one match; required before deleting |
| `scan_clone_only.py <profile> [prefix]` | Block-page check when the original is gone |

## Authentication — you cannot do this part

Each Google account needs an `nlm` profile, created by an **interactive browser
login**. There is no API key, token, or env var to set, and no way to automate
it.

```bash
nlm login profile list                 # which profiles exist, and whose account
nlm notebook list --json -p <profile>  # HTTP 400 => session is dead
```

If a profile is missing or dead, **STOP and ask the user** to run
`nlm login -p <profile> --force` and sign in via the browser it opens. Never
ask for, handle, echo, or store passwords, cookies, or tokens — the CLI keeps
credentials in `~/.notebooklm-mcp-cli/`, and this toolkit never touches them.

## Sessions die constantly — plan for it

Google invalidates the session after roughly **550–650 sources written in one
stretch**, and sessions also expire on their own overnight. Symptoms: adds fail
with "Could not add URL/file sources", then every call including
`notebook list` returns HTTP 400.

**Schedule one large notebook (250–300 sources) per run, or 2–3 small ones.**
Two large ones sits at the ceiling and has failed. Verify auth before starting,
and treat a mid-run death as expected rather than exceptional.

## Single notebook

```bash
python nlm_clone.py clone "<title or id>" --from <src> --to <dst>
```

`--title` renames the copy; `--dry-run` previews. After any failure, re-run the
identical command — import resumes from `exports/<slug>/import_state.json` and
never duplicates the notebook or already-added sources.

## Bulk migrations

Write a list file (one notebook ID per line, `#` comments fine), run it
detached, and attach a monitor to the log. Match on
`OK =====|FAILED =====|ABORT|ALL DONE|Done\. Notebook|UNACCOUNTED|batch of .* failed`.

**A retry loop re-exports and looks like healthy progress.** Check the count of
`^  ! ` failure lines, not just the newest log line, before reporting that a
run is fine.

## Verify — and never overclaim

1. `verify.py` — counts. **Weak guarantee**: a source whose re-fetch returned a
   Cloudflare page still counts as a source.
2. `scan_blocked.py` — the check counts cannot do. In the reference migration
   it found 241 affected sources across 14 of 27 notebooks that `verify.py`
   called flawless.
3. `fidelity.py` — format degradation.

Report what was actually checked. Never say "cloned 100%" on count evidence.

## Deleting anything

- **Only ever delete true duplicates**, and only with explicit user approval.
- Run `reconcile.py` first; require `clone − extras + missing == original`. If
  the books don't balance, delete nothing and investigate.
- Compare content length of both copies before removing either.
- **Same-title sources are usually not duplicates**: NotebookLM renames a web
  source when its re-fetch is blocked, so distinct pages collapse onto one
  title, and users legitimately add the same URL twice.
- **Never advise deleting an original** from count parity. Notebooks with
  bot-protected articles or original PDFs/images/audio lose real content the
  clone cannot reconstruct.

## Privacy when handling output

`exports/`, `*.log`, `blocked_sources.md` and `batch*.txt` contain the user's
notebook content, titles, and URLs. They are gitignored — keep them that way,
and don't paste their contents anywhere outside the conversation.

## Fidelity rules

- Web / YouTube with a URL → re-fetched fresh (may hit bot walls).
- PDF, Word, image, audio, Drive → **extracted text only**; the original file
  is unrecoverable from the clone or from `exports/`.
- YouTube returns `url: null` even from `source get`; only the transcript is
  retrievable. A title that is itself a URL is recovered; otherwise text.
- Notes copy fully (split at 25k chars).
- Never copied: chat history, Studio artifacts, source labels, sharing
  settings. Check `nlm list artifacts <id> -p <profile>` before calling an
  original expendable.

## Gotchas already fixed — don't reintroduce

- `nlm source content --output` crashes on Unicode (Windows). Fetch `--json`,
  unwrap `value.content`, write UTF-8 yourself.
- Uploads take the filename as title; rename after, plus an end-of-run fixup
  pass for uploads still processing.
- PowerShell `Out-File -Encoding utf8` writes a BOM that corrupts the first
  notebook ID. Read list files as `utf-8-sig`.
- **Never let an unreadable account degrade to an empty list** (`or []`) — that
  turns a dead session into a false "all clean" result. Fail loudly.
- `nlm source delete` takes bare source IDs plus `-y`; there is no `--notebook` flag.
