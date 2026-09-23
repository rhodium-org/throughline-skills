#!/usr/bin/env python3
"""Deterministic half of a throughline challenge pass.

Reads a project as the JSON that `tl dump` emits and reports the checks that
need no judgement. The semantic checks (link strength,
sibling naming, a rationale narrower than its family) are left to the reader;
`siblings` prints the material they need held together.

Standard library only. Every command exits 0; the output is a review list, not a
gate. Run `all` for the graph-wide checks, `siblings UID` for one item. Given a
graph root it runs `tl` from throughline 3.11.0 or later, which composes the
graph's sources, and exits 2 on an older one.

Usage:
  challenge.py [-C PATH | --dump FILE] <command> [options]

Commands:
  mentions      prose names an item by UID but records no link to it
  universal     universal language with one or no grounded child
  verification  how each branch is verified; branches with no automated test
  failure-case  normative items whose text never says what a violation is
  untestable    normative items whose predicate no observation could settle
  replacement   live items carrying a link whose NAME reads as replacement
  unstamped     local links into a source that carry no stamp
  uncovered     borrowed items of given types with no incoming local link
  siblings UID  every parent of UID and the other children under each
  all           mentions, universal, verification, failure-case, untestable,
                replacement, unstamped
"""
from __future__ import annotations

import argparse
import json
import re
import signal
import subprocess
import sys
from collections import defaultdict

from tl_cli import require_tl

UID_RE = re.compile(r"(?<![\w:])(?:([A-Za-z][\w-]*):)?([A-Z][A-Z0-9]*-\d{3,})\b")
UNIVERSAL_RE = re.compile(
    r"\b(always|never|every|all|none|nothing|no [\w-]+ at all|anywhere|"
    r"nowhere|whenever)\b", re.I)
NEGATIVE_RE = re.compile(
    r"\b(never|not|no|nothing|nobody|nowhere|without|refus\w*|reject\w*|"
    r"fail\w*|block\w*|cannot|can't|must not|shall not|only|unless|"
    r"until|except|forbid\w*|prohibit\w*|denied|deny)\b", re.I)
VAGUE_WORDS = [
    "appropriate", "adequate", "reasonable", "suitable", "sufficient",
    "user-friendly", "intuitive", "easy", "simple", "clear", "clearly",
    "legible", "readable", "sparingly", "designed", "well-designed",
    "elegant", "clean", "robust", "efficient", "fast", "quickly",
    "as needed", "where possible", "if possible", "etc",
]
REPLACEMENT_NAME_RE = re.compile(
    r"supersed|replac|obsolet|deprecat|irrelevant|retire", re.I)


def load(args) -> dict:
    if args.dump:
        with open(args.dump) as fh:
            return json.load(fh)
    cmd = [require_tl(), "-C", args.path, "dump"]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(f"`{' '.join(cmd)}` exited {out.returncode}: {out.stderr.strip()}; "
                 "pass --dump FILE")
    return json.loads(out.stdout)


class Graph:
    def __init__(self, dump: dict):
        self.dump = dump
        self.config = dump.get("config", {})
        self.items = {i["uid"]: i for i in dump.get("items", [])}
        g = self.config.get("grounding", {})
        self.ground_types = set(g.get("ground_link_types", []))
        self.root_types = set(g.get("root_types", []))
        self.delivery_roots = set(g.get("delivery_roots", []))
        self.incoming: dict[str, list[tuple[str, dict]]] = defaultdict(list)
        for uid, item in self.items.items():
            for link in item.get("links", []) or []:
                self.incoming[link.get("target", "")].append((uid, link))

    def is_local(self, uid: str) -> bool:
        return ":" not in uid

    def live(self, item: dict) -> bool:
        return item.get("status") not in ("deleted", "rejected")

    def text_of(self, item: dict) -> str:
        return " ".join(str(item.get(k) or "") for k in ("title", "text", "rationale"))

    def children(self, uid: str) -> list[str]:
        """Items grounded to uid through a grounding link type."""
        return [src for src, link in self.incoming.get(uid, [])
                if link.get("type") in self.ground_types]

    def parents(self, item: dict) -> list[tuple[str, str]]:
        return [(l.get("target", ""), l.get("type", ""))
                for l in item.get("links", []) or []]


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


# ── commands ────────────────────────────────────────────────────────────────

