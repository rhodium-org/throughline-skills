#!/usr/bin/env python3
"""The glossary skill's script: the mechanical half of writing a glossary of a
throughline graph, and the whole of publishing it.

A glossary is a graph of its own that follows throughline-glossary-standard and
composes the graph it explains. The skill decides what each term says; this script
lays the glossary graph down beside the graph it explains, lists the concepts worth
considering, says what a change to the explained graph has touched, and renders the
glossary as one Markdown document the same way every time.

    glossary.py init -C REPO --explains idd [--at glossary] [--as app] [--ref vX.Y.Z]
    glossary.py candidates -C GLOSSARY [--top 40]
    glossary.py review -C GLOSSARY
    glossary.py render -C GLOSSARY [--audience AUD] [--out PATH] [--check]

Standard library only. Needs tl from throughline 5.2.0 or later.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

from tl_cli import refuse, require_tl

STANDARD_URL = "https://github.com/rhodium-org/throughline-glossary-standard"
STANDARD_REF = "v1.0.0"
NAMESPACE = "glossary"
FLOOR = (5, 2, 0)
FLOOR_WHY = "the first release that checks a link declared to run outside the graph"

# Words that never make a concept on their own.
COMMON = frozenset("""
a about above after again against all also an and any are as at be because been
before being below between both but by can cannot could did do does doing done down
during each either every few for from further had has have having he her here hers
him his how i if in into is it its itself just least less may me might more most must
my never no nor not now of off on once one only or other our out over own per same
shall she should since so some such than that the their them then there these they
this those through to too under until up upon us very via was we were what when where
whether which while who whom whose why will with within without would yet you your
item items graph graphs new use used uses using make made makes making set sets way
ways thing things take takes taken give gives given get gets kept keep keeps see
shown show shows says say said like given two three first second last next each
january february march april may june july august september october november december
""".split())
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'-]*")
# Code, file names and paths, which name no concept: `x`, a/b.c, server.test.mjs.
CODE_RE = re.compile(r"`[^`]*`|\S*/\S*|\b[\w-]+(?:\.[\w-]+)*\.[a-z]{1,5}\b")


def tl() -> str:
    return require_tl(FLOOR, FLOOR_WHY)


# tl: implements tl-glossary/REQ-0009@3f8b0bbb95e9
def dump(root: str, saved: str | None = None) -> dict:
    """The glossary graph's dump: read from ``saved`` where given, else from tl."""
    if saved:
        with open(saved, encoding="utf-8") as fh:
            return json.load(fh)
    cmd = [tl(), "-C", root, "dump"]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(f"`{' '.join(cmd)}` exited {out.returncode}: {out.stderr.strip()}")
    return json.loads(out.stdout)


class Glossary:
    """A glossary graph as its dump shows it: its own items; the items of the graphs
    it explains; and the terms of the other glossaries it composes and maps onto."""

    def __init__(self, data: dict):
        self.items = {i["uid"]: i for i in data.get("items", [])}
        schema = (data.get("schema_source") or {}).get("namespace")
        self.live = {u: i for u, i in self.items.items()
                     if i.get("status") not in ("deleted", "rejected")}
        by_ns: dict[str, set[str]] = defaultdict(set)
        for u, i in self.live.items():
            if ":" in u:
                by_ns[u.rsplit(":", 1)[0]].add(i.get("type"))
        # A composed graph that holds terms is a glossary to map onto, not one to explain.
        self.glossary_ns = sorted(ns for ns, kinds in by_ns.items()
                                  if ns != schema and kinds & {"term", "glossary"})
        declared = (data.get("config") or {}).get("sources") or []
        self.explained_ns = sorted(s["namespace"] for s in declared
                                   if not s.get("schema") and s.get("namespace") != schema
                                   and s["namespace"] not in self.glossary_ns)
        local = [i for u, i in self.live.items() if ":" not in u]
        by_name = lambda i: (i.get("title") or "").casefold()
        self.terms = sorted((i for i in local if i.get("type") == "term"), key=by_name)
        self.audiences = sorted((i for i in local if i.get("type") == "audience"), key=by_name)
        self.glosses = [i for i in local if i.get("type") == "gloss"]
        self.glossary = next((i for i in local if i.get("type") == "glossary"), None)
        self.others = sorted((i for u, i in self.live.items() if ":" in u
                              and u.rsplit(":", 1)[0] in self.glossary_ns
                              and i.get("type") == "term"), key=lambda i: i["uid"])

    def explained(self) -> list[dict]:
        return [i for u, i in sorted(self.live.items())
                if ":" in u and u.split(":", 1)[0] in self.explained_ns]

    def names(self, term: dict) -> list[str]:
        return [term.get("title") or ""] + list((term.get("attrs") or {}).get("aliases") or [])

    @staticmethod
    def targets(item: dict, kind: str) -> list[str]:
        return [l["target"] for l in item.get("links") or [] if l.get("type") == kind]

    def gloss(self, term: dict, audience: dict | None) -> dict | None:
        """The gloss that words ``term`` for ``audience``, if one does."""
        if audience is None:
            return None
        return next((x for x in self.glosses if term["uid"] in self.targets(x, "glosses")
                     and audience["uid"] in self.targets(x, "for")), None)

    def audience(self, named: str) -> dict:
        """The audience named by its UID or its title."""
        for a in self.audiences:
            if named in (a["uid"], a.get("title")) or named.casefold() == (a.get("title") or "").casefold():
                return a
        refuse(f"no audience {named!r}: the glossary has "
               + (", ".join(f"{a['uid']} {a.get('title')}" for a in self.audiences) or "none"))

    @staticmethod
    def outside(uid: str) -> bool:
        return ":" in uid


