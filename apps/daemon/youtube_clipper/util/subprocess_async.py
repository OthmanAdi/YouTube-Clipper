"""Thin async subprocess wrapper. Captures stdout/stderr. Tree-kills on timeout."""
from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_IS_WINDOWS = sys.platform == "win32"


@dataclass
class CompletedProcess:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def _kill_tree(pid: int) -> None:
    """Kill the process and ALL its descendants.

    Required because yt-dlp can spawn ffmpeg internally; killing only yt-dlp leaves ffmpeg
    holding the stdout/stderr pipes open, which makes asyncio.proc.communicate() hang
    indefinitely after a timeout. This is the bug that made stage 2 appear stuck for 8+
    minutes on a 9-minute clip.
    """
    if _IS_WINDOWS:
        # taskkill /T = include child processes; /F = force.
        try:
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
        except Exception:
            pass
    else:
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except Exception:
            try:
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass


async def run(
    args: list[str],
    *,
    cwd: Path | None = None,
    timeout_s: float | None = None,
    capture: bool = True,
) -> CompletedProcess:
    extra_kw: dict = {}
    if not _IS_WINDOWS:
        # On POSIX, start a new session so we can killpg() the whole group on timeout.
        extra_kw["start_new_session"] = True

    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE if capture else None,
        stderr=asyncio.subprocess.PIPE if capture else None,
        **extra_kw,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        # The orphan-child problem: we MUST kill the whole tree, otherwise grandchildren
        # (e.g. ffmpeg launched by yt-dlp) keep the inherited pipe open and proc.wait()
        # blocks indefinitely.
        _kill_tree(proc.pid)
        # Best-effort wait, capped so we don't hang here either.
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            pass
        raise
    return CompletedProcess(
        args=list(args),
        returncode=proc.returncode or 0,
        stdout=(out or b"").decode("utf-8", errors="replace"),
        stderr=(err or b"").decode("utf-8", errors="replace"),
    )
