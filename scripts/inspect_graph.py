#!/usr/bin/env python3
"""One item's trace and blast, across every graph in a repository, as a page.

`tl trace` prints what an item rests on and `tl blast` what rests on it, each
inside one graph. This script reads `tl dump` for every graph under a
repository, joins them through their `path` sources, and builds one view of
the item: what it rests on above it, what rests on it below, every item with
its whole content, every link that leaves its graph with the state of its
stamp, and each graph's `tl check` result. It writes that view as JSON, as a
page that stands alone in one file, or as a fragment to show inline.

Standard library only. It writes only the file it is asked for, and never
changes a graph. Needs tl from throughline 5.2.0 or later on PATH.

Usage:
  inspect_graph.py [-C GRAPH] [--repo DIR] [--depth N] [--no-check] UID
                   [--json FILE | --html FILE | --fragment FILE]

It follows two links each way unless --depth says otherwise (0 follows them
all) and says how many items lie beyond. With no output option it prints a summary. FILE may be - for standard output.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from tl_cli import require_tl

FLOOR = (5, 2, 0)
FLOOR_WHY = "the release whose dump this script reads"
TEMPLATE = Path(__file__).resolve().parents[1] / "skills" / "inspect" / "page.html"
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache"}

# Layout, in the page's own units: boxes in rows of at most PER_ROW.
WIDTH, BOX_W, BOX_H, GAP_X, PER_ROW = 680, 150, 56, 16, 4
ROW_GAP, LAYER_GAP, MARGIN = 14, 44, 20


def fail(msg: str) -> None:
    print(f"inspect_graph: {msg}", file=sys.stderr)
    sys.exit(2)


def tl(*args: str, ok=(0,)) -> subprocess.CompletedProcess:
    cmd = [require_tl(FLOOR, FLOOR_WHY), *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode not in ok:
        fail(f"`{' '.join(cmd)}` exited {proc.returncode}: {proc.stderr.strip()}")
    return proc


def repo_of(graph: Path) -> Path:
    """The repository holding the graph: the nearest ancestor with a .git, else the graph."""
    for d in (graph, *graph.parents):
        if (d / ".git").exists():
            return d
    return graph


SOURCES_RE = re.compile(r"^\[\[sources\]\]\s*$(.*?)(?=^\[|\Z)", re.M | re.S)
PATH_RE = re.compile(r"""^\s*path\s*=\s*["']([^"']+)["']""", re.M)


def path_sources(root: Path) -> list[Path]:
    """The graphs a graph borrows from by path, read from its throughline.toml."""
    text = (root / "throughline.toml").read_text(encoding="utf-8")
    return [(root / m.group(1)).resolve()
            for block in SOURCES_RE.findall(text) for m in PATH_RE.finditer(block)]


# tl: implements tl-inspect/REQ-0001@012865cd6da8
def graph_roots(repo: Path, graph: Path) -> list[Path]:
    """The graph and every graph under repo joined to it by path sources, either way round."""
    found = {graph}
    for d, dirs, files in os.walk(repo):
        dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS)
        if "throughline.toml" in files:
            found.add(Path(d).resolve())
    joined = defaultdict(set)
    for root in found:
        for src in path_sources(root):
            if src in found:
                joined[root].add(src)
                joined[src].add(root)
    reached, todo = {graph}, [graph]
    while todo:
        for n in joined[todo.pop()] - reached:
            reached.add(n)
            todo.append(n)
    return sorted(reached)


class Graph:
    def __init__(self, root: Path, repo: Path):
        self.root = root
        try:
            self.rel = root.relative_to(repo).as_posix() or "."
        except ValueError:
            self.rel = root.as_posix()
        self.dump = json.loads(tl("-C", str(root), "dump").stdout)
        cfg = self.dump.get("config", {})
        self.name = cfg.get("project", {}).get("name") or root.name
        roles = cfg.get("status", {}).get("roles", {})
        self.unsigned = {roles.get("initial", "proposed"), roles.get("proposed", "proposed"),
                         roles.get("suspect", "suspect")}
        self.path_sources = {s["namespace"]: (root / s["path"]).resolve()
                             for s in cfg.get("sources", []) if s.get("path")}
        self.items = self.dump.get("items", [])


class View:
    """Every item of every graph under one key, and every link once."""

    def __init__(self, repo: Path, graphs: list[Graph]):
        self.repo = repo
        self.graphs = {g.root: g for g in graphs}
        self.nodes: dict[tuple, dict] = {}
        self.out: dict[tuple, list[dict]] = defaultdict(list)
        self.inc: dict[tuple, list[tuple]] = defaultdict(list)
        # Local items first: an item is described by the graph that owns it.
        for local in (True, False):
            for g in graphs:
                for item in g.items:
                    if ("source" not in item) == local:
                        self._add(g, item)
        for key, links in self.out.items():
            for link in links:
                self.inc[link["to"]].append(key)

    def home(self, g: Graph, ns: str, seen=()) -> Path | None:
        """The graph a namespace names from g, where a path source leads to one."""
        if ns in g.path_sources:
            return g.path_sources[ns]
        for root in g.path_sources.values():
            via = self.graphs.get(root)
            if via is not None and root not in seen:
                found = self.home(via, ns, (*seen, g.root))
                if found is not None:
                    return found
        return None

    def key(self, g: Graph, uid: str) -> tuple:
        if ":" not in uid:
            return (str(g.root), uid)
        ns, local = uid.split(":", 1)
        root = self.home(g, ns)
        if root is not None and root in self.graphs:
            return (str(root), local)
        return (f"source:{ns}", local)

    # tl: implements tl-inspect/REQ-0001@012865cd6da8, tl-inspect/REQ-0002@20a6c4cd589b
    def _add(self, g: Graph, item: dict) -> None:
        key = self.key(g, item["uid"])
        if key in self.nodes:
            return
        owner = self.graphs.get(Path(key[0])) if not key[0].startswith("source:") else None
        signed = [{"by": r.get("by"), "at": r.get("at"), "as": r.get("role")}
                  for r in item.get("ratifications") or []]
        self.nodes[key] = {
            "uid": key[1],
            "graph": owner.name if owner else key[0].split(":", 1)[1],
            "root": owner.rel if owner else None,
            "external": owner is None,
            "type": item.get("type"),
            "status": item.get("status"),
            "unsigned": bool(owner) and item.get("status") in owner.unsigned,
            "title": item.get("title") or "",
            "text": item.get("text") or "",
            "rationale": item.get("rationale") or "",
            "attrs": item.get("attrs") or {},
            "normative": item.get("normative"),
            "fingerprint": item.get("fingerprint"),
            "signed": signed,
        }
        for link in item.get("links") or []:
            self.out[key].append({"to": self.key(g, link["target"]), "type": link.get("type"),
                                  "stamp": link.get("stamp")})

    # tl: implements tl-inspect/REQ-0003@2a1304661a64
    def stamp_state(self, src: tuple, link: dict) -> str | None:
        """current or stale for a stamped link; unstamped for one that leaves its graph bare."""
        target = self.nodes.get(link["to"])
        if link.get("stamp"):
            if target is None or not target.get("fingerprint"):
                return "unknown"
            return "current" if link["stamp"] == target["fingerprint"] else "stale"
        return "unstamped" if link["to"][0] != src[0] else None

    # tl: implements tl-inspect/REQ-0001@012865cd6da8, tl-inspect/REQ-0010@0b22a0ece1da
    def reach(self, start: tuple, step, depth: int) -> tuple[dict[tuple, int], int]:
        """The items within depth links of start by step, each with its distance, and
        how many more lie beyond that depth (none when depth is 0, which follows every link)."""
        dist, frontier = {start: 0}, [start]
        while frontier:
            nxt = []
            for k in frontier:
                for n in step(k):
                    if n not in dist and n in self.nodes:
                        dist[n] = dist[k] + 1
                        nxt.append(n)
            frontier = nxt
        near = {k: d for k, d in dist.items() if not depth or d <= depth}
        return near, len(dist) - len(near)


def layers(view: View, focus: tuple, members: set[tuple], step) -> dict[tuple, int]:
    """Longest distance from the focus inside members, so no link joins two items of one layer."""
    memo: dict[tuple, int] = {focus: 0}
    stack: set[tuple] = set()

    def depth(k: tuple) -> int:
        if k in memo:
            return memo[k]
        if k in stack:
            return 0
        stack.add(k)
        best = max((depth(n) for n in step(k) if n in members or n == focus), default=-1)
        stack.discard(k)
        memo[k] = best + 1
        return memo[k]

    return {k: depth(k) for k in members}


# tl: implements tl-inspect/REQ-0004@bfaeea805767
def place(order: list[list[tuple]]) -> tuple[dict[tuple, tuple[int, int]], int]:
    """A position for every item: each layer in rows of at most PER_ROW, centred, top to bottom."""
    pos, y = {}, MARGIN
    for n, layer in enumerate(order):
        if n:
            y += LAYER_GAP
        rows = [layer[i:i + PER_ROW] for i in range(0, len(layer), PER_ROW)]
        for r, row in enumerate(rows):
            if r:
                y += ROW_GAP
            width = len(row) * BOX_W + (len(row) - 1) * GAP_X
            x = (WIDTH - width) // 2
            for k in row:
                pos[k] = (x, y)
                x += BOX_W + GAP_X
            y += BOX_H
    return pos, y + MARGIN


# tl: implements tl-inspect/REQ-0009@a720ea9e71b5
def check(g: Graph) -> dict:
    proc = tl("-C", str(g.root), "check", ok=(0, 1))
    m = re.search(r"(\d+) error\(s\), (\d+) warning\(s\)", proc.stdout + proc.stderr)
    return {"graph": g.name, "root": g.rel,
            "errors": int(m.group(1)) if m else None,
            "warnings": int(m.group(2)) if m else None}


def ident(key: tuple) -> str:
    return f"{key[0]}#{key[1]}"


def build(args) -> dict:
    graph = Path(args.path).resolve()
    if not (graph / "throughline.toml").is_file():
        fail(f"{graph} holds no throughline.toml: name a graph root with -C")
    repo = Path(args.repo).resolve() if args.repo else repo_of(graph)
    require_tl(FLOOR, FLOOR_WHY)
    with ThreadPoolExecutor() as pool:
        graphs = list(pool.map(lambda r: Graph(r, repo), graph_roots(repo, graph)))
    view = View(repo, graphs)
    here = view.graphs[graph]
    focus = view.key(here, args.uid)
    if focus not in view.nodes:
        fail(f"{args.uid} is not an item of {here.name} ({here.rel})")

    up, up_beyond = view.reach(focus, lambda k: [l["to"] for l in view.out[k]], args.depth)
    down, down_beyond = view.reach(focus, lambda k: view.inc[k], args.depth)
    above = set(up) - {focus}
    below = set(down) - {focus} - above
    up_layer = layers(view, focus, above, lambda k: view.inc[k])
    down_layer = layers(view, focus, below, lambda k: [l["to"] for l in view.out[k]])

    def by_layer(layer: dict[tuple, int], reverse: bool) -> list[list[tuple]]:
        rows = defaultdict(list)
        for k, n in layer.items():
            rows[n].append(k)
        return [sorted(rows[n], key=lambda k: (view.nodes[k]["graph"], k[1]))
                for n in sorted(rows, reverse=reverse)]

    order = by_layer(up_layer, True) + [[focus]] + by_layer(down_layer, False)
    pos, height = place(order)
    shown = set(pos)

    nodes = []
    for k in (k for layer in order for k in layer):
        n = dict(view.nodes[k])
        n["id"] = ident(k)
        n["role"] = "focus" if k == focus else "trace" if k in above else "blast"
        n["other"] = k[0] != focus[0]
        n["x"], n["y"] = pos[k]
        n["links"] = [{"type": l["type"], "to": ident(l["to"]),
                       "target": (view.nodes[l["to"]]["graph"] + "/" if l["to"][0] != k[0] else "")
                                 + l["to"][1] if l["to"] in view.nodes else l["to"][1],
                       "stamp": view.stamp_state(k, l), "shown": l["to"] in shown}
                      for l in view.out[k]]
        nodes.append(n)
    edges = [{"from": ident(k), "to": ident(l["to"]), "type": l["type"],
              "stamp": view.stamp_state(k, l)}
             for k in shown for l in view.out[k] if l["to"] in shown]

    used = {k[0] for k in shown}
    with ThreadPoolExecutor() as pool:
        checks = [] if args.no_check else list(pool.map(check, [g for g in graphs if str(g.root) in used]))
    return {
        "focus": ident(focus),
        "repo": repo.name,
        "depth": args.depth,
        "beyond": {"trace": up_beyond, "blast": down_beyond},
        "size": {"width": WIDTH, "height": height, "box_w": BOX_W, "box_h": BOX_H},
        "nodes": nodes,
        "edges": edges,
        "checks": checks,
    }


# tl: implements tl-inspect/REQ-0005@29bb2a9376a5
def fragment(data: dict) -> str:
    """The page's body with the view in it: one piece of HTML that loads nothing."""
    if not TEMPLATE.is_file():
        fail(f"the page template is missing at {TEMPLATE}")
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.read_text(encoding="utf-8").replace("/*VIEW*/null", payload, 1)