def in_path(sent: str, m: "re.Match") -> bool:
    """A UID-shaped token that is part of a file path: preceded by a path
    separator, or followed by a file extension (REQ-0002)."""
    before = sent[m.start() - 1] if m.start() > 0 else ""
    # Tuple membership: an empty `before` (token starts the sentence) is a
    # substring of every string, so a plain `in "/\\"` test would call every
    # sentence-initial UID a path.
    return before in ("/", "\\") or re.match(r"\.\w", sent[m.end():m.end() + 2]) is not None


def cmd_mentions(g: Graph, args) -> None:
    """REQ-0002: a UID in prose with no matching link edge. A token inside a
    file path is a path mention, listed apart and not counted as a citation."""
    n = 0
    paths = 0
    for uid, item in g.items.items():
        if args.local_only and not g.is_local(uid):
            continue
        if not g.live(item):
            continue
        linked = {l.get("target") for l in item.get("links", []) or []}
        reported: set[tuple[str, str]] = set()
        for field in ("text", "rationale"):
            for sent in sentences(str(item.get(field) or "")):
                for m in UID_RE.finditer(sent):
                    ns, bare = m.group(1), m.group(2)
                    if not ns and ":" in uid:
                        ns = uid.split(":", 1)[0]  # a borrowed item names its own graph
                    cited = f"{ns}:{bare}" if ns else bare
                    if cited == uid or cited not in g.items or cited in linked:
                        continue
                    if (cited, sent) in reported:
                        continue
                    reported.add((cited, sent))
                    if in_path(sent, m):
                        # A file may be named after a local or a borrowed item
                        # that shares the UID; name every candidate (REQ-0002).
                        cands = sorted(u for u in g.items
                                       if u == bare or u.endswith(":" + bare))
                        paths += 1
                        print(f"path      {uid} -> {' | '.join(cands)}  [{field}]  {sent[:140]}")
                        continue
                    n += 1
                    print(f"mentions  {uid} -> {cited}  [{field}]  {sent[:140]}")
    print(f"# mentions: {n} citation(s) with no edge; {paths} path mention(s) "
          "(a file named after an item — an edge is the human's call)")


def cmd_universal(g: Graph, args) -> None:
    """REQ-0009: universal language whose grounded children name one mechanism."""
    n = 0
    for uid, item in g.items.items():
        if args.local_only and not g.is_local(uid):
            continue
        if not g.live(item) or not item.get("normative", True):
            continue
        if item.get("type") == "test":
            continue
        hits = sorted({m.group(0).lower() for m in UNIVERSAL_RE.finditer(str(item.get("text") or ""))})
        if not hits:
            continue
        kids = [k for k in g.children(uid)
                if g.live(g.items[k]) and g.items[k].get("type") != "test"]
        if len(kids) != 1:
            continue  # a leaf is guarded by its test; several children may name several mechanisms
        n += 1
        k = kids[0]
        print(f"universal {uid}  says {'/'.join(hits)}  realised by one child: {k} ({g.items[k].get('title', '')[:60]})")
    print(f"# universal: {n} finding(s) (universal language realised by exactly one grounded child)")


