"""Thin async subprocess wrapper. Captures stdout/stderr as decoded text."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CompletedProcess:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


async def run(
    args: list[str],
    *,
    cwd: Path | None = None,
    timeout_s: float | None = None,
    capture: bool = True,
) -> CompletedProcess:
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE if capture else None,
        stderr=asyncio.subprocess.PIPE if capture else None,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    return CompletedProcess(
        args=list(args),
        returncode=proc.returncode or 0,
        stdout=(out or b"").decode("utf-8", errors="replace"),
        stderr=(err or b"").decode("utf-8", errors="replace"),
    )
