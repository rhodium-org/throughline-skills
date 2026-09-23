"""The throughline CLI the scripts drive, held to the release that composes.

From throughline 3.11.0 `tl` composes the `path` and `url` sources a graph
declares, so one command drives every graph, sourced or not. An older `tl`
reads a sourced graph without its sources and reports every namespace:UID link
as unresolved, so a script refuses it rather than report on half a graph.

Standard library only.
"""
from __future__ import annotations

import functools
import re
import shutil
import subprocess
import sys
from pathlib import Path

MINIMUM = (3, 11, 0)
UPGRADE = "pip install --upgrade 'throughline>=3.11.0'"


def refuse(msg: str) -> None:
    print(f"{Path(sys.argv[0]).stem}: {msg}", file=sys.stderr)
    sys.exit(2)


@functools.cache
def require_tl() -> str:
    """`tl`, once it is on PATH at MINIMUM or later; otherwise exit 2 saying why."""
    if shutil.which("tl") is None:
        refuse(f"tl is not on PATH: {UPGRADE}")
    proc = subprocess.run(["tl", "--version"], capture_output=True, text=True)
    said = (proc.stdout or proc.stderr).strip()
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", said)
    if m is None:
        refuse(f"`tl --version` printed no version ({said!r}): {UPGRADE}")
    if tuple(int(g) for g in m.groups()) < MINIMUM:
        refuse(f"tl {m.group(0)} is older than 3.11.0, the first release that composes "
               f"a graph's sources itself: {UPGRADE}")
    return "tl"
