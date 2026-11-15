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
                   [--json FILE | --html FILE | --fragment FILE | --open]
                   [--fresh]

It follows two links each way unless --depth says otherwise (0 follows them
all) and says how many items lie beyond. With no output option it prints a
summary. FILE may be - for standard output. --html and --fragment also print
the summary on standard error; --fragment adds the fragment's size, and says
when it is too large to be worth showing inline. --open writes the page to the temporary
directory and opens it in the person's browser.

Reading a graph with tl takes seconds, so what tl said of a graph is kept in
the user's cache directory and used again until a file of that graph, of a
graph it borrows from by path, or tl itself changes. --fresh reads every
graph again.
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import json
import os
import re
import shutil
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

# A fragment is shown inline by an assistant writing it out again, a few
# thousand characters a minute. Past this many it is quicker to open the page.
INLINE_LIMIT = 14000


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


CACHE = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "tl-inspect"
KEPT = ("uid", "type", "status", "title", "text", "rationale", "attrs", "normative",
        "fingerprint", "ratifications", "links", "source")


@functools.cache
def tl_stamp() -> str:
    """Which tl is on PATH, told without running it."""
    exe = shutil.which("tl")
    if exe is None:
        require_tl(FLOOR, FLOOR_WHY)
    st = Path(exe).resolve().stat()
    return f"{Path(exe).resolve()}:{st.st_mtime_ns}:{st.st_size}"


# tl: implements tl-inspect/REQ-0008@dc37b2291c1d
def accept_tl() -> None:
    """Refuse a tl that is missing or too old, before anything is read.

    Asking tl its version takes a second, so a tl that has passed is remembered
    by its file's path, time of change and size, and is asked again only when
    one of those differs.
    """
    passed = CACHE / "tl-accepted"
    try:
        if tl_stamp() in passed.read_text(encoding="utf-8").splitlines():
            return
    except OSError:
        pass
    require_tl(FLOOR, FLOOR_WHY)
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        passed.write_text(tl_stamp() + "\n", encoding="utf-8")
    except OSError:
        pass


@functools.cache
def files_state(root: Path) -> str:
    """Every file of one graph by name, time of change and size."""
    lines, todo = [], [str(root)]
    while todo:
        with os.scandir(todo.pop()) as entries:
            for e in entries:
                if e.is_dir(follow_symlinks=False):
                    if e.name not in SKIP_DIRS:
                        todo.append(e.path)
                else:
                    st = e.stat(follow_symlinks=False)
                    lines.append(f"{e.path}:{st.st_mtime_ns}:{st.st_size}")
    return hashlib.sha256("\n".join(sorted(lines)).encode()).hexdigest()


def state(root: Path, seen: tuple = ()) -> str:
    """A graph's files as they stand, and those of every graph it borrows from by path."""
    parts = [files_state(root)]
    for src in path_sources(root):
        if src not in seen and (src / "throughline.toml").is_file():
            parts.append(state(src, (*seen, root)))
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