# tl: implements tl-inspect/REQ-0005@29bb2a9376a5
def page(data: dict) -> str:
    focus = next(n for n in data["nodes"] if n["id"] == data["focus"])
    title = f"{focus['graph']}/{focus['uid']}: trace and blast"
    return ("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            f"<title>{title}</title>\n"
            "<style>html{background:#f7f6f2}body{margin:0 auto;max-width:720px;padding:16px;"
            "font-family:system-ui,sans-serif}"
            "@media (prefers-color-scheme:dark){html{background:#1b1b19}}</style>\n"
            "</head>\n<body>\n" + fragment(data) + "\n</body>\n</html>\n")


def summary(data: dict) -> str:
    by = defaultdict(list)
    for n in data["nodes"]:
        by[n["role"]].append(n)
    focus = by["focus"][0]
    lines = [f"{focus['graph']}/{focus['uid']}  [{focus['type']}/{focus['status']}]  {focus['title']}"]
    for role, head in (("trace", "rests on"), ("blast", "rests on it")):
        lines.append(f"{head}: {len(by[role])} item(s)"
                     + (f", {data['beyond'][role]} more beyond depth {data['depth']}"
                        if data["beyond"][role] else ""))
        for n in by[role]:
            mark = "  (unsigned)" if n["unsigned"] else ""
            lines.append(f"  {n['graph']}/{n['uid']}  [{n['type']}/{n['status']}]  {n['title']}{mark}")
    bad = [e for e in data["edges"] if e["stamp"] in ("stale", "unstamped")]
    lines.append(f"links leaving a graph that are stale or unstamped: {len(bad)}")
    for e in bad:
        lines.append(f"  {e['from'].split('#')[1]} -{e['type']}-> {e['to'].split('#')[1]}  {e['stamp']}")
    for c in data["checks"]:
        lines.append(f"tl check {c['root']}: {c['errors']} error(s), {c['warnings']} warning(s)")
    return "\n".join(lines) + "\n"


