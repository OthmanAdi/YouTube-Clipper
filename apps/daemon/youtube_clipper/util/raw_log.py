"""Post-job: filter the daemon's JSONL pipeline log for one job_id into a per-clip raw.log."""
from __future__ import annotations

import json
from pathlib import Path


def build_raw_log(logs_dir: Path, job_id: str, out_path: Path) -> None:
    out_lines: list[str] = []
    if not logs_dir.exists():
        out_path.write_text("", encoding="utf-8")
        return
    for f in sorted(logs_dir.glob("pipeline.jsonl*")):
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("job_id") == job_id:
                    out_lines.append(line)
        except FileNotFoundError:
            continue
    out_path.write_text(
        "\n".join(out_lines) + ("\n" if out_lines else ""), encoding="utf-8"
    )
