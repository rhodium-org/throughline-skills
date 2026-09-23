"""The scripts drive tl from throughline 3.11.0 or later and refuse an older one.

skill TEST-0009 (shape), tl-challenge TEST-0008 and tl-assess TEST-0010. From
3.11.0 tl composes a graph's sources itself; an older tl reads a sourced graph
without them, so each script exits 2 naming the floor before it reads anything.
A stand-in tl on PATH plays the older release.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

# script, the arguments of a command that runs tl on a graph root
COMMANDS = {
    "shape skill TEST-0009": ("shape.py", ["-C", "{root}", "init"]),
    "tl-challenge TEST-0008": ("challenge.py", ["-C", "{root}", "all"]),
    "tl-assess TEST-0010": ("assess.py", ["graph", "-C", "{root}"]),
}


def stand_in(bin_dir: Path, version: str) -> None:
    bin_dir.mkdir()
    tl = bin_dir / "tl"
    tl.write_text(f"#!/bin/sh\necho 'tl {version}'\n")
    tl.chmod(0o755)


def run(script, args, root, path):
    argv = [sys.executable, str(SCRIPTS / script), *(a.format(root=root) for a in args)]
    env = dict(os.environ, PATH=path)
    return subprocess.run(argv, cwd=root, env=env, text=True, capture_output=True)


@pytest.mark.parametrize("item", COMMANDS)
def test_an_older_tl_is_refused_naming_the_floor(item, tmp_path):
    script, args = COMMANDS[item]
    stand_in(tmp_path / "bin", "3.10.2")
    root = tmp_path / "work"
    root.mkdir()
    r = run(script, args, root, f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}")
    assert r.returncode == 2, r.stdout + r.stderr
    assert "tl 3.10.2 is older than 3.11.0" in r.stderr
    assert "pip install --upgrade 'throughline>=3.11.0'" in r.stderr
    assert list(root.iterdir()) == []            # refused before anything was written


@pytest.mark.parametrize("item", COMMANDS)
def test_no_tl_is_refused_naming_the_install(item, tmp_path):
    script, args = COMMANDS[item]
    (tmp_path / "empty").mkdir()
    root = tmp_path / "work"
    root.mkdir()
    r = run(script, args, root, str(tmp_path / "empty"))
    assert r.returncode == 2, r.stdout + r.stderr
    assert "tl is not on PATH" in r.stderr and "throughline>=3.11.0" in r.stderr


@pytest.mark.parametrize("item", COMMANDS)
def test_the_floor_itself_is_accepted(item, tmp_path):
    script, args = COMMANDS[item]
    stand_in(tmp_path / "bin", "3.11.0")
    root = tmp_path / "work"
    root.mkdir()
    r = run(script, args, root, f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}")
    # The stand-in answers only --version, so the command fails after the
    # floor check; what matters is that the floor did not refuse it.
    assert "older than 3.11.0" not in r.stderr and "not on PATH" not in r.stderr