# ── init ────────────────────────────────────────────────────────────────────

def graph_root_above(path: Path, stop: Path) -> Path | None:
    """The nearest folder from ``path`` up to ``stop`` that holds a graph."""
    for p in [path, *path.parents]:
        if (p / "throughline.toml").exists():
            return p
        if p == stop:
            break
    return None


# tl: implements tl-glossary/REQ-0003@e53584a07fb8
def cmd_init(args) -> int:
    tl()                                     # refused before anything is written
    repo = Path(args.path).resolve()
    explained = (repo / args.explains).resolve()
    target = (repo / args.at).resolve()
    if not (explained / "throughline.toml").exists():
        refuse(f"{args.explains} holds no throughline.toml: name the graph the glossary explains")
    holder = graph_root_above(target, repo)
    if holder is not None:
        refuse(f"{args.at} is inside the graph at {holder.relative_to(repo) or '.'}: "
               "put the glossary in a folder of its own beside it (--at)")
    if target.exists() and any(target.iterdir()):
        refuse(f"{args.at} is not empty")
    target.mkdir(parents=True, exist_ok=True)
    pinned = ["--ref", args.ref] if "://" in args.standard else []
    run = subprocess.run([tl(), "-C", str(target), "init", "--from-schema", args.standard,
                          *pinned, "--namespace", NAMESPACE,
                          "--name", f"Glossary of {args.explains}"],
                         capture_output=True, text=True)
    if run.returncode != 0:
        sys.exit(run.stderr.strip() or run.stdout.strip())
    rel = Path(*([".."] * len(target.relative_to(repo).parts)), explained.relative_to(repo))
    with open(target / "throughline.toml", "a", encoding="utf-8") as fh:
        fh.write(f'\n# The graph this glossary explains.\n[[sources]]\nnamespace = "{args.as_}"\n'
                 f'path = "{rel.as_posix()}"\n')
    print(f"made the glossary graph at {target.relative_to(repo)}, explaining "
          f"{args.explains} as {args.as_}, and following {args.standard}@{args.ref}")
    return 0


# ── candidates ──────────────────────────────────────────────────────────────

def phrases(text: str, longest: int = 3):
    """Every run of one to ``longest`` words that neither starts nor ends on a
    common word, lower-cased."""
    words = [re.sub(r"'s$", "", w.lower()).strip("'-")
             for w in WORD_RE.findall(CODE_RE.sub(" ", text))]
    for n in range(1, longest + 1):
        for i in range(len(words) - n + 1):
            run = words[i:i + n]
            if run[0] in COMMON or run[-1] in COMMON or len(run[0]) < 3:
                continue
            yield " ".join(run)


