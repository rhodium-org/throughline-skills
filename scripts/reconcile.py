#!/usr/bin/env python3
"""Deterministic half of reconciling code with its throughline graphs.

Code cites the graph items it serves in one comment notation, in any language:
a comment line opening `tl: implements billing/REQ-0042@3f9a1c0d` above the
code that builds the item, or `tl: verifies billing/TEST-0042` above the test.
SKILL.md gives the grammar in full.

This script reads those citations from the files git tracks and compares them
with the graphs `tl dump` gives: citations that resolve to nothing, accepted
items nothing cites, statuses the code contradicts, test items no test cites,
and stamps written against an item that has since changed. It reports; it
never changes the graph, and changes code only to write the stamps `restamp`
is asked for. Which side of a disagreement moves is the human's call, read in
SKILL.md.

Standard library only. `tl` from throughline 3.11.0 or later must be on PATH.
`scan` exits 0 with findings unless --gate is given; `table --check` exits 1
on a stale table; 2 is a usage error or a refusal.

Usage:
  reconcile.py [-C REPO] scan [PATH...] [--exclude GLOB]... [--graph NAME]...
                 [--types T,..] [--accepted S,..] [--claimed S,..]
                 [--test-type T] [--gate] [--json]
  reconcile.py [-C REPO] table [PATH...] [--exclude GLOB]...
                 [--write FILE | --check FILE]
  reconcile.py [-C REPO] restamp (UID | FILE:LINE) [PATH...] [--exclude GLOB]...
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from tl_cli import require_tl

MARKER = "tl:"
# Longest first, so "<!--" and "//" are not read as "-" or "/".
OPENERS = ("<!--", "/*", "//", "--", "#", ";", "%", "*")
CLOSERS = ("*/", "-->")
LINK_RE = re.compile(r"([a-z][a-z0-9_]*)\s+(\S.*)")
REF_RE = re.compile(
    r"(?:(?P<graph>[A-Za-z0-9][\w.-]*)/)?"
    r"(?P<uid>(?:[A-Za-z][\w-]*:)*[A-Z][A-Z0-9]*-\d+)"
    r"(?:@(?P<stamp>[0-9a-fA-F]+))?")
MIN_STAMP = 8
WRITE_STAMP = 12
BUILDS = ("implements", "satisfies")
BEGIN = "<!-- reconcile:begin -->"
END = "<!-- reconcile:end -->"
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__"}
IGNORE_FILE = ".reconcileignore"

# The order findings are reported in, and what each kind means.
KINDS = {
    "malformed": "a line opening with the marker that does not parse",
    "unknown-link-type": "a link type outside the graph's vocabulary",
    "unknown-graph": "a qualifier naming no graph in this repository",
    "ambiguous-graph": "a qualifier naming more than one graph",
    "unqualified": "a bare UID in a repository holding more than one graph",
    "no-such-item": "a UID the graph does not hold",
    "dead-item": "an item at the graph's invalidated or tombstone status",
    "uncited": "an accepted item no code implements or satisfies",
    "claimed-absent": "an item at an implemented status no code implements",
    "unaccepted": "code implementing an item nobody has accepted",
    "under-question": "code resting on an item at the graph's suspect status",
    "not-wired": "an automated test item no test code verifies",
    "unrecorded-test": "a verifies citation the graph records no test behind",
    "stale": "a stamp written against an edition the item has moved on from",
}


def die(msg: str, code: int = 2) -> None:
    print(f"reconcile: {msg}", file=sys.stderr)
    sys.exit(code)


def git(repo: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and proc.returncode != 0:
        die(f"`git {' '.join(args)}` exited {proc.returncode}: {proc.stderr.strip()}")
    return proc.stdout


def tl_json(graph: Path, *args: str) -> object:
    proc = subprocess.run([require_tl(), "-C", str(graph), *args], capture_output=True, text=True)
    if proc.returncode not in (0, 1) or not proc.stdout.strip():
        die(f"`tl -C {graph} {' '.join(args)}` exited {proc.returncode}: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


# ---------------------------------------------------------------- fingerprints

def _norm(value: object) -> str:
    text = unicodedata.normalize("NFC", str(value)).replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()


# tl: implements tl-reconcile/REQ-0001@efdaeb927f64, tl-reconcile/REQ-0017@3f30a1e93c0b
def fingerprint(item: dict, config: dict) -> str:
    """The SHA-256 tl ratify and tl link --stamp record, recomputed from what
    tl dump carries: the authored UID, type, text, the normative and derived
    flags, and the attributes the schema marks normative, in schema order."""
    uid = item["uid"].rsplit(":", 1)[-1]
    spec = config.get("types", {}).get(item["type"], {}).get("attrs", {})
    names = [n for n, s in spec.items() if isinstance(s, dict) and s.get("normative")]
    parts = [("uid", uid), ("type", item["type"]), ("text", _norm(item.get("text") or "")),
             ("normative", str(item.get("normative", True))),
             ("derived", str(item.get("derived", False)))]
    parts += [(f"attr:{n}", _norm(item.get("attrs", {}).get(n, ""))) for n in names]
    canonical = "\x1e".join(f"{k}\x1f{v}" for k, v in parts)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def hexof(fp: str) -> str:
    return fp.split(":", 1)[-1].lower()


# ---------------------------------------------------------------- graphs

@dataclass
class Graph:
    root: Path
    dump: dict
    name: str = ""
    items: dict = field(default_factory=dict)
    files: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.name = self.dump["config"]["project"]["name"]
        self.items = {i["uid"]: i for i in self.dump["items"]}
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for f in filenames:
                if f.endswith(".yml") and f[:-4] in self.items:
                    self.files[f[:-4]] = Path(dirpath) / f

    @property
    def config(self) -> dict:
        return self.dump["config"]

    def role(self, name: str, default: str) -> str:
        return self.config.get("status", {}).get("roles", {}).get(name, default)

    @property
    def vocabulary(self) -> set:
        return set(self.config.get("links", {}).get("types", []))

    def is_dead(self, item: dict) -> bool:
        return bool(item.get("deleted")) or item.get("status") in (
            self.role("invalidated", "rejected"), self.role("tombstone", "deleted"))

    def local(self) -> list:
        return [i for i in self.dump["items"]
                if not i.get("source") and not self.is_dead(i)]


def find_graphs(repo: Path) -> list[Path]:
    roots = []
    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        if "throughline.toml" in filenames:
            roots.append(Path(dirpath))
    return roots


def signed_fingerprints(item: dict) -> list[str]:
    """The fingerprints the item's signatures recorded: format 4 keeps one on each
    signature in a list beside the item, format 3 one in its attributes."""
    entries = item.get("ratifications")
    if entries is None:
        legacy = item.get("attrs", {}).get("ratified_fingerprint")
        return [legacy] if legacy else []
    return [e["fingerprint"] for e in entries if e.get("fingerprint")]


# tl: implements tl-reconcile/REQ-0017@3f30a1e93c0b
def check_fingerprints(graph: Graph) -> None:
    """Refuse to run when this script's fingerprint disagrees with a
    ratification tl check accepts: tl's algorithm has moved, and every stamp
    would otherwise read as stale."""
    differ = [i for i in graph.local()
              if signed_fingerprints(i)
              and fingerprint(i, graph.config) not in signed_fingerprints(i)]
    if not differ:
        return
    stale = {f.get("uid") for f in tl_json(graph.root, "check", "--format", "json")
             if f.get("rule") == "ratified-stale"}
    wrong = [i["uid"] for i in differ if i["uid"] not in stale]
    if wrong:
        die(f"the fingerprint this script computes for {graph.name} {', '.join(wrong)} "
            "disagrees with the ratification tl accepts — tl's fingerprint has changed "
            "and this script needs updating before it can compare stamps")


def load_graphs(repo: Path) -> list[Graph]:
    require_tl()
    roots = find_graphs(repo)
    if not roots:
        die(f"no throughline graph under {repo}")
    graphs = [Graph(root, tl_json(root, "dump")) for root in roots]
    for g in graphs:
        check_fingerprints(g)
    return graphs


# ---------------------------------------------------------------- citations

@dataclass
class Ref:
    raw: str
    graph: str | None
    uid: str
    stamp: str | None


@dataclass
class Citation:
    path: str
    line: int
    text: str
    link: str | None = None
    refs: list = field(default_factory=list)
    error: str | None = None


# tl: implements tl-reconcile/REQ-0001@efdaeb927f64
def parse_line(text: str, link_types: set) -> tuple | None:
    """None for a line that is not a citation; else (link, refs, error).

    A citation is a line whose content, after leading whitespace and at most
    one comment opener, begins with the marker and then a link type some
    graph declares. A marker line opening with any other word is not a
    citation: tl's own messages open with the same marker. A marker with
    nothing after it, or a link type followed by what does not parse, is an
    error, never a skip."""
    s = text.strip()
    for opener in OPENERS:
        if s.startswith(opener):
            s = s[len(opener):].lstrip()
            break
    if not s.startswith(MARKER):
        return None
    body = s[len(MARKER):].strip()
    for closer in CLOSERS:
        if body.endswith(closer):
            body = body[:-len(closer)].rstrip()
    if not body:
        return None, [], "nothing after the marker"
    first = re.match(r"[a-z][a-z0-9_]*", body)
    if not first or first.group(0) not in link_types:
        return None
    m = LINK_RE.fullmatch(body)
    if not m:
        return first.group(0), [], f"{first.group(0)!r} is followed by no item references"
    link, refs = m.group(1), []
    for raw in (r.strip() for r in m.group(2).split(",")):
        rm = REF_RE.fullmatch(raw)
        if not rm:
            return link, [], f"{raw!r} is not an item reference"
        stamp = rm.group("stamp")
        if stamp is not None and len(stamp) < MIN_STAMP:
            return link, [], f"stamp {stamp!r} on {raw!r} is shorter than {MIN_STAMP} hex digits"
        refs.append(Ref(raw, rm.group("graph"), rm.group("uid"), stamp.lower() if stamp else None))
    return link, refs, None


def excluded(path: str, patterns: list[str]) -> bool:
    parts = path.split("/")
    prefixes = ["/".join(parts[:n]) for n in range(1, len(parts) + 1)]
    return any(fnmatch.fnmatch(p, pat.rstrip("/")) or fnmatch.fnmatch(path, pat)
               for pat in patterns for p in prefixes)


# tl: implements tl-reconcile/REQ-0002@a20ec0186960
def scan_files(repo: Path, paths: list[str], patterns: list[str],
               graphs: list[Graph]) -> tuple[int, list[Citation]]:
    """Every citation in the files git tracks under PATHS, skipping each
    graph's own files, each excluded path and each path .reconcileignore
    names. Returns the files read and the citations found."""
    # A graph nested below the root is skipped whole. A graph at the root holds
    # the code too, so only its own files are: the config and each register.
    roots = [str(g.root.relative_to(repo)).replace(os.sep, "/") for g in graphs]
    skip = [r for r in roots if r != "."]
    if "." in roots:
        skip += ["throughline.toml"] + sorted(
            str(Path(d).relative_to(repo)).replace(os.sep, "/")
            for d, _dirs, files in os.walk(repo) if ".register.yml" in files
            and not set(Path(d).relative_to(repo).parts) & SKIP_DIRS)
    ignore = repo / IGNORE_FILE
    if ignore.is_file():
        skip.append(IGNORE_FILE)
        patterns = patterns + [ln.strip() for ln in ignore.read_text(encoding="utf-8").splitlines()
                               if ln.strip() and not ln.strip().startswith("#")]
    link_types = set().union(*(g.vocabulary for g in graphs))
    listed = git(repo, "ls-files", "-z", "--", *(paths or ["."])).split("\0")
    read, found = 0, []
    for rel in sorted(p for p in listed if p):
        if any(rel == r or rel.startswith(r + "/") for r in skip):
            continue
        if excluded(rel, patterns):
            continue
        try:
            text = (repo / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        read += 1
        for n, line in enumerate(text.splitlines(), 1):
            parsed = parse_line(line, link_types)
            if parsed is not None:
                link, refs, error = parsed
                found.append(Citation(rel, n, line.strip(), link, refs, error))
    return read, found


# ---------------------------------------------------------------- resolution

@dataclass
class Finding:
    kind: str
    path: str | None
    line: int | None
    ref: str
    message: str
    code: str | None = None
    item: str | None = None

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


def describe(item: dict) -> str:
    return f"[{item.get('status')}] {item.get('title')}"


def display(graph: Graph, uid: str, graphs: list[Graph]) -> str:
    return f"{graph.name}/{uid}" if len(graphs) > 1 else uid


# tl: implements tl-reconcile/REQ-0003@349d841068d4
def resolve(ref: Ref, link: str, graphs: list[Graph]) -> tuple:
    """(graph, item, None) for a ref to a live item, else (graph?, item?, (kind, why))."""
    if ref.graph:
        named = [g for g in graphs if g.name == ref.graph]
        if not named:
            return None, None, ("unknown-graph", f"no graph in this repository is named {ref.graph!r}")
        if len(named) > 1:
            return None, None, ("ambiguous-graph", f"{len(named)} graphs are named {ref.graph!r}: "
                                + ", ".join(str(g.root) for g in named))
        graph = named[0]
    elif len(graphs) > 1:
        return None, None, ("unqualified", f"this repository holds {len(graphs)} graphs; name one, "
                            f"as in <graph>/{ref.uid} (graphs: "
                            + ", ".join(sorted(g.name for g in graphs)) + ")")
    else:
        graph = graphs[0]
    item = graph.items.get(ref.uid)
    if item is None:
        return graph, None, ("no-such-item", f"{graph.name} holds no item {ref.uid}")
    if graph.is_dead(item):
        return graph, item, ("dead-item", f"{ref.uid} is {item.get('status')} in {graph.name}")
    if link not in graph.vocabulary:
        return graph, item, ("unknown-link-type",
                             f"{link!r} is not in {graph.name}'s link vocabulary: "
                             + ", ".join(sorted(graph.vocabulary)))
    return graph, item, None


@dataclass
class Resolved:
    citation: Citation
    ref: Ref
    graph: Graph
    item: dict


def resolve_all(citations: list[Citation], graphs: list[Graph]) -> tuple[list, list]:
    findings, resolved = [], []
    for c in citations:
        if c.error:
            findings.append(Finding("malformed", c.path, c.line, "", c.error, c.text))
            continue
        for ref in c.refs:
            graph, item, problem = resolve(ref, c.link, graphs)
            if problem:
                kind, why = problem
                findings.append(Finding(kind, c.path, c.line, ref.raw, why, c.text,
                                        describe(item) if item else None))
            else:
                resolved.append(Resolved(c, ref, graph, item))
    return findings, resolved


def uid_key(uid: str) -> tuple:
    m = re.match(r"(.*?)(\d+)$", uid)
    return (m.group(1), int(m.group(2))) if m else (uid, 0)


# ---------------------------------------------------------------- graph-side checks

# tl: implements tl-reconcile/REQ-0004@106eb6ca501d, tl-reconcile/REQ-0005@31cf438bda21, tl-reconcile/REQ-0006@3ddd98e35ec8
def graph_findings(graphs: list[Graph], resolved: list[Resolved], a) -> tuple[list, list]:
    """Findings that start from the graph: what nothing cites, what is claimed
    built and is not, what code builds that nobody accepted, and the tests.
    Local items only: a borrowed item is its owner's to account for."""
    built = defaultdict(set)        # graph name -> UIDs code implements or satisfies
    verified = defaultdict(set)     # graph name -> UIDs code verifies
    for r in resolved:
        if r.citation.link in BUILDS:
            built[r.graph.name].add(r.ref.uid)
        elif r.citation.link == "verifies":
            verified[r.graph.name].add(r.ref.uid)

    findings, through_children = [], []
    scope = [g for g in graphs if not a.graph or g.name in a.graph]
    for g in scope:
        statuses = set(g.config.get("status", {}).get("values", []))
        types = set(a.types.split(",")) if a.types else {"requirement"}
        accepted = set(a.accepted.split(",")) if a.accepted else \
            {"approved", "ratified", "implemented", "verified"} & statuses
        claimed = set(a.claimed.split(",")) if a.claimed else {"implemented", "verified"} & statuses
        live = g.local()
        children = defaultdict(set)
        for i in live:
            for link in i.get("links", []):
                if link.get("type") in ("refines", "derives_from"):
                    children[link["target"]].add(i["uid"])

        def below(uid: str) -> set:
            seen, todo = set(), list(children[uid])
            while todo:
                u = todo.pop()
                if u not in seen:
                    seen.add(u)
                    todo.extend(children[u])
            return seen

        for i in sorted(live, key=lambda i: uid_key(i["uid"])):
            uid, ref = i["uid"], display(g, i["uid"], graphs)
            if uid in built[g.name]:
                continue
            if i["type"] in types and i.get("status") in accepted:
                cited_below = sorted(below(uid) & built[g.name], key=uid_key)
                if cited_below:
                    through_children.append(Finding(
                        "realised-through-children", None, None, ref,
                        "cited below it: " + ", ".join(cited_below), item=describe(i)))
                else:
                    findings.append(Finding("uncited", None, None, ref,
                                            "no implements or satisfies citation names it or "
                                            "anything below it", item=describe(i)))
            if i.get("status") in claimed and i["type"] != a.test_type:
                findings.append(Finding("claimed-absent", None, None, ref,
                                        f"it is {i['status']} and no code implements or satisfies it",
                                        item=describe(i)))
            if (i["type"] == a.test_type and i.get("attrs", {}).get("method") == "automated"
                    and uid not in verified[g.name]):
                findings.append(Finding("not-wired", None, None, ref,
                                        "an automated test item no verifies citation names",
                                        item=describe(i)))

        unaccepted = {g.role("initial", "draft"), g.role("proposed", "proposed"), "deferred"}
        suspect = g.role("suspect", "suspect")
        tested = {link["target"] for i in live if i["type"] == a.test_type
                  for link in i.get("links", []) if link.get("type") == "verifies"}
        for r in resolved:
            if r.graph is not g:
                continue
            ref, status = display(g, r.ref.uid, graphs), r.item.get("status")
            where = (r.citation.path, r.citation.line)
            if r.citation.link in BUILDS and status in unaccepted:
                findings.append(Finding("unaccepted", *where, ref,
                                        f"the code builds an item at {status}, which nobody has accepted",
                                        r.citation.text, describe(r.item)))
            if r.citation.link in BUILDS and status == suspect:
                findings.append(Finding("under-question", *where, ref,
                                        "the code rests on an item under question",
                                        r.citation.text, describe(r.item)))
            if r.citation.link == "verifies" and not r.item.get("source"):
                if r.item["type"] == a.test_type:
                    if not any(link.get("type") == "verifies" for link in r.item.get("links", [])):
                        findings.append(Finding("unrecorded-test", *where, ref,
                                                "the test item verifies nothing in its graph",
                                                r.citation.text, describe(r.item)))
                elif r.ref.uid not in tested:
                    findings.append(Finding("unrecorded-test", *where, ref,
                                            "no test item in the graph verifies this item",
                                            r.citation.text, describe(r.item)))
    return findings, through_children