def cmd_verification(g: Graph, args) -> None:
    """REQ-0004: verification per branch, not per item.

    A branch is the head plus every live item grounded below it. Its members
    are the items that need verifying: every non-test item in the branch, the
    head included, less root types (an intent is verified through its branch,
    not by a test of its own) and less the types passed as --ignore-types. Its
    tests are the live tests with a verifies link into any member or into the
    head, so a requirement headed branch counts the tests that verify the
    requirement itself; before, only tests below the head were found and a
    directly verified requirement read as unchecked."""
    branch_types = set(args.branch_types.split(",")) if args.branch_types else g.delivery_roots
    method_attr = args.method_attr
    ignore = set(args.ignore_types.split(",")) if args.ignore_types else set()
    n = 0
    for root_uid, root in sorted(g.items.items()):
        if root.get("type") not in branch_types or not g.live(root):
            continue
        if args.local_only and not g.is_local(root_uid):
            continue
        seen, stack = set(), [root_uid]
        while stack:
            u = stack.pop()
            if u in seen:
                continue
            seen.add(u)
            stack.extend(k for k in g.children(u) if g.live(g.items[k]))
        members = sorted(u for u in seen
                         if g.items[u].get("type") != "test"
                         and g.items[u].get("type") not in g.root_types
                         and g.items[u].get("type") not in ignore)
        tally: dict[str, int] = defaultdict(int)
        tested_types: dict[str, set] = defaultdict(set)
        untested: list[str] = []
        for u in sorted(set(members) | {root_uid}):
            it = g.items[u]
            tests = [s for s, l in g.incoming.get(u, [])
                     if l.get("type") == "verifies" and g.live(g.items[s])]
            if not tests:
                if u in members and it.get("normative", True):
                    untested.append(u)
                continue
            for t in tests:
                m = (g.items[t].get("attrs") or {}).get(method_attr) or "unstated"
                tally[m] += 1
                tested_types[m].add(it.get("type"))
        auto = tally.get("automated", 0)
        flag = ""
        if members and auto == 0:
            flag = "  <- NO AUTOMATED CHECK"
        elif members and tally:
            covered = set().union(*tested_types.values())
            all_types = {g.items[u].get("type") for u in members}
            if all_types - covered:
                flag = f"  <- unchecked kinds: {', '.join(sorted(all_types - covered))}"
        if flag:
            n += 1
        dist = ", ".join(f"{k}={v}" for k, v in sorted(tally.items())) or "none"
        print(f"branch    {root_uid}  {root.get('title', '')[:60]}\n"
              f"          members={len(members)} tests: {dist}"
              f"{'  untested: ' + ', '.join(sorted(untested)) if untested else ''}{flag}")
    print(f"# verification: {n} branch(es) flagged")


def cmd_failure_case(g: Graph, args) -> None:
    """REQ-0007: requirements with no clause saying what a violation is (weak signal)."""
    n = 0
    for uid, item in g.items.items():
        if args.local_only and not g.is_local(uid):
            continue
        t = item.get("type")
        if not g.live(item) or not item.get("normative", True) or t == "test" or t in g.root_types:
            continue
        if NEGATIVE_RE.search(str(item.get("text") or "")):
            continue
        n += 1
        print(f"no-failure {uid}  {item.get('title', '')[:80]}")
    print(f"# failure-case: {n} item(s) state only the wanted behaviour (review order, not a gate)")


def cmd_untestable(g: Graph, args) -> None:
    """REQ-0005: predicates no observation of the running system could settle."""
    n = 0
    # Word boundaries that a hyphen does not supply: "machine-readable" is a
    # compound, not the predicate "readable".
    pat = re.compile(r"(?<![\w-])(" + "|".join(re.escape(w) for w in VAGUE_WORDS)
                     + r")(?![\w-])", re.I)
    for uid, item in g.items.items():
        if args.local_only and not g.is_local(uid):
            continue
        t = item.get("type")
        if not g.live(item) or not item.get("normative", True) or t == "test" or t in g.root_types:
            continue
        for sent in sentences(str(item.get("text") or "")):
            hits = sorted({m.group(0).lower() for m in pat.finditer(sent)})
            if hits:
                n += 1
                print(f"untestable {uid}  [{'/'.join(hits)}]  {sent[:140]}")
    print(f"# untestable: {n} sentence(s) with a vague predicate")


def cmd_replacement(g: Graph, args) -> None:
    """REQ-0008: a live item pointing at its own replacement. Name-based only:
    the tool reads meaning, this script can only read names, so it also prints
    the link vocabulary for the reader to classify."""
    types = (g.config.get("links") or {}).get("types", [])
    print("link vocabulary: " + ", ".join(types))
    suspects = [t for t in types if REPLACEMENT_NAME_RE.search(t)]
    n = 0
    for uid, item in g.items.items():
        if not g.live(item):
            continue
        for l in item.get("links", []) or []:
            if l.get("type") in suspects:
                n += 1
                print(f"replacement {uid} --{l['type']}--> {l.get('target')}  (status {item.get('status')})")
    print(f"# replacement: {n} live item(s) carry a replacement-named link"
          + ("" if suspects else " (no link type is named like one; classify the vocabulary above by meaning)"))