# tl: implements tl-glossary/REQ-0001@e45474e9876f
def cmd_candidates(args) -> int:
    g = Glossary(dump(args.path, args.dump))
    taken = {n.casefold() for t in g.terms for n in g.names(t)}
    used: dict[str, set[str]] = defaultdict(set)
    degree: Counter = Counter()
    for it in g.explained():
        text = " ".join(str(it.get(k) or "") for k in ("title", "text", "rationale"))
        for p in set(phrases(text)):
            used[p].add(it["uid"])
        for link in it.get("links") or []:
            degree[it["uid"]] += 1
            if link.get("target") in g.live:
                degree[link["target"]] += 1
    # A plural is counted with its singular where the graph uses both.
    for p in sorted(used):
        if p.endswith("s") and p[:-1] in used:
            used[p[:-1]] |= used.pop(p)
    rows = [(p, sorted(u)) for p, u in used.items() if len(u) >= 2 and p not in taken]
    # A longer phrase used by as many items says more than the words inside it.
    rows.sort(key=lambda r: (-len(r[1]), -len(r[0].split()), r[0]))
    print(f"candidates from {', '.join(g.explained_ns) or 'no explained graph'} "
          f"({len(g.explained())} items), most used first; "
          f"{len(g.terms)} term(s) already in the glossary")
    for p, uids in rows[:args.top]:
        shown = ", ".join(uids[:6]) + (f" and {len(uids) - 6} more" if len(uids) > 6 else "")
        print(f"  {len(uids):3d}  {p}  ({shown})")
    print("centres (most linked to and from):")
    for uid, n in degree.most_common(10):
        print(f"  {n:3d}  {uid}  {g.live[uid].get('title', '')}")
    return 0


# ── review ──────────────────────────────────────────────────────────────────

MATCHES = ("same_as", "close_to", "broader_match", "narrower_match")


def moved(g: Glossary, link: dict) -> str | None:
    """Why ``link`` no longer stands as stamped, or None."""
    target = g.items.get(link.get("target", ""))
    if target is None or target.get("status") in ("deleted", "rejected"):
        return "gone"
    stamp = link.get("stamp")
    if stamp is None:
        return "unstamped"
    return "moved" if stamp != target.get("fingerprint") else None


def stale(g: Glossary, item: dict, stamped=lambda link: Glossary.outside(link["target"])):
    """Every link of ``item`` that should carry a stamp and no longer stands, why."""
    return [(link, why) for link in item.get("links") or [] if stamped(link)
            for why in [moved(g, link)] if why]


def word_in(name: str, text: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text, re.I) is not None


# tl: implements tl-glossary/REQ-0004@b76040f97582, tl-glossary/REQ-0007@7739125cae80, tl-glossary/REQ-0011@41e6e99ea9c4
def cmd_review(args) -> int:
    g = Glossary(dump(args.path, args.dump))
    touched, settled = [], []
    for term in g.terms:
        found = stale(g, term)
        (touched if found else settled).append((term, found))
    print(f"{len(g.terms)} term(s): {len(touched)} touched, {len(settled)} settled")
    for term, found in touched:
        print(f"touched  {term['uid']}  {term.get('title', '')}")
        for link, why in found:
            target = g.items.get(link["target"]) or {}
            print(f"    {why:9s} {link['type']} {link['target']}  {target.get('title', '')}")
    for term, _ in settled:
        print(f"settled  {term['uid']}  {term.get('title', '')}")
    # A gloss rests on its term: a change to the term marks the gloss.
    for x in g.glosses:
        for link, why in stale(g, x, lambda link: link["type"] == "glosses"):
            print(f"gloss    {x['uid']}  {why} glosses {link['target']}  "
                  f"{(g.items.get(link['target']) or {}).get('title', '')}")
    pairs = Counter((t, a) for x in g.glosses for t in g.targets(x, "glosses") for a in g.targets(x, "for"))
    for (t, a), n in sorted(pairs.items()):
        if n > 1:
            print(f"glosses  {n} glosses word {t} for {a}; keep one")
    # Names within this glossary.
    shared: dict[str, list[str]] = defaultdict(list)
    for term in g.terms:
        for name in {n.casefold() for n in g.names(term) if n}:
            shared[name].append(term["uid"])
    for name, uids in sorted(shared.items()):
        if len(uids) > 1:
            print(f"shared name  '{name}'  {', '.join(uids)}")
    consistency(g)
    return 0