# ---------------------------------------------------------------- stamps

def item_rel(repo: Path, r: Resolved) -> str | None:
    f = r.graph.files.get(r.ref.uid)
    return str(f.relative_to(repo)).replace(os.sep, "/") if f and not r.item.get("source") else None


def strip_sources(toml_text: str) -> str:
    """The config without its [[sources]] tables: a local item's fingerprint
    reads none of them, and an old edition's sources may no longer resolve."""
    out, skipping = [], False
    for line in toml_text.splitlines(keepends=True):
        head = line.strip()
        if head.startswith("["):
            skipping = head == "[[sources]]"
        if not skipping:
            out.append(line)
    return "".join(out)


# tl: implements tl-reconcile/REQ-0007@6a1d3a105819
def stamped_edition(repo: Path, r: Resolved, cache: dict) -> str | None:
    """The commit whose edition of the item the stamp was taken from, found by
    dumping the graph as each commit touching the item's file held it."""
    rel = item_rel(repo, r)
    if rel is None:
        return None
    suffix = str(r.graph.files[r.ref.uid].relative_to(r.graph.root)).replace(os.sep, "/")
    # Each commit prints its hash, then the item's path as that commit held it.
    log = git(repo, "log", "--follow", "--format=%H", "--name-only", "--", rel, check=False)
    lines = [ln for ln in log.splitlines() if ln.strip()]
    for commit, path in zip(lines[0::2], lines[1::2]):
        if not path.endswith(suffix):
            continue
        root = path[: -len(suffix)].rstrip("/")
        key = (commit, root, r.ref.uid)
        if key not in cache:
            cache[key] = edition_fingerprint(repo, commit, root, r.ref.uid)
        fp = cache[key]
        if fp and hexof(fp).startswith(r.ref.stamp):
            return commit[:12]
    return None