def cmd_unstamped(g: Graph, args) -> None:
    """Implementation discipline: a link into a source without a stamp cannot
    tell you when the source moved."""
    n = 0
    for uid, item in g.items.items():
        if not g.is_local(uid) or not g.live(item):
            continue
        for l in item.get("links", []) or []:
            tgt = l.get("target", "")
            if ":" not in tgt:
                continue
            if args.namespace and not tgt.startswith(args.namespace + ":"):
                continue
            if not l.get("stamp"):
                n += 1
                print(f"unstamped {uid} --{l.get('type')}--> {tgt}")
    print(f"# unstamped: {n} link(s); stamp each in place with `tl link SRC DST --type T --stamp`")


def cmd_uncovered(g: Graph, args) -> None:
    """Borrowed items of the given types that no local item links to."""
    ns = args.namespace
    types = set(args.types.split(",")) if args.types else None
    link_types = set(args.links.split(",")) if args.links else None
    n = 0
    for uid, item in sorted(g.items.items()):
        if not uid.startswith(ns + ":") or not g.live(item):
            continue
        if types and item.get("type") not in types:
            continue
        local_in = [(s, l) for s, l in g.incoming.get(uid, []) if g.is_local(s)
                    and (not link_types or l.get("type") in link_types)]
        if local_in:
            continue
        n += 1
        print(f"uncovered {uid}  [{item.get('type')}/{item.get('status')}]  {item.get('title', '')[:80]}")
    print(f"# uncovered: {n} borrowed item(s) in '{ns}' with no incoming local link")


def cmd_siblings(g: Graph, args) -> None:
    """Material for REQ-0001, REQ-0003 and REQ-0006: hold the family together."""
    uid = args.uid
    item = g.items.get(uid)
    if not item:
        sys.exit(f"{uid} is not in the graph")
    print(f"{uid}  {item.get('title', '')}\n")
    for parent, ltype in g.parents(item):
        p = g.items.get(parent)
        if not p:
            print(f"parent {parent} ({ltype}) — NOT IN GRAPH\n")
            continue
        print(f"parent {parent} ({ltype})  [{p.get('type')}]  {p.get('title', '')}")
        print(f"    text: {str(p.get('text') or '')[:300]}")
        sibs = [s for s, l in g.incoming.get(parent, []) if s != uid]
        for s in sorted(set(sibs)):
            si = g.items.get(s, {})
            print(f"    sibling {s}  [{si.get('type')}/{si.get('status')}]  {si.get('title', '')}")
        print()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-C", "--path", default=".", help="project root (default .)")
    ap.add_argument("--dump", help="read this dump JSON instead of running the tool")
    ap.add_argument("--local-only", action="store_true",
                    help="only report on local items (skip borrowed ones)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("mentions", cmd_mentions), ("universal", cmd_universal),
                     ("failure-case", cmd_failure_case), ("untestable", cmd_untestable),
                     ("replacement", cmd_replacement)):
        sub.add_parser(name).set_defaults(func=fn)
    s = sub.add_parser("verification"); s.set_defaults(func=cmd_verification)
    s.add_argument("--branch-types", help="comma list of types that head a branch (default: delivery roots)")
    s.add_argument("--method-attr", default="method", help="test attribute naming the method (default: method)")
    s.add_argument("--ignore-types", help="comma list of member types verified by other means (e.g. journey,page)")
    s = sub.add_parser("unstamped"); s.set_defaults(func=cmd_unstamped)
    s.add_argument("--namespace", help="only links into this source")
    s = sub.add_parser("uncovered"); s.set_defaults(func=cmd_uncovered)
    s.add_argument("--namespace", required=True)
    s.add_argument("--types", help="comma list of borrowed types to expect coverage on")
    s.add_argument("--links", help="comma list of link types that count as coverage")
    s = sub.add_parser("siblings"); s.set_defaults(func=cmd_siblings)
    s.add_argument("uid")
    s = sub.add_parser("all"); s.set_defaults(func=None)
    args = ap.parse_args(argv)
    g = Graph(load(args))
    if args.cmd == "all":
        args.local_only = True
        args.branch_types = None; args.method_attr = "method"; args.namespace = None
        args.ignore_types = None
        for fn in (cmd_mentions, cmd_universal, cmd_verification, cmd_failure_case,
                   cmd_untestable, cmd_replacement, cmd_unstamped):
            print(f"── {fn.__name__[4:].replace('_', '-')} ──")
            fn(g, args)
            print()
        return 0
    args.func(g, args)
    return 0


if __name__ == "__main__":
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    sys.exit(main())