def emit(text: str, dest: str) -> None:
    if dest == "-":
        sys.stdout.write(text)
    else:
        Path(dest).write_text(text, encoding="utf-8")
        print(f"wrote {dest}", file=sys.stderr)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-C", "--path", default=".", help="the graph root the item is named in (default .)")
    ap.add_argument("--repo", help="the directory searched for graphs (default: the repository holding the graph)")
    ap.add_argument("--depth", type=int, default=2, help="links to follow each way (default 2); 0 follows them all")
    ap.add_argument("--no-check", action="store_true", help="leave out each graph's tl check result")
    ap.add_argument("uid", help="the item, as the graph names it: REQ-0014, or service:REQ-0014 for a borrowed one")
    out = ap.add_mutually_exclusive_group()
    out.add_argument("--json", metavar="FILE", help="write the view as JSON")
    out.add_argument("--html", metavar="FILE", help="write a page that stands alone in one file")
    out.add_argument("--fragment", metavar="FILE", help="write the page's body, to show inline")
    args = ap.parse_args(argv)
    if args.depth < 0:
        fail("--depth cannot be negative")
    # tl: implements tl-inspect/REQ-0008@dc37b2291c1d
    require_tl(FLOOR, FLOOR_WHY)
    data = build(args)
    if args.json:
        emit(json.dumps(data, ensure_ascii=False, indent=1) + "\n", args.json)
    elif args.html:
        emit(page(data), args.html)
    elif args.fragment:
        emit(fragment(data), args.fragment)
    else:
        sys.stdout.write(summary(data))
    return 0


if __name__ == "__main__":
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    sys.exit(main())
