# YouTube-Clipper

> Hear a great moment in YouTube. Alt+drag the seekbar. Get verbatim audio,
> a Whisper transcript, AI-written summary + bullets + notable quotes, and a
> shareable web page. All local, all in one folder, in under a minute.

Built for educators, second-brain builders, and anyone who quotes other people's
ideas for a living and is tired of scrubbing, transcribing, and pasting.

## What it produces

For every Alt+drag range, you get a single folder with:

```
2026-05-17_<channel-slug>_<title-slug>_NNN/
├── note.md           markdown note — TL;DR, bullets, notable quotes, transcript,
│                     audio embed, jump-to-time links, sacrosanct "My Notes"
│                     section that survives every re-run
├── audio.mp3         16 kHz mono, ready for Whisper or sharing
├── transcript.json   word-level segments, language, model, durations
├── transcript.txt    [mm:ss] readable form
├── summary.json      tldr, bullets, notable_quotes, tags, backend
├── metadata.json     full yt-dlp -J dump of the source video
├── manifest.json     Job state (re-run input, retry budgets, durations)
├── raw.log           daemon's structured JSON log filtered to this one job_id
└── index.html        (on demand) self-contained editorial page with
                      click-to-jump transcript and embedded audio. Zero CDN deps.
```

## How it works

```
[Alt+drag on YouTube seekbar]
   │
   ▼
Chrome MV3 extension ──HTTP/WS──▶  FastAPI daemon (127.0.0.1:7777)
                                      │
   ┌───────────────┬───────────────┬──┴─────────────┬────────────────┬──────────────┐
   ▼               ▼               ▼                ▼                ▼              ▼
 1.resolve     2.download     3.normalize      4.transcribe     5.summarize    6.write_note
 (yt-dlp -J)   (yt-dlp        (ffmpeg          (faster-whisper   (Azure OR     (Jinja2 →
               range)         16k mono mp3)    local CPU/GPU)    Ollama, JSON  note.md +
                                                                 mode)         index.html)
```

Five stages are **deterministic** wrappers around battle-tested CLI tools.
**Only stage 5 is AI.** That ratio is the architecture — robustness comes from
minimizing the AI surface. When something fails, it fails in a known stage with
a known error class. When something is slow, you can see exactly which stage
spent which milliseconds in `manifest.json`.

## Why Alt+drag, not a button

Capture friction is the difference between *"I'll save this later"* and *"I have
this forever"*. Five seconds versus five minutes. The extension paints a pink
overlay on YouTube's native seekbar while you drag, locks the range on release,
and pre-fills the popup. Zero copy-paste. Zero typing. Ctrl was conflicting with
YouTube's own seekbar shortcuts, so Alt is the trigger.

## The summarizer: pick per clip

Two backends, switched in the popup dropdown:

- **Ollama** (local) — `hermes3:8b`, `qwen2.5:14b`, anything you've pulled.
  Transcript never leaves the box. Slower (10-30s) but free and private.
- **Azure Foundry** — `gpt-4o-mini` by default. Faster, higher quality, needs
  an API key, sends the transcript to Azure.

Detail intensity is also selectable: **Quick** (3-5 terse bullets), **Standard**
(5-8 balanced), **Deep** (8-12 thorough with longer notable quotes).

Want a third backend? The summarizer adapter is one file (`Summarizer` protocol
in `apps/daemon/youtube_clipper/adapters/base.py`). 30 lines of `httpx` and
you're done.

## The website export

Click **Generate website** on any completed clip. The daemon renders a single
self-contained `index.html` in the clip folder: dark editorial theme, embedded
audio player, click-any-timestamp-to-jump transcript, pull-quotes for the AI's
favorite lines. Zero CDN dependencies. Open by double-click, host anywhere.

Want a custom design? Click **Custom design (Claude prompt)**. It copies a
full `frontend-design` prompt to your clipboard. Paste into Claude Code, get
an `index.custom.html` rendered next to the default.

## Local-first by default

- Audio never leaves the box. Whisper runs locally.
- Transcript never leaves the box if you pick Ollama.
- Daemon binds `127.0.0.1`, never exposed externally.
- No telemetry, no accounts, no analytics.
- Daemon stays in memory: ~120 MB plus the Whisper model.

## Install

You need:

| Tool | Why | Get it |
|---|---|---|
| Python 3.11 or 3.12 | Daemon runtime | uv will pick one for you |
| `uv` | Python deps and version manager | `https://docs.astral.sh/uv/getting-started/installation/` |
| Node 20+ and npm | Build the extension | `https://nodejs.org/` |
| `ffmpeg` | Audio normalize | `winget install Gyan.FFmpeg` / `brew install ffmpeg` / apt |
| `yt-dlp` | YouTube download | `winget install yt-dlp` / `brew install yt-dlp` / pip |
| Chromium browser | The extension | Chrome or Edge |
| Ollama (optional) | Local summarizer | `https://ollama.com/` — then `ollama pull hermes3:8b` |
| Azure OpenAI (optional) | Cloud summarizer | Azure portal → create OpenAI resource → deployment for `gpt-4o-mini` |

### Windows (the path I tested)

```powershell
git clone https://github.com/OthmanAdi/YouTube-Clipper.git
cd YouTube-Clipper
scripts\install.ps1            # uv sync + npm ci --ignore-scripts + builds the extension
# (only if you want Azure) edit config\.secrets.env with your endpoint + key
scripts\start-daemon.ps1       # uvicorn on 127.0.0.1:7777
```

Then in Edge or Chrome:

