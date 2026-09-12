#!/usr/bin/env python3
"""Mechanics of the throughline shaping skill.

The skill's judgement — what the sources say, what the domain is, which
registers the work needs and why — lives in SKILL.md. This script does only
the parts that need no judgement: laying down the shaping graph, authoring an
item with the origin and status the skill is bound to, turning the register
decisions in the shaping graph into a second graph, and running the check
gate over both. Every structural change goes through the `tl` / `tl-compose`
CLI; nothing here writes an item file by hand.

Standard library only. `tl-compose` (which brings `tl`) must be on PATH.

Layout it produces, under the repo root:

  idd/shaping/     the reasoning graph — fixed name, owned by the skill
  idd/<name>/      the graph for the work itself — named by the skill during
                   discovery, recorded as the name decision in shaping and as
                   a `path` source in shaping's throughline.toml

Usage:
  shaping.py [-C REPO] init                 create idd/shaping/ (refuses if present)
  shaping.py [-C REPO] status [--json]      what the shaping graph holds so far
  shaping.py [-C REPO] new PREFIX --type T --title .. --text .. [--rationale ..]
                       [--ground UID]... [--ground-type derives_from]
                       [--attr k=v]... [--graph shaping|<name>]
  shaping.py [-C REPO] write                create idd/<name>/ from the decisions
  shaping.py [-C REPO] check [--strict]     gate both graphs, binary per graph
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from datetime import date
from pathlib import Path

IDD = "idd"
SHAPING = "shaping"
BECAUSE = "throughline shaping: "

# The shaping graph is the same shape every time, because the conversation is.
# type -> (register prefix, register dir, register title)
SHAPING_REGISTERS = [
    ("source", "SRC", "sources", "Sources read"),
    ("domain", "DOM", "domain", "Domain reading"),
    ("need", "NEED", "needs", "What this work needs from its graph"),
    ("decision", "DEC", "decisions", "Register and naming decisions"),
    ("non_goal", "NG", "non-goals", "Registers considered and not created"),
    ("constraint", "CON", "constraints", "Inherited standards"),
]
# Extra roots: a source is a premise (root, not delivery — nothing has to
# follow from a document); a domain reading is the premise everything else
# follows from, so it is a delivery root and an unserved one is a finding.
SHAPING_ROOTS = {"source": "root", "domain": "delivery-root"}
SHAPING_ATTRS = {
    "source": [("path", "--kind", "string"), ("read", "--kind", "date")],
    "decision": [
        ("kind", "--kind", "enum", "--values", "register,name", "--required"),
        ("prefix", "--kind", "string"),
        ("dir", "--kind", "string"),
        ("item_type", "--kind", "string"),
        ("grounding", "--kind", "enum", "--values", "root,delivery-root,grounded"),
    ],
}
DEFAULT_DELIVERY_ROOTS = {"intent", "business_need", "risk", "constraint"}
DEAD = {"deleted", "rejected"}
NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
PREFIX_RE = re.compile(r"^[A-Z][A-Z0-9]{1,15}$")
TYPE_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def die(msg: str, code: int = 2) -> None:
    print(f"shaping: {msg}", file=sys.stderr)
    sys.exit(code)


def binary(graph: Path) -> str:
    """The multigraph rule: a graph with [[sources]] takes tl-compose."""
    cfg = graph / "throughline.toml"
    sourced = cfg.exists() and "[[sources]]" in cfg.read_text()
    name = "tl-compose" if sourced else "tl"
    if shutil.which(name) is None:
        die(f"{name} is not on PATH — pip install throughline-compose")
    return name


def run(graph: Path, *args: str, quiet: bool = False) -> subprocess.CompletedProcess:
    cmd = [binary(graph) if graph.joinpath("throughline.toml").exists() else "tl",
           "-C", str(graph), *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        die(f"`{' '.join(cmd)}` exited {proc.returncode}")
    if not quiet and proc.stdout.strip():
        print(proc.stdout.rstrip())
    return proc


def config(graph: Path) -> dict:
    return tomllib.loads((graph / "throughline.toml").read_text())


def local_items(graph: Path) -> list[dict]:
    """Live local items of a graph, from the dump interchange surface."""
    out = run(graph, "dump", quiet=True).stdout
    items = json.loads(out)["items"]
    return [i for i in items if not i.get("source") and ":" not in i["uid"]
            and i.get("status") not in DEAD]


def declare_type(graph: Path, item_type: str, why: str) -> None:
    cfg = config(graph)
    if item_type not in cfg.get("types", {}):
        run(graph, "schema", "type", "add", item_type, "--because", BECAUSE + why)
    attrs = config(graph)["types"].get(item_type, {}).get("attrs", {})
    if "origin" not in attrs:
        run(graph, "schema", "attr", "add", item_type, "origin", "--kind", "enum",
            "--values", "human,ai,hybrid", "--because",
            BECAUSE + "every item records where it came from")


def declare_root(graph: Path, item_type: str, role: str, why: str) -> None:
    g = config(graph)["grounding"]
    if item_type not in g.get("root_types", []):
        run(graph, "schema", "grounding", "add", "root_types", item_type,
            "--because", BECAUSE + why)
    if role == "delivery-root" and item_type not in g.get("delivery_roots", []):
        run(graph, "schema", "grounding", "add", "delivery_roots", item_type,
            "--because", BECAUSE + why)


def shaped_name(shaping: Path) -> str | None:
    """The name decision recorded in the shaping graph, if one is live."""
    names = [i for i in local_items(shaping)
             if i["type"] == "decision" and i.get("attrs", {}).get("kind") == "name"]
    if not names:
        return None
    if len(names) > 1:
        die("more than one live name decision in shaping: "
            + ", ".join(i["uid"] for i in names) + " — reject all but one")
    name = names[0].get("attrs", {}).get("dir")
    if not name:
        die(f"{names[0]['uid']} is the name decision but carries no dir attribute")
    return name


# ---------------------------------------------------------------- commands

def cmd_init(repo: Path, _a) -> None:
    shaping = repo / IDD / SHAPING
    if (shaping / "throughline.toml").exists():
        die(f"{shaping} already exists — this repo has been shaped before; "
            "run `status`, read the prior reasoning back, and re-confirm it "
            "rather than starting again", 1)
    if (repo / IDD / "throughline.toml").exists():
        die(f"{repo / IDD} is itself a graph root; the shaping layout needs "
            f"{IDD}/ to hold sibling graphs, not to be one")
    run(shaping, "init", "--bare", "--name", SHAPING)
    for item_type, prefix, d, title in SHAPING_REGISTERS:
        declare_type(shaping, item_type, f"the shaping conversation records {title.lower()}")
        for spec in SHAPING_ATTRS.get(item_type, []):
            run(shaping, "schema", "attr", "add", item_type, *spec,
                "--because", BECAUSE + f"a {item_type} carries its {spec[0]}")
        if item_type in SHAPING_ROOTS:
            declare_root(shaping, item_type, SHAPING_ROOTS[item_type],
                         f"a {item_type} is a premise of the shaping")
        run(shaping, "register", "new", prefix, d, "--title", title)
    print(f"shaping graph laid down at {shaping}; every item you author "
          "enters as origin ai, status proposed")


def status_data(repo: Path) -> dict:
    shaping = repo / IDD / SHAPING
    if not (shaping / "throughline.toml").exists():
        return {"shaping": None}
    items = local_items(shaping)
    by_type: dict[str, list] = {}
    for i in items:
        by_type.setdefault(i["type"], []).append(
            {"uid": i["uid"], "title": i["title"], "status": i["status"],
             "attrs": i.get("attrs", {})})
    name = shaped_name(shaping)
    pointer = any(s.get("namespace") == name
                  for s in config(shaping).get("sources", []))
    return {
        "shaping": str(shaping),
        "items": by_type,
        "name": name,
        "shaped_graph": str(repo / IDD / name) if name else None,
        "shaped_exists": bool(name) and (repo / IDD / name / "throughline.toml").exists(),
        "pointer_recorded": pointer,
    }


def cmd_status(repo: Path, a) -> None:
    data = status_data(repo)
    if a.json:
        print(json.dumps(data, indent=2))
        return
    if data["shaping"] is None:
        print(f"no shaping graph at {repo / IDD / SHAPING} — run `init` to start discovery")
        return
    print(f"shaping graph: {data['shaping']}")
    for item_type, _p, _d, title in SHAPING_REGISTERS:
        rows = data["items"].get(item_type, [])
        print(f"\n{title} ({len(rows)})")
        for r in rows:
            read = r["attrs"].get("read")
            when = f"  (read {read})" if read else ""
            print(f"  {r['uid']}  [{r['status']}]  {r['title']}{when}")
    print()
    if data["name"]:
        state = "exists" if data["shaped_exists"] else "not yet written"
        print(f"shaped graph: {data['shaped_graph']} ({state}; pointer "
              f"{'recorded' if data['pointer_recorded'] else 'not recorded'})")
    else:
        print("shaped graph: not yet named (no live name decision)")


def cmd_new(repo: Path, a) -> None:
    graph = repo / IDD / a.graph
    if not (graph / "throughline.toml").exists():
        die(f"no graph at {graph}")
    if not TYPE_RE.match(a.type):
        die(f"item type {a.type!r} is not a lower-case identifier")
    args = ["new", a.prefix, "--type", a.type, "--title", a.title, "--text", a.text,
            "--origin", "ai", "--status", "proposed", "--no-interactive"]
    for g in a.ground or []:
        args += ["--ground", g]
    if a.ground_type:
        args += ["--ground-type", a.ground_type]
    attrs = list(a.attr or [])
    if a.type == "source" and not any(kv.startswith("read=") for kv in attrs):
        # A source is a record of what was read, and what was read is what
        # existed that day: date it by construction so it never reads as a
        # present-tense claim, and a re-run can see how old the reading is.
        attrs.append("read=" + date.today().isoformat())
    for kv in attrs:
        if "=" not in kv:
            die(f"--attr expects KEY=VALUE, got {kv!r}")
        args += ["--attr", kv]
    out = run(graph, *args, quiet=True).stdout
    m = re.search(r"created ([A-Z][A-Z0-9]*-\d+)", out)
    if not m:
        die("could not read the new UID back from tl")
    uid = m.group(1)
    if a.rationale:
        run(graph, "amend", uid, "--rationale", a.rationale, quiet=True)
    print(uid)


def cmd_write(repo: Path, _a) -> None:
    shaping = repo / IDD / SHAPING
    if not (shaping / "throughline.toml").exists():
        die(f"no shaping graph at {shaping} — run `init` first")
    name = shaped_name(shaping)
    if not name:
        die("no live name decision in shaping — record one (a decision with "
            "kind=name and dir=<name>) before writing the second graph")
    if not NAME_RE.match(name) or name == SHAPING:
        die(f"{name!r} is not a usable directory name (lower-case, digits, "
            f"hyphens; not {SHAPING!r})")
    target = repo / IDD / name
    if (target / "throughline.toml").exists():
        die(f"{target} already exists — the second graph has been written; add "
            "registers to it with `tl register new` by hand if a new decision "
            "calls for one", 1)

    decisions = [i for i in local_items(shaping)
                 if i["type"] == "decision" and i.get("attrs", {}).get("kind") == "register"]
    if not decisions:
        die("no live register decisions in shaping — nothing to write")
    regs = []
    for d in decisions:
        at = d.get("attrs", {})
        missing = [k for k in ("prefix", "dir", "item_type") if not at.get(k)]
        if missing:
            die(f"{d['uid']} is a register decision missing {', '.join(missing)}")
        if not PREFIX_RE.match(at["prefix"]):
            die(f"{d['uid']}: prefix {at['prefix']!r} is not a valid UID prefix")
        if not TYPE_RE.match(at["item_type"]):
            die(f"{d['uid']}: item_type {at['item_type']!r} is not a lower-case identifier")
        regs.append((d["uid"], at["prefix"], at["dir"], at["item_type"],
                     at.get("grounding", "grounded"), d["title"]))
    prefixes = [r[1] for r in regs]
    if len(set(prefixes)) != len(prefixes):
        die("two register decisions claim the same prefix: " + ", ".join(prefixes))
    if not any(r[4] == "delivery-root" or r[3] in DEFAULT_DELIVERY_ROOTS for r in regs):
        die("no register decision holds a delivery root (an intent, business "
            "need, risk or constraint, or a type declared grounding=delivery-root) "
            "— the second graph would have nowhere to put the intent it is "
            "grounded in")

    run(target, "init", "--bare", "--name", name)
    for uid, prefix, d, item_type, grounding, title in regs:
        declare_type(target, item_type, f"{uid} — {title}")
        if grounding in ("root", "delivery-root"):
            declare_root(target, item_type, grounding, f"{uid} — {title}")
        run(target, "register", "new", prefix, d, "--title", title)

    cfg = shaping / "throughline.toml"
    if not any(s.get("namespace") == name for s in config(shaping).get("sources", [])):
        with cfg.open("a") as f:
            f.write(
                "\n# The graph this shaping produced. Composed so `tl-compose context`\n"
                "# here shows the whole picture; from now on drive shaping with\n"
                "# tl-compose, never bare tl (the binary rule).\n"
                "[[sources]]\n"
                f'namespace = "{name}"\n'
                f'path = "../{name}"\n')
    print(f"wrote {target} with {len(regs)} register(s) and recorded the pointer in "
          f"{cfg}\nnext: seed the root intent there with `new --graph {name} ...`, "
          "then run `check`")


def cmd_check(repo: Path, a) -> None:
    shaping = repo / IDD / SHAPING
    if not (shaping / "throughline.toml").exists():
        die(f"no shaping graph at {shaping}")
    graphs = [shaping]
    name = shaped_name(shaping)
    if name and (repo / IDD / name / "throughline.toml").exists():
        graphs.append(repo / IDD / name)
    rc = 0
    for g in graphs:
        cmd = [binary(g), "-C", str(g), "check"] + (["--strict"] if a.strict else [])
        print(f"== {' '.join(cmd)}")
        proc = subprocess.run(cmd, text=True)
        rc = max(rc, proc.returncode)
        print()
    sys.exit(rc)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog=__doc__.split("Usage:")[1])
    p.add_argument("-C", "--repo", default=".", help="repository root (default: .)")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    s = sub.add_parser("status")
    s.add_argument("--json", action="store_true")
    n = sub.add_parser("new")
    n.add_argument("prefix")
    n.add_argument("--graph", default=SHAPING)
    n.add_argument("--type", required=True)
    n.add_argument("--title", required=True)
    n.add_argument("--text", required=True)
    n.add_argument("--rationale")
    n.add_argument("--ground", action="append")
    n.add_argument("--ground-type")
    n.add_argument("--attr", action="append")
    sub.add_parser("write")
    c = sub.add_parser("check")
    c.add_argument("--strict", action="store_true")
    a = p.parse_args(argv)
    repo = Path(a.repo).resolve()
    {"init": cmd_init, "status": cmd_status, "new": cmd_new,
     "write": cmd_write, "check": cmd_check}[a.command](repo, a)


if __name__ == "__main__":
    main()