# tl: implements tl-inspect/REQ-0014@3f0845166cb0
class Graph:
    """What tl says of one graph: read from tl once, then from the cache until the graph changes."""

    def __init__(self, root: Path, repo: Path, fresh: bool = False):
        self.root = root
        self.rootname = str(root)
        try:
            self.rel = root.relative_to(repo).as_posix() or "."
        except ValueError:
            self.rel = root.as_posix()
        self.key = hashlib.sha256(f"{tl_stamp()}\n{state(root)}".encode()).hexdigest()
        self.file = CACHE / (hashlib.sha256(str(root).encode()).hexdigest()[:24] + ".json")
        kept = None if fresh else self._kept()
        if kept is None:
            dump = json.loads(tl("-C", str(root), "dump").stdout)
            cfg = dump.get("config", {})
            roles = cfg.get("status", {}).get("roles", {})
            kept = {
                "key": self.key,
                "name": cfg.get("project", {}).get("name") or root.name,
                "unsigned": sorted({roles.get("initial", "proposed"), roles.get("proposed", "proposed"),
                                    roles.get("suspect", "suspect")}),
                "path_sources": {s["namespace"]: s["path"] for s in cfg.get("sources", []) if s.get("path")},
                "items": [{k: i[k] for k in KEPT if k in i} for i in dump.get("items", [])],
                "check": None,
            }
            self._keep(kept)
        self.kept = kept
        self.name = kept["name"]
        self.unsigned = set(kept["unsigned"])
        self.path_sources = {ns: (root / p).resolve() for ns, p in kept["path_sources"].items()}
        self.items = kept["items"]

    def _kept(self) -> dict | None:
        try:
            kept = json.loads(self.file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return kept if kept.get("key") == self.key else None

    def _keep(self, kept: dict) -> None:
        try:
            CACHE.mkdir(parents=True, exist_ok=True)
            tmp = self.file.with_suffix(f".{os.getpid()}.tmp")
            tmp.write_text(json.dumps(kept, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.file)
        except OSError:
            pass  # a cache that cannot be written costs time, not correctness

    def check(self) -> dict:
        if self.kept["check"] is None:
            proc = tl("-C", str(self.root), "check", ok=(0, 1))
            m = re.search(r"(\d+) error\(s\), (\d+) warning\(s\)", proc.stdout + proc.stderr)
            self.kept["check"] = [int(m.group(1)) if m else None, int(m.group(2)) if m else None]
            self._keep(self.kept)
        errors, warnings = self.kept["check"]
        return {"graph": self.name, "root": self.rel, "errors": errors, "warnings": warnings}


class View:
    """Every item of every graph under one key, and every link once."""

    def __init__(self, repo: Path, graphs: list[Graph]):
        self.repo = repo
        self.graphs = {g.root: g for g in graphs}
        self.owners: dict[tuple, str] = {}
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
            return (g.rootname, uid)
        ns, local = uid.split(":", 1)
        owner = self.owners.get((g.rootname, ns))
        if owner is None:
            root = self.home(g, ns)
            owner = self.owners[(g.rootname, ns)] = (
                str(root) if root is not None and root in self.graphs else f"source:{ns}")
        return (owner, local)

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
    return g.check()


def ident(key: tuple) -> str:
    return f"{key[0]}#{key[1]}"


def build(args) -> dict:
    graph = Path(args.path).resolve()
    if not (graph / "throughline.toml").is_file():
        fail(f"{graph} holds no throughline.toml: name a graph root with -C")
    repo = Path(args.repo).resolve() if args.repo else repo_of(graph)
    with ThreadPoolExecutor() as pool:
        graphs = list(pool.map(lambda r: Graph(r, repo, args.fresh), graph_roots(repo, graph)))
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
             for k in (k for layer in order for k in layer) for l in view.out[k] if l["to"] in shown]

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


STAMPS = {None: 0, "current": 1, "stale": 2, "unstamped": 3}
ROLES = {"trace": 0, "focus": 1, "blast": 2}


# tl: implements tl-inspect/REQ-0011@1ad5cbe2116c
def pack(data: dict) -> dict:
    """The view as the page reads it: every word of every item, and nothing said twice.

    An item is a row. A graph is named once and items point at it; a link to an
    item shown names that item's place in the rows, so no path is repeated and
    the lines between boxes need no list of their own. What the page does not
    show (fingerprints, the repository's name) is left out.
    """
    place = {n["id"]: i for i, n in enumerate(data["nodes"])}
    graphs: list[list] = []

    def graph(n: dict) -> int:
        pair = [n["graph"], n["root"]]
        if pair not in graphs:
            graphs.append(pair)
        return graphs.index(pair)

    rows = [[n["uid"], graph(n), n["type"], n["status"],
             2 if n["external"] else 1 if n["unsigned"] else 0,
             n["title"], n["text"], n["rationale"],
             {k: v for k, v in n["attrs"].items() if v is not None and v != ""},
             [[r["by"], (r["at"] or "")[:10], r["as"] or ""] for r in n["signed"]],
             ROLES[n["role"]], n["x"], n["y"],
             [[l["type"], place[l["to"]] if l["shown"] else l["target"], STAMPS[l["stamp"]]]
              for l in n["links"]]]
            for n in data["nodes"]]
    size = data["size"]
    return {"f": place[data["focus"]], "d": data["depth"],
            "b": [data["beyond"]["trace"], data["beyond"]["blast"]],
            "s": [size["width"], size["height"], size["box_w"], size["box_h"]],
            "g": graphs, "n": rows,
            "c": [[c["graph"], c["errors"], c["warnings"]] for c in data["checks"]]}


# tl: implements tl-inspect/REQ-0005@29bb2a9376a5, tl-inspect/REQ-0011@1ad5cbe2116c
def fragment(data: dict) -> str:
    """The page's body with the view in it: one piece of HTML that loads nothing."""
    if not TEMPLATE.is_file():
        fail(f"the page template is missing at {TEMPLATE}")
    payload = json.dumps(pack(data), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    template = re.sub(r"<!--.*?-->", "", TEMPLATE.read_text(encoding="utf-8"), flags=re.S)
    lines = [l.strip() for l in template.splitlines()]
    return "\n".join(l for l in lines if l).replace("/*VIEW*/null", payload, 1) + "\n"


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


# tl: implements tl-inspect/REQ-0015@97545fcbfcc6
def hosted(data: dict) -> str:
    """The page as a host that wraps it in its own document wants it: a title, the
    page's ground in both themes under the host's theme switch, and the body."""
    focus = next(n for n in data["nodes"] if n["id"] == data["focus"])
    dark = "--ig-ground:#1b1b19;--ig-ink:#f1efe8;color-scheme:dark"
    return (f"<title>{focus['graph']} {focus['uid']} inspected</title>\n"
            '<meta name="claude:viewport-fit-sides" content="cover">\n'
            "<style>:root{--ig-ground:#f7f6f2;--ig-ink:#1b1b19}"
            "@media (prefers-color-scheme:dark){:root:not([data-theme=\"light\"]){" + dark + "}}"
            ":root[data-theme=\"dark\"]{" + dark + "}"
            "body{background:var(--ig-ground);color:var(--ig-ink);font-family:system-ui,sans-serif;"
            "max-width:720px;margin:0 auto;padding-block:16px;"
            "padding-left:max(16px,env(safe-area-inset-left,0px));"
            "padding-right:max(16px,env(safe-area-inset-right,0px))}</style>\n" + fragment(data))


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
    # Inside one graph too: tl from 5.8 stamps a link made with its item, so one
    # there goes stale when its target is reworded, as one leaving a graph does.
    lines.append(f"links that are stale or unstamped: {len(bad)}")
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
    ap.add_argument("--fresh", action="store_true", help="read every graph with tl again, ignoring what was kept")
    ap.add_argument("uid", help="the item, as the graph names it: REQ-0014, or service:REQ-0014 for a borrowed one")
    out = ap.add_mutually_exclusive_group()
    out.add_argument("--json", metavar="FILE", help="write the view as JSON")
    out.add_argument("--html", metavar="FILE", help="write a page that stands alone in one file")
    out.add_argument("--fragment", metavar="FILE", help="write the page's body, to show inline")
    out.add_argument("--open", action="store_true", help="write the page and open it in the browser")
    out.add_argument("--hosted", metavar="FILE",
                     help="write the page for a host that publishes it inside its own document")
    args = ap.parse_args(argv)
    if args.depth < 0:
        fail("--depth cannot be negative")
    accept_tl()
    data = build(args)
    if args.json:
        emit(json.dumps(data, ensure_ascii=False, indent=1) + "\n", args.json)
    elif args.html:
        emit(page(data), args.html)
        print(summary(data), end="", file=sys.stderr)
    elif args.fragment:
        # tl: implements tl-inspect/REQ-0011@1ad5cbe2116c
        body = fragment(data)
        emit(body, args.fragment)
        print(summary(data) + f"fragment: {len(body)} characters", file=sys.stderr)
        if len(body) > INLINE_LIMIT:
            print(f"That is more than the {INLINE_LIMIT} worth writing out inline: "
                  "open the page instead (--open), or draw fewer items (--depth 1).", file=sys.stderr)
    elif args.hosted:
        emit(hosted(data), args.hosted)
        print(summary(data), end="", file=sys.stderr)
    elif args.open:
        # tl: implements tl-inspect/REQ-0012@05cfd6f0a028
        import tempfile
        import webbrowser
        focus = next(n for n in data["nodes"] if n["id"] == data["focus"])
        dest = Path(tempfile.gettempdir()) / f"inspect-{focus['graph']}-{focus['uid']}.html"
        dest.write_text(page(data), encoding="utf-8")
        sys.stdout.write(summary(data))
        opened = webbrowser.open(dest.as_uri())
        print(f"{'opened' if opened else 'wrote; no browser could be opened for'} {dest}")
    else:
        sys.stdout.write(summary(data))
    return 0


if __name__ == "__main__":
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    sys.exit(main())
