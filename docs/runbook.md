# YouTube-Clipper Runbook

## First-time setup

1. **Clone or open the repo** at `<repo>`.
2. **Install everything**:
   ```powershell
   scripts\install.ps1
   ```
   This runs `uv sync` for the daemon, `npm ci --ignore-scripts` for the extension (worm-safe), builds the extension, copies `config\.secrets.env` from the template if missing.
3. **Fill in secrets** (only if you want Azure summaries):
   - Open `config\.secrets.env`
   - Set `AZURE_FOUNDRY_ENDPOINT` and `AZURE_FOUNDRY_KEY`
   - If you only want Ollama: open `config\config.toml` and set `[summarizer.azure]` `enabled = false`. Replace the two `${AZURE_FOUNDRY_*}` strings with anything (e.g. `"unused"`) since interpolation runs before the `enabled` check.
4. **(Optional) Pull the Ollama model** if you'll use the local summarizer:
   ```powershell
   ollama pull qwen2.5:14b
   ```
5. **Start the daemon**:
   ```powershell
   scripts\start-daemon.ps1
   ```
   You'll see structured JSON log lines stream to stderr. Leave this terminal open.
6. **Load the extension in Chrome**:
   - `chrome://extensions/`
   - Toggle **Developer mode** (top right)
   - **Load unpacked**
   - Select `<repo>\apps\extension\dist`

## Daily use

1. Open any YouTube watch page.
2. Start the daemon (`scripts\start-daemon.ps1`) if it's not already running.
3. Hold **Ctrl** and drag across the seekbar to paint a range (pink overlay shows as you drag).
4. Click the **YouTube Clipper** icon in the toolbar — popup appears with the captured range.
5. Pick **Azure Foundry** or **Ollama** in the dropdown.
6. Click **Extract**.
7. Watch the live progress in the popup (6 stages).
8. When done, your note is at `output\<date>_<channel-slug>_<title-slug>_<NNN>\note.md`.

The popup's **Copy note path** button puts the path into your clipboard so you can paste it into Obsidian / Explorer.

## File layout per clip

```
output\2026-05-17_andrej-karpathy_agents-have-arrived_001\
  ├── note.md          your markdown note (TL;DR + bullets + transcript + My Notes)
  ├── audio.mp3        16 kHz mono mp3 of the range
  ├── transcript.json  word-level timestamps, language, model info
  ├── transcript.txt   readable timestamped transcript (`[mm:ss] text`)
  ├── manifest.json    full Job state (re-run input)
  ├── metadata.json    full yt-dlp -J dump of the source video
  ├── summary.json     summarizer output (tldr, bullets, tags, backend)
  └── raw.log          per-clip filtered JSON log (one job's complete trace)
```

The daemon's own daily log is at `logs\pipeline.jsonl[.YYYY-MM-DD]`.

## Re-running and "My Notes" preservation

You can re-render a note (e.g. after editing the transcript file or summary fields manually). The `## My Notes` section and everything below it in `note.md` is preserved verbatim across re-runs. The rest of the note is regenerated from the manifest + summary.json + transcript.json.

## Failure modes and recovery

| Symptom | Likely cause | Fix |
|---|---|---|
| Popup shows red dot, "Daemon not running" | uvicorn isn't running | `scripts\start-daemon.ps1` |
| Daemon refuses to start, "config references env var…" | `.secrets.env` missing or not loaded | Re-run `start-daemon.ps1` (it loads the file) or set the env vars manually |
| Stage 2 fails on a video | yt-dlp out of date or geo-blocked | `pip install -U yt-dlp` / use a VPN / try a different video |
| Stage 4 logs `whisper.fallback` repeatedly | CUDA OOM on a long clip | The daemon automatically retries with int8 then CPU. CPU will be ~5x slower. |
| Stage 5 fails with 401 | Azure key wrong | Update `config\.secrets.env`, restart daemon |
| Stage 5 fails on Ollama | Model not pulled | `ollama pull qwen2.5:14b` |
| Note has stale TL;DR | Old fields cached | Re-run from popup once daemon is fixed; My Notes will be preserved |

## Inspecting a failure

1. Find the job folder under `output\` (it stays on disk on failure for forensics).
2. Open `raw.log` — it's the daemon's structured JSON log filtered to that one `job_id`.
3. Each line is one event with `stage`, `event`, durations, and any captured `error_message`.
4. The `manifest.json` shows exactly which stage failed and what was completed.

## Where the logs live

- **All jobs combined, daily rotated**: `logs\pipeline.jsonl` (and `pipeline.jsonl.YYYY-MM-DD` after rollover)
- **Per-clip filtered**: `output\<clip-folder>\raw.log`

## Stopping the daemon

```powershell
scripts\stop-daemon.ps1
```

This kills whatever process owns TCP/7777.

## Worm-safe install reminders

- `npm install`/`npm ci` always runs with `--ignore-scripts` in `install.ps1`. Don't drop that flag.
- `package.json` pins exact versions (no `^`, no `~`).
- `package-lock.json` is committed.
- `install.ps1` strips `GH_TOKEN` and `NPM_TOKEN` from its process env before running npm.
- If you ever see the install script try to fetch unexpected packages, abort and ask before continuing.

## Doctor

Anytime something feels off:

```powershell
scripts\doctor.ps1
```

This probes every dependency and reports a green/red table. Exit code is 0 iff everything is green.
