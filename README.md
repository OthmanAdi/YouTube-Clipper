# YouTube-Clipper

Mark a range on any YouTube seekbar with Ctrl+drag. Get a markdown note with verbatim transcript, AI summary, bullet points, and the extracted audio. Local-first, Whisper-powered, robust by design.

## Status

**Day 0** — design phase. See:

- `MISSION.md` — north star + success criteria
- `PROFILE.md` — who/why/use-cases
- `docs/specs/2026-05-17-design.md` — the technical design (work in progress)

Implementation has not started. Once the spec is approved, the next step is `writing-plans` to produce a step-by-step implementation plan.

## Project layout (planned)

```
YouTube-Clipper/
├── apps/extension/     Chrome MV3 extension (TS + Vite)
├── apps/daemon/        FastAPI pipeline (Python 3.11)
├── output/             Clip folders land here (note.md + audio.mp3 + transcript.json)
├── logs/               Daily-rotated JSONL pipeline logs
├── config/             config.toml + .secrets.env
├── scripts/            install / start-daemon / doctor
└── docs/specs/         Spec docs by date
```

## Pipeline at a glance

```
[Ctrl+drag on YouTube]
  -> extension sends {url, start_s, end_s, summarizer} to FastAPI daemon
  -> 1. resolve     yt-dlp metadata
  -> 2. download    yt-dlp range
  -> 3. normalize   ffmpeg
  -> 4. transcribe  faster-whisper large-v3 (local)
  -> 5. summarize   Azure Foundry  OR  Ollama (per-clip choice)
  -> 6. write_note  note.md + transcript.json + raw.log
  -> popup: "Done. Open note."
```

Only stage 5 is AI. The other five are pure functions over CLI tools.