# tl: implements tl-glossary/REQ-0011@41e6e99ea9c4, tl-glossary/REQ-0012@ae21a456dea0
def consistency(g: Glossary) -> None:
    """What stands between this glossary's names and those of the glossaries it maps
    onto, and the retired names its explained graphs still use."""
    for term in g.terms:
        for name in (term.get("attrs") or {}).get("deprecated_names") or []:
            for it in g.explained():
                text = " ".join(str(it.get(k) or "") for k in ("title", "text", "rationale"))
                if word_in(name, text):
                    print(f"retired name  '{name}' ({term['uid']} {term.get('title')}) still in "
                          f"{it['uid']}  {it.get('title', '')}")
    if not g.glossary_ns:
        return
    other_names: dict[str, list[dict]] = defaultdict(list)
    for o in g.others:
        for n in g.names(o):
            other_names[n.casefold()].append(o)
    for term in g.terms:
        matched = [t for k in MATCHES for t in g.targets(term, k)]
        for kind in MATCHES:
            for uid in g.targets(term, kind):
                other = g.items.get(uid) or {}
                if other.get("type") != "term":
                    print(f"not a term    {term['uid']} {kind} {uid}: match only terms of another glossary")
                elif kind == "same_as" and (other.get("title") or "").casefold() != (term.get("title") or "").casefold():
                    print(f"name differs  {term['uid']} {term.get('title')}  is the same as  "
                          f"{uid} {other.get('title')}: one concept, two preferred names")
        if not matched and not (term.get("attrs") or {}).get("local"):
            print(f"no match      {term['uid']} {term.get('title')}: in no glossary of "
                  f"{', '.join(g.glossary_ns)}; add it there, or mark it local")
        for name in {n.casefold() for n in g.names(term) if n}:
            for o in other_names.get(name, []):
                if o["uid"] not in matched:
                    print(f"two meanings  '{name}'  is {term['uid']} {term.get('title')} here and "
                          f"{o['uid']} {o.get('title')} there, with no match between them")


# ── render ──────────────────────────────────────────────────────────────────

def anchor(name: str, seen: set[str]) -> str:
    """The heading id GitHub gives ``name``, made unique the way it does."""
    base = re.sub(r"[^\w\- ]", "", name.strip().lower()).replace(" ", "-")
    a, n = base, 1
    while a in seen:
        a, n = f"{base}-{n}", n + 1
    seen.add(a)
    return a


def one_line(text: str) -> str:
    return " ".join(str(text or "").split())


def cite(g: Glossary, uid: str) -> str:
    title = (g.items.get(uid) or {}).get("title")
    return f"`{uid}` {one_line(title)}" if title else f"`{uid}`"


def signed(item: dict) -> str:
    rats = item.get("ratifications") or []
    if item.get("status") == "ratified" and rats:
        last = rats[-1]
        return f"signed by {last.get('by', 'someone')} on {str(last.get('at', ''))[:10]}"
    return "not yet signed"


def lower_first(text: str) -> str:
    text = one_line(text)
    return text[:1].lower() + text[1:]


# tl: implements tl-glossary/REQ-0008@b8b6b33a2dba, tl-glossary/REQ-0010@081b487da583
def render(g: Glossary, audience: dict | None = None) -> str:
    gls = g.glossary or {}
    terms = [t for t in g.terms
             if audience is None or audience["uid"] in g.targets(t, "for")]
    title = one_line(gls.get("title") or "Glossary")
    out = [f"# {title}" + (f": for {lower_first(audience.get('title'))}" if audience else ""), ""]
    if gls.get("text"):
        out += [one_line(gls["text"]), ""]
    if audience:
        out += [f"*Written for {lower_first(audience.get('title'))}: "
                f"{lower_first((audience.get('attrs') or {}).get('knows'))}*", ""]
    elif g.audiences:
        out += ["Published for " + "; ".join(
            f"{lower_first(a.get('title'))} ({sum(a['uid'] in g.targets(t, 'for') for t in g.terms)} terms)"
            for a in g.audiences) + ".", ""]
    out += ["<!-- Rendered from the glossary graph by the tl:glossary skill. "
            "Change the graph, never this file. -->", ""]
    seen: set[str] = set()
    anchors = {t["uid"]: anchor(t.get("title") or t["uid"], seen) for t in terms}

    def worded(t):
        x = g.gloss(t, audience)
        a = dict(t.get("attrs") or {})
        if x:
            a.update({k: v for k, v in (x.get("attrs") or {}).items() if k != "origin"})
        return (x.get("text") if x else t.get("text")), a, x

    out += ["| Term | In one line |", "|---|---|"]
    for t in terms:
        out.append(f"| [{t.get('title')}](#{anchors[t['uid']]}) | {one_line(worded(t)[0])} |")
    out.append("")

    def named(uid):
        item = g.items.get(uid) or {}
        if uid in anchors:
            return f"[{item.get('title', uid)}](#{anchors[uid]})"
        if ":" in uid:
            return f"{item.get('title', uid)} (`{uid}`)"
        return item.get("title", uid)

    for t in terms:
        text, a, x = worded(t)
        links = defaultdict(list)
        for link in t.get("links") or []:
            links[link["type"]].append(link)
        out += [f"## {t.get('title')}", ""]
        under = list({l["target"]: l for l in t.get("links") or []
                      if Glossary.outside(l.get("target", ""))
                      and moved(g, l) in ("moved", "gone")}.values())
        if x:
            under += [l for l in x.get("links") or []
                      if l["type"] == "glosses" and moved(g, l) in ("moved", "gone")]
        if under:
            out += ["> **Under review.** " + "; ".join(
                f"{cite(g, l['target'])} has {'gone' if moved(g, l) == 'gone' else 'changed'}"
                for l in under) + " since this entry was written.", ""]
        if a.get("aliases"):
            out += [f"*Also called {', '.join(a['aliases'])}.*", ""]
        if a.get("deprecated_names"):
            out += [f"*No longer called {', '.join(a['deprecated_names'])}.*", ""]
        out += [one_line(text), ""]
        if a.get("why"):
            out += [f"**Why it exists.** {one_line(a['why'])}", ""]
        if a.get("how_it_works"):
            out += [f"**How it works.** {one_line(a['how_it_works'])}", ""]
            for l in links["driven_by"]:
                out.append(f"- Decided by {cite(g, l['target'])}")
            if links["driven_by"]:
                out.append("")
        if a.get("example"):
            shown = "".join(f" ({cite(g, l['target'])})" for l in links["shown_by"])
            out += [f"**Example.** {one_line(a['example'])}{shown}", ""]
        for kind, label in (("broader", "A kind of"), ("distinct_from", "Not to be confused with"),
                            ("relates", "See also"), ("same_as", "The same as"),
                            ("close_to", "Close to"), ("broader_match", "Narrower than"),
                            ("narrower_match", "Broader than")):
            if links[kind]:
                out += [f"**{label}** " + ", ".join(named(l["target"]) for l in links[kind]) + ".", ""]
        if links["defined_from"]:
            out += ["Defined from " + "; ".join(cite(g, l["target"]) for l in links["defined_from"])
                    + f". `{t['uid']}`, {signed(t)}"
                    + (f"; worded for this reader in `{x['uid']}`, {signed(x)}" if x else "") + ".", ""]
    return "\n".join(out).rstrip() + "\n"