def edition_fingerprint(repo: Path, commit: str, root: str, uid: str) -> str | None:
    archive = subprocess.run(["git", "-C", str(repo), "archive", commit, "--", root or "."],
                             capture_output=True)
    if archive.returncode != 0:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
            try:
                tar.extractall(tmp, filter="data")
            except TypeError:                       # Python before the filter argument
                tar.extractall(tmp)
        graph = Path(tmp) / root
        cfg = graph / "throughline.toml"
        if not cfg.exists():
            return None
        cfg.write_text(strip_sources(cfg.read_text()))
        proc = subprocess.run([require_tl(), "-C", str(graph), "dump", "--local"],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            return None
        dump = json.loads(proc.stdout)
        item = next((i for i in dump["items"] if i["uid"] == uid), None)
        return fingerprint(item, dump["config"]) if item else None


def stamp_findings(repo: Path, resolved: list[Resolved], graphs: list[Graph]) -> list:
    findings, cache = [], {}
    for r in resolved:
        if r.ref.stamp is None:
            continue
        current = hexof(fingerprint(r.item, r.graph.config))
        if current.startswith(r.ref.stamp):
            continue
        commit = stamped_edition(repo, r, cache)
        rel = item_rel(repo, r)
        then = (f"stamped against the edition in commit {commit}; compare with "
                f"`git diff {commit} -- {rel}`" if commit else
                "no commit in the item's history holds the stamped edition")
        findings.append(Finding("stale", r.citation.path, r.citation.line,
                                display(r.graph, r.ref.uid, graphs),
                                f"the item has changed since the stamp ({r.ref.stamp} → "
                                f"{current[:WRITE_STAMP]}); {then}",
                                r.citation.text, describe(r.item)))
    return findings


def commit_time(repo: Path, *args: str) -> int:
    out = git(repo, *args, check=False).strip()
    return int(out) if out.isdigit() else 0


# tl: implements tl-reconcile/REQ-0009@bb02cd099748
def review_order(repo: Path, resolved: list[Resolved], graphs: list[Graph]) -> list[dict]:
    """Unstamped citations, those whose item changed after the cited line
    first. A weak signal for where to start reading, never a finding."""
    rows = []
    for r in resolved:
        rel = item_rel(repo, r)
        if r.ref.stamp is not None or rel is None:
            continue
        item_t = commit_time(repo, "log", "-1", "--format=%ct", "--", rel)
        blame = git(repo, "blame", "--porcelain", "-L", f"{r.citation.line},{r.citation.line}",
                    "--", r.citation.path, check=False)
        m = re.search(r"^committer-time (\d+)$", blame, re.M)
        line_t = int(m.group(1)) if m else 0
        rows.append({"path": r.citation.path, "line": r.citation.line,
                     "ref": display(r.graph, r.ref.uid, graphs),
                     "item_changed_after_code": item_t > line_t})
    return sorted(rows, key=lambda row: not row["item_changed_after_code"])


# ---------------------------------------------------------------- commands

def collect(repo: Path, a) -> tuple:
    graphs = load_graphs(repo)
    files, citations = scan_files(repo, a.paths, a.exclude or [], graphs)
    findings, resolved = resolve_all(citations, graphs)
    return graphs, files, citations, findings, resolved


def print_finding(f: Finding) -> None:
    where = f" {f.path}:{f.line}" if f.path else ""
    ref = f" {f.ref}" if f.ref else ""
    print(f"  {f.kind}{where}{ref} — {f.message}")
    if f.item:
        print(f"      item: {f.item}")
    if f.code:
        print(f"      code: {f.code}")


# tl: implements tl-reconcile/REQ-0011@2a93748c2549
def cmd_scan(repo: Path, a) -> None:
    graphs, files, citations, findings, resolved = collect(repo, a)
    more, through_children = graph_findings(graphs, resolved, a)
    findings += more + stamp_findings(repo, resolved, graphs)
    order = list(KINDS)
    findings.sort(key=lambda f: (order.index(f.kind), f.path or "", f.line or 0, f.ref))
    refs = [ref for c in citations for ref in c.refs]
    stamped = sum(1 for ref in refs if ref.stamp)
    review = review_order(repo, resolved, graphs)
    if a.json:
        print(json.dumps({
            "files": files, "citations": len(citations), "references": len(refs),
            "stamped": stamped, "graphs": [g.name for g in graphs],
            "findings": [f.as_dict() for f in findings],
            "realised_through_children": [f.as_dict() for f in through_children],
            "review_order": review}, indent=2))
    else:
        print(f"read {files} file(s), found {len(citations)} citation(s) naming "
              f"{len(refs)} item reference(s) ({stamped} stamped, {len(refs) - stamped} unstamped) "
              f"against {len(graphs)} graph(s)")
        print(f"\nfindings ({len(findings)}):")
        for f in findings:
            print_finding(f)
        if through_children:
            print(f"\nrealised through children — listed, not findings ({len(through_children)}):")
            for f in through_children:
                print_finding(f)
        if review:
            print("\nreview order for unstamped citations, item changed after the code first "
                  "— not findings:")
            for row in review:
                mark = "item changed after code" if row["item_changed_after_code"] else "code is newer"
                print(f"  {row['path']}:{row['line']} {row['ref']} ({mark})")
    sys.exit(1 if a.gate and findings else 0)


# tl: implements tl-reconcile/REQ-0010@03b6f6ba7aeb
def render_table(resolved: list[Resolved], graphs: list[Graph]) -> str:
    rows = sorted({(r.graph.name, uid_key(r.ref.uid), display(r.graph, r.ref.uid, graphs),
                    r.item.get("title", ""), r.citation.link, r.citation.path, r.citation.line)
                   for r in resolved})
    out = ["| Item | Title | Link | Location |", "|---|---|---|---|"]
    for _g, _k, ref, title, link, path, line in rows:
        title = title.replace("|", "\\|")
        out.append(f"| `{ref}` | {title} | {link} | `{path}:{line}` |")
    return "\n".join(out) + "\n"


def between_markers(text: str) -> tuple[int, int] | None:
    b, e = text.find(BEGIN), text.find(END)
    if b < 0 or e < b:
        return None
    return b + len(BEGIN), e


def cmd_table(repo: Path, a) -> None:
    graphs, _files, _citations, _findings, resolved = collect(repo, a)
    table = render_table(resolved, graphs)
    target = a.write or a.check
    if not target:
        sys.stdout.write(table)
        return
    path = repo / target
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    span = between_markers(text)
    if span is None:
        die(f"{target} holds no `{BEGIN}` … `{END}` pair to put the table between")
    current = text[span[0]:span[1]].strip("\n") + "\n"
    if a.check:
        if current != table:
            print(f"{target}: the citation table is stale — regenerate it with "
                  f"`table --write {target}`", file=sys.stderr)
            sys.exit(1)
        print(f"{target}: the citation table is current")
        return
    path.write_text(text[:span[0]] + "\n" + table + text[span[1]:], encoding="utf-8")
    print(f"wrote the citation table ({table.count(chr(10)) - 2} row(s)) to {target}")


# tl: implements tl-reconcile/REQ-0008@6f63bce2f150
def cmd_restamp(repo: Path, a) -> None:
    """Stamp the citations of one item, or of one file and line, with the
    item's current fingerprint. Deliberately no form that stamps everything."""
    graphs, _files, _citations, _findings, resolved = collect(repo, a)
    target = a.target
    m = re.fullmatch(r"(.+):(\d+)", target)
    if m and (repo / m.group(1)).is_file():
        chosen = [r for r in resolved
                  if r.citation.path == m.group(1) and r.citation.line == int(m.group(2))]
    else:
        rm = REF_RE.fullmatch(target)
        if not rm or rm.group("stamp"):
            die(f"{target!r} is neither an item reference nor FILE:LINE")
        graph, item, problem = resolve(Ref(target, rm.group("graph"), rm.group("uid"), None),
                                       "implements", graphs)
        if problem and problem[0] != "unknown-link-type":
            die(problem[1])
        chosen = [r for r in resolved if r.graph is graph and r.ref.uid == rm.group("uid")]
    if not chosen:
        die(f"no resolving citation of {target} in the files scanned", 1)
    by_file = defaultdict(list)
    for r in chosen:
        by_file[r.citation.path].append(r)
    for rel, rs in sorted(by_file.items()):
        path = repo / rel
        with path.open(encoding="utf-8", newline="") as fh:
            lines = fh.read().splitlines(keepends=True)
        for r in sorted(rs, key=lambda r: r.citation.line):
            text = lines[r.citation.line - 1]
            pos = text.index(MARKER) + len(MARKER)
            idx = text.index(r.ref.raw, pos)
            base = r.ref.raw.split("@", 1)[0]
            new = f"{base}@{hexof(fingerprint(r.item, r.graph.config))[:WRITE_STAMP]}"
            lines[r.citation.line - 1] = text[:idx] + new + text[idx + len(r.ref.raw):]
            print(f"restamped {rel}:{r.citation.line} {r.ref.raw} → {new}")
        with path.open("w", encoding="utf-8", newline="") as fh:
            fh.write("".join(lines))


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog="Usage:" + __doc__.split("Usage:")[1])
    p.add_argument("-C", "--repo", default=".", help="repository root (default: .)")
    sub = p.add_subparsers(dest="command", required=True)

    def scoped(name: str) -> argparse.ArgumentParser:
        s = sub.add_parser(name)
        s.add_argument("paths", nargs="*", help="paths to scan (default: the whole repository)")
        s.add_argument("--exclude", action="append", metavar="GLOB",
                       help="skip paths matching GLOB (repeatable)")
        return s

    s = scoped("scan")
    s.add_argument("--graph", action="append", metavar="NAME",
                   help="report graph-side findings for this graph only (repeatable)")
    s.add_argument("--types", help="implementable item types (default: requirement)")
    s.add_argument("--accepted", help="statuses an item must be cited at "
                                      "(default: approved,ratified,implemented,verified)")
    s.add_argument("--claimed", help="statuses that claim code exists (default: implemented,verified)")
    s.add_argument("--test-type", default="test", help="the item type of tests (default: test)")
    s.add_argument("--gate", action="store_true", help="exit 1 when any finding stands")
    s.add_argument("--json", action="store_true")
    t = scoped("table")
    g = t.add_mutually_exclusive_group()
    g.add_argument("--write", metavar="FILE", help="write the table between the markers in FILE")
    g.add_argument("--check", metavar="FILE", help="exit 1 when the table in FILE is stale")
    r = sub.add_parser("restamp")
    r.add_argument("target", help="an item reference, or FILE:LINE")
    r.add_argument("paths", nargs="*")
    r.add_argument("--exclude", action="append", metavar="GLOB")
    a = p.parse_args(argv)
    require_tl()                    # the floor first, before anything is read
    repo = Path(a.repo).resolve()
    try:
        top = subprocess.run(["git", "-C", str(repo), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True)
    except FileNotFoundError:
        die("git is not on PATH; the scan reads the files git tracks")
    if top.returncode != 0:
        die(f"{repo} is not inside a git repository; the scan reads the files git tracks")
    repo = Path(top.stdout.strip())
    {"scan": cmd_scan, "table": cmd_table, "restamp": cmd_restamp}[a.command](repo, a)


if __name__ == "__main__":
    main()
