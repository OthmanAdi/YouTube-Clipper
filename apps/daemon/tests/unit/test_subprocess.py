import sys

import pytest

from youtube_clipper.util.subprocess_async import run


@pytest.mark.asyncio
async def test_run_ok():
    res = await run([sys.executable, "-c", "print('hello')"])
    assert res.ok
    assert "hello" in res.stdout


@pytest.mark.asyncio
async def test_run_fail():
    res = await run([sys.executable, "-c", "import sys; sys.exit(2)"])
    assert not res.ok
    assert res.returncode == 2


@pytest.mark.asyncio
async def test_run_stderr_captured():
    res = await run([sys.executable, "-c", "import sys; sys.stderr.write('boom')"])
    assert "boom" in res.stderr
