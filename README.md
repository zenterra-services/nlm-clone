# nlm-clone

Copy a NotebookLM notebook — sources and notes — from one Google account to
another, then **audit whether the copy is actually faithful**.

NotebookLM has no public API. This toolkit drives the
[`nlm` CLI](https://pypi.org/project/notebooklm-mcp-cli/) (`notebooklm-tools`),
which talks to NotebookLM's internal endpoints using a browser login. Every
call takes an explicit `--profile`, so nothing is switched globally and two
accounts can be used in the same run.

Proven on a 36-notebook / ~4,900-source migration between two accounts.

> **Unofficial and unsupported.** This depends on private endpoints that Google
> can change or block at any time, and on automation that Google may rate-limit
> (see [Throttling](#throttling-read-this-before-a-bulk-run)). Use it on
> accounts you own, at your own risk.

---

## Authentication — what you need, and what this tool never touches

**You need one `nlm` auth profile per Google account.** Creating one opens a
browser for a normal Google sign-in:

```bash
nlm login                  # first account  -> profile "default"
nlm login -p work          # second account -> profile "work"
nlm login profile list     # verify which account each profile holds
```

- Credentials are session cookies obtained by that browser login. **The `nlm`
  CLI owns them entirely** and stores them under `~/.notebooklm-mcp-cli/`
  (`auth.json` plus a Chrome profile directory) — outside this repository.
- **This toolkit never reads, writes, logs, or transmits credentials.** It only
  passes a *profile name* (a string like `work`) to the `nlm` CLI, which does
  its own auth. There is no API key, token, or secret to configure here, and
  nothing to put in a `.env`.
- No network calls are made by this code except through the `nlm` CLI to
  NotebookLM. Nothing is sent anywhere else, and there is no telemetry.
- Sessions expire often — see [Throttling](#throttling-read-this-before-a-bulk-run).
  Re-authenticating always requires an interactive browser login
  (`nlm login -p <profile> --force`); it cannot be automated or scripted.

If you ever use `nlm login --manual -f cookies.json`, that cookie file contains
live session credentials for your Google account. Keep it outside the repo and
delete it afterwards — `.gitignore` covers common names as a safety net, but
don't rely on that.

## Privacy — the biggest risk in this repo is your own data

Running this tool writes your notebook *content* into the working directory:

| Path | Contains |
|---|---|
| `exports/` | Full extracted text of every source, plus titles and URLs |
| `*.log` | Notebook titles, source titles, URLs |
| `blocked_sources.md` | Titles and URLs of affected sources |
| `batch*.txt` | Notebook IDs from your account |

**All of it is gitignored.** Before publishing a fork or sharing a clone of
this repo, run `git status --ignored` and confirm none of it is staged. A
36-notebook migration produced ~78 MB of private text in `exports/` alone.

---

## Quick start

```bash
# One-shot: copy a notebook from profile "default" into profile "work"
python nlm_clone.py clone "My Notebook" --from default --to work

# Or in two steps — the export folder doubles as a local backup
python nlm_clone.py export "My Notebook" --profile default
python nlm_clone.py import exports/my-notebook --profile work

# Preview without changing anything
python nlm_clone.py import exports/my-notebook --profile work --dry-run
```

Identify a notebook by title (exact or unique substring) or by UUID. `export`
writes `manifest.json` plus the raw text of every content-based source;
`import` is **resumable** — re-run the same command after a failure and it
continues from `import_state.json` rather than duplicating anything.

## The scripts

| Script | Purpose |
|---|---|
| `nlm_clone.py` | `export` / `import` / `clone` a single notebook. Resumable. |
| `run_batch.py <src> <dst> <list.txt> [gap]` | Clone many, paced, with retries and auto-abort |
| `verify.py <src> <dst> [titles.txt]` | Source-count parity — necessary, **not sufficient** |
| `scan_blocked.py <src> <dst> [out.md]` | Web sources whose re-fetch hit a bot wall |
| `fidelity.py [exports-dir]` | Which sources were degraded to plain text (offline) |
| `reconcile.py <src-p> <src-id> <dst-p> <dst-id>` | One-to-one match; run before deleting anything |
| `scan_clone_only.py <profile> [prefix]` | Block-page check when the original is already gone |

## What gets copied, and how

| Original source type | How it is rebuilt |
|---|---|
| Web page | Re-added by URL — NotebookLM fetches a **fresh** copy |
| YouTube (URL recoverable) | Re-added by URL |
| YouTube (URL hidden by the API) | Transcript imported as text; video link lost |
| PDF / Word / uploaded file | **Extracted text only** — formatting, images, and the original file are lost |
| Image / audio | Extracted text only, if NotebookLM extracted any; otherwise skipped and reported |
| Pasted / generated text | Re-uploaded verbatim (blank lines and list numbering may normalise) |
| Google Drive doc | Extracted text (the target account may not have Drive access) |
| Notes | Recreated with title and content; notes over 25k chars are split |

**Never copied** — NotebookLM offers no transfer path: chat history, Studio
artifacts (audio/video overviews, mind maps, reports, quizzes — regenerable in
the copy), source labels, sharing settings. Check
`nlm list artifacts <id> -p <profile>` before treating an original as expendable.

NotebookLM's per-notebook source cap (~300) applies to the target too.

> **Only need access, not ownership?** `nlm share invite <notebook-id> <email>`
> shares the original outright — nothing is copied, nothing degrades.

---

## Throttling (read this before a bulk run)

Google invalidates the session after roughly **550–650 sources written in one
stretch** — observed three times in a large migration, with 2–3 minute pauses
between notebooks. Symptoms, in order:

1. Source adds start failing: `Could not add URL sources` / `Could not add file source`
2. Then *every* call, including `nlm notebook list`, returns **HTTP 400**

The only recovery is an interactive `nlm login -p <profile> --force`. Sessions
also expire on their own between working days.

**Therefore:** schedule **one large notebook (250–300 sources) per run**, or a
handful of small ones. Two large notebooks in one run sits right at the ceiling
and has failed. `run_batch.py` aborts after two consecutive failures instead of
grinding through the rest.

## Verifying a clone — counts are not fidelity

`verify.py` compares source counts. That check is necessary but **cannot detect
the most common form of loss**: a web page whose re-fetch was served a
Cloudflare challenge, a reCAPTCHA, or a 403 **still counts as a source**. The
count matches perfectly while the copy holds a block page instead of the article.

In the reference migration this affected **241 sources across 14 of 27
notebooks** that `verify.py` reported as flawless. Always run:

```bash
python scan_blocked.py default work    # writes blocked_sources.md
python fidelity.py                     # offline, reads local manifests
```

Do not describe a clone as complete on the strength of counts alone.

## Before you delete an original

1. `scan_blocked.py` — if the notebook's value is in bot-protected articles,
   the copy may hold challenge pages. The original still has the real content.
2. `fidelity.py` — PDFs, Word docs, images and audio exist in the clone as
   **extracted text only**. The original files cannot be reconstructed, and
   `exports/` holds text, not the files.
3. `nlm list artifacts` — Studio artifacts and chat history never transfer.

When removing duplicates, run `reconcile.py` first and require the books to
balance (`clone − extras + missing == original`). **Same-title sources are
usually not duplicates**: NotebookLM renames a web source when its re-fetch is
blocked, so many distinct pages collapse onto one title, and notebooks
legitimately contain the same URL twice. Matching on titles alone will make you
delete real content.

## Security posture

Static analysis (Bandit, Ruff, Flake8, mypy) is clean. Notes for reviewers:

- **No third-party dependencies.** The toolkit imports only the Python standard
  library, so there is no dependency CVE surface to audit.
- **No shell execution.** Every subprocess call passes an argument *list* with
  `shell=False` (the default), so notebook titles, IDs and URLs cannot be
  interpreted as shell syntax. Bandit's B404/B603 findings flag the use of
  `subprocess` itself, not an injection path. There is no `eval`, `exec`, or
  `shell=True` anywhere.
- **Export folders are untrusted input.** `manifest.json` drives the import, so
  a manifest obtained from someone else is attacker-controlled data. Import
  rejects any `content_file` that resolves outside the export directory —
  without that check, a crafted manifest could have a file such as
  `../../../.ssh/id_rsa` uploaded to a NotebookLM notebook. Only import export
  folders you produced or trust.
- **Credentials are never handled here** — see
  [Authentication](#authentication--what-you-need-and-what-this-tool-never-touches).
- **No network access of its own.** All traffic goes through the `nlm` CLI to
  NotebookLM; there is no telemetry and no other endpoint.

Found a security issue? Open an issue, or report privately if it is sensitive.

## Requirements

- Python 3.9+ (no third-party packages)
- `nlm` CLI: `pip install notebooklm-mcp-cli` (or `uv tool install`)
- A Google account per profile, each logged in once via browser

## Known platform quirks handled

- `nlm source content --output` crashes on non-ASCII content under Windows;
  this toolkit fetches `--json` and writes UTF-8 itself.
- Uploaded files take the filename as their title, so titles are restored
  afterwards, with a second fixup pass for uploads still processing.
- YouTube sources report `url: null` even from `source get`; only the
  transcript is retrievable.
- PowerShell's `Out-File -Encoding utf8` writes a BOM that would corrupt the
  first notebook ID; list files are read as `utf-8-sig`.

## License

MIT — see `LICENSE`.
