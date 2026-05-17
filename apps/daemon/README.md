# YouTube-Clipper Daemon

FastAPI service on `127.0.0.1:7777` that runs the 6-stage clip extraction pipeline.

## Quick start

```powershell
# from the repo root
cd apps\daemon
uv sync --extra dev
uv run pytest

# run the daemon (in dev mode)
$env:YTCLIPPER_CONFIG = "..\..\config\config.toml"
uv run uvicorn youtube_clipper.api.app:app --host 127.0.0.1 --port 7777 --reload
```

## Endpoints

- `GET  /health` — daemon status + summarizer availability
- `POST /clip`   — enqueue a clip extraction: `{url, start_s, end_s, summarizer}` → `{job_id, clip_id}`
- `GET  /jobs/{job_id}` — current job state
- `WS   /events/{job_id}` — live pipeline progress
