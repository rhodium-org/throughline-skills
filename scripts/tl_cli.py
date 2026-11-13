"""The throughline CLI the scripts drive, held to the plugin's one floor.

The floor is throughline 5.2.0, the oldest release the plugin's tests run
against. `tl` composes the `path` and `url` sources a graph declares, so one
command drives every graph, sourced or not. A script refuses an older `tl`
rather than report on a graph it may read differently, or only in part.

Standard library only.
"""
from __future__ import annotations

import functools
import re
import shutil
import subprocess
import sys
from pathlib import Path

MINIMUM = (5, 2, 0)


def refuse(msg: str) -> None:
    print(f"{Path(sys.argv[0]).stem}: {msg}", file=sys.stderr)
    sys.exit(2)


# tl: implements tl-assess/REQ-0009@58982b050797, tl-challenge/REQ-0008@f4a711abf8c5, skill/REQ-0009@a420ad5b6ca7, tl-reconcile/REQ-0011@18c3a13c5389
@functools.cache
def require_tl(minimum: tuple[int, int, int] = MINIMUM,
               why: str = "the oldest release these skills are tested against") -> str:
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
