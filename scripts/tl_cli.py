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


def refuse(msg: str) -> None:
    print(f"{Path(sys.argv[0]).stem}: {msg}", file=sys.stderr)
    sys.exit(2)


# tl: implements tl-assess/REQ-0009@2a17db5c5743, tl-challenge/REQ-0008@0a8cc6e25509, skill/REQ-0009@e43dcbfe112b, tl-reconcile/REQ-0011@2a93748c2549
@functools.cache
def require_tl(minimum: tuple[int, int, int] = MINIMUM,
               why: str = "the first release that composes a graph's sources itself") -> str:
    """`tl`, once it is on PATH at ``minimum`` or later; otherwise exit 2 saying why.
    A script that needs a later release names it and what that release first did."""
    floor = ".".join(str(n) for n in minimum)
    upgrade = f"pip install --upgrade 'throughline>={floor}'"
    if shutil.which("tl") is None:
        refuse(f"tl is not on PATH: {upgrade}")
    proc = subprocess.run(["tl", "--version"], capture_output=True, text=True)
    said = (proc.stdout or proc.stderr).strip()
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", said)
    if m is None:
        refuse(f"`tl --version` printed no version ({said!r}): {upgrade}")
    if tuple(int(g) for g in m.groups()) < minimum:
        refuse(f"tl {m.group(0)} is older than {floor}, {why}: {upgrade}")
    return "tl"