1. `chrome://extensions/` → toggle **Developer mode** (top right).
2. **Load unpacked** → select `apps/extension/dist`.
3. Open any YouTube watch page. Hold **Alt** and drag across the seekbar.
4. Click the YouTube Clipper toolbar icon. Pick **Ollama** or **Azure**. Click **Extract**.

### macOS / Linux

The daemon is plain Python — `uvicorn youtube_clipper.api.app:app` works the
same. The extension build is plain Node + `tsc`. Only the PowerShell wrapper
scripts (`scripts/*.ps1`) are Windows-specific. Equivalent bash is two lines
each — they're on the roadmap but trivial to port for now.

### First clip will be slow

faster-whisper downloads the `medium` model (~770 MB) from HuggingFace the first
time stage 4 runs. After that it's cached. Pre-download with:

```bash
uv run --project apps/daemon python -c "from faster_whisper import WhisperModel; WhisperModel('medium', device='cpu', compute_type='int8')"
```

### CPU vs GPU

Defaults to CPU (`int8`, `medium` model) which works on any modern laptop. If you
have CUDA, swap `config.toml` to `device = "cuda"`, `compute_type = "float16"`,
`model = "large-v3"`. Stage 4 has a CUDA → int8 → CPU auto-fallback chain on
OOM, so misconfigurations degrade gracefully.

### IPv6 gotcha (Windows)

PowerShell resolves `localhost` to `::1` (IPv6) first, but Ollama by default
only binds IPv4. The config uses `http://127.0.0.1:11434` for exactly this
reason. If you ever swap it for `localhost`, expect connection errors.

### Worm-safe npm install

`scripts/install.ps1` runs `npm ci --ignore-scripts` — the propagation vector for
the Shai-Hulud worm and similar npm supply-chain attacks is disabled. Exact-
pinned versions, lockfile committed, GH/NPM tokens stripped from the install
environment. Total npm dependency footprint: 7 packages.

## Anything misbehaving?

```powershell
scripts\doctor.ps1
```

Probes every dependency and prints a green/red table. Exit code 0 iff every
probe is OK. Catches: missing `ffmpeg` / `yt-dlp`, missing `config.toml`,
missing `.secrets.env`, missing extension build, daemon not running, Ollama
not reachable.

## Tech stack, pinned

| Layer | Choice | Why |
|---|---|---|
| Daemon | Python 3.11+, FastAPI, uvicorn, structlog | Async, JSONL logging with `job_id` contextvars |
| Transcription | faster-whisper (`medium` default, swap to `large-v3`) | 4-8x faster than openai/whisper, same accuracy |
| Audio | yt-dlp + ffmpeg | Battle-tested CLI binaries, no Python re-implementation |
| Summarizer | Azure Foundry OR Ollama via `httpx` | Provider-agnostic JSON-mode adapter |
| Extension | TypeScript, Chrome MV3, no bundler | `tsc` + 30-line build script. 7 npm deps total. |
| Templates | Jinja2 (note.md, index.html) | One template per artifact |
| Tests | pytest, pytest-asyncio | 47 tests covering every stage |

## Folder layout

```
YouTube-Clipper/
├── apps/extension/        Chrome MV3 extension (TS + tiny Node build)
├── apps/daemon/           FastAPI pipeline (Python, 47 tests)
├── config/                config.toml + .secrets.env.example
├── scripts/               install / start / stop / doctor (PowerShell)
├── docs/specs/            spec doc
├── docs/plans/            implementation plan
├── docs/runbook.md        recovery + failure modes
├── llm.txt                structured snapshot for LLM consumption
├── MISSION.md             why this exists
├── PROFILE.md             who this is built for
└── output/                clips land here (gitignored)
```

## Design constraints worth knowing

- **`## My Notes` in every `note.md` is sacrosanct.** Re-running the pipeline
  preserves everything from that heading to EOF — it's the user-edited section.
- **Per-stage retry policy** with explicit fallback chains (Whisper CUDA → int8
  → CPU; summarizer 429 → exponential backoff → user prompt to switch backend).
- **Failed jobs are kept on disk**, not deleted. `manifest.json` records which
  stage failed and why. `raw.log` has the full structured trace, grep-able by
  `job_id`.
- **`raw.log` is built post-job** by filtering the daemon's daily JSONL log for
  one `job_id` — every line includes `job_id`, `clip_id`, `stage` via structlog
  contextvars.
- **Idempotent stages.** Every pipeline stage reads its inputs from disk and
  writes its outputs to disk. Re-running skips work that's already done.
  (Foundation for a future "Retry from stage N" UI.)

## Roadmap

- `scripts/*.sh` macOS/Linux equivalents.
- `Retry from stage N` button on failed jobs (the daemon already supports it,
  the popup needs a route).
- Optional `qmd` indexing — push every `note.md` into a local RAG collection so
  you can query across all your clips.
- Optional Obsidian vault destination — already works via `output_dir` override,
  just no UI for vault-aware tagging yet.
- Speaker diarization (Whisper doesn't do this natively; would need pyannote).

## License

MIT — see `LICENSE`. Use it, fork it, ship a teaching empire on top of it.
Attribution is nice.

## Credits

Whisper (OpenAI / SYSTRAN), yt-dlp, ffmpeg, FastAPI, structlog, faster-whisper
(SYSTRAN), Ollama, Azure OpenAI Service. The stack stands on solid open-source
shoulders.

---

Built by [OthmanAdi](https://github.com/OthmanAdi) in Berlin. More tools at
[othmanadi.com](https://othmanadi.com).