def default_out(root: Path, audience: dict | None) -> Path:
    """docs/glossary.md at the top of the repository holding the glossary, or
    docs/glossary-<audience>.md for one audience."""
    top = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True)
    base = Path(top.stdout.strip()) if top.returncode == 0 else root.parent
    name = f"glossary-{anchor(audience.get('title') or audience['uid'], set())}" if audience else "glossary"
    return base / "docs" / f"{name}.md"


# tl: implements tl-glossary/REQ-0008@b8b6b33a2dba, tl-glossary/REQ-0010@081b487da583
def cmd_render(args) -> int:
    root = Path(args.path).resolve()
    g = Glossary(dump(str(root), args.dump))
    audience = g.audience(args.audience) if args.audience else None
    text = render(g, audience)
    out = Path(args.out) if args.out else default_out(root, audience)
    if args.check:
        if not out.exists() or out.read_text(encoding="utf-8") != text:
            print(f"stale: {out} — run glossary.py render")
            return 1
        print(f"up to date: {out}")
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"rendered {out}: {text.count(chr(10) + '## ')} term(s)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="glossary.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init", help="lay a glossary graph down beside the graph it explains")
    p.add_argument("-C", dest="path", default=".", help="the repository")
    p.add_argument("--explains", required=True, help="the explained graph's root, from -C")
    p.add_argument("--at", default="glossary", help="where the glossary graph goes, from -C")
    p.add_argument("--as", dest="as_", default="app", help="the explained graph's namespace")
    p.add_argument("--ref", default=STANDARD_REF, help="the standard's tag")
    p.add_argument("--standard", default=STANDARD_URL,
                   help="the standard's repository, or a path to a checkout of it")
    for name, help_ in (("candidates", "list the concepts worth considering"),
                        ("review", "say what a change to the explained graph touched"),
                        ("render", "render the glossary as one Markdown document")):
        p = sub.add_parser(name, help=help_)
        p.add_argument("-C", dest="path", default=".", help="the glossary graph's root")
        p.add_argument("--dump", help="read this saved `tl dump` instead of running tl")
        if name == "candidates":
            p.add_argument("--top", type=int, default=40)
        if name == "render":
            p.add_argument("--out", help="default: docs/glossary.md at the repository's top, "
                           "or docs/glossary-<audience>.md")
            p.add_argument("--audience", help="publish for this audience (its UID or title): "
                           "the terms for it, in its glosses")
            p.add_argument("--check", action="store_true",
                           help="write nothing; exit 1 when the document is stale")
    args = ap.parse_args(argv)
    return {"init": cmd_init, "candidates": cmd_candidates, "review": cmd_review,
            "render": cmd_render}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
