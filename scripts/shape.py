#!/usr/bin/env python3
"""Mechanics of the throughline shape skill.

The skill's judgement — what the sources say, what the domain is, which
registers the work needs and why — lives in SKILL.md. This script does only
the parts that need no judgement: laying down the shape graph, authoring an
item with the origin and status the skill is bound to, turning the register
decisions in the shape graph into a second graph, and running the check
gate over both. Every structural change goes through the `tl` CLI; nothing
here writes an item file by hand.

Standard library only. `tl` from throughline 3.11.0 or later must be on PATH;
it composes the pointer from the shape graph to the second graph itself.

Layout it produces, under the repo root, for each piece of work shaped:

  idd/shape/         the reasoning graph while the shaping is in progress;
                     idd/shape-2/, idd/shape-3/ ... when another holds that name
  idd/<name>/        the graph for the work itself — named by the skill during
                     discovery, recorded as the name decision in the shape graph
                     and as a `path` source in its throughline.toml
  idd/<name>-shape/  the reasoning graph once `write` has created idd/<name>/:
                     directory and project are renamed after the graph it produced

Usage:
  shape.py [-C REPO] [--shape DIR] init [--another]
                                          lay a shaping down (refuses on a shaped
                                          repo unless --another)
  shape.py [-C REPO] [--shape DIR] status [--json]
                                          what the shape graph holds so far, or
                                          every shaping when none is chosen
  shape.py [-C REPO] [--shape DIR] new PREFIX --type T --title .. --text ..
                       [--rationale ..] [--ground UID]... [--ground-type T]
                       [--attr k=v]... [--graph <name>]
  shape.py [-C REPO] [--shape DIR] write  create idd/<name>/ from the decisions
                                          and rename the shaping <name>-shape
  shape.py [-C REPO] [--shape DIR] repair bring a shaping and its graph made by an
                                          older tl or script to what tl reads now
  shape.py [-C REPO] [--shape DIR] check [--strict]
                                          gate both graphs

--shape names the shaping's directory under idd/. Without it a command acts on
the one shaping in progress, or the one shaping the repo holds, and exits 2
listing them when that leaves more than one.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
from datetime import date
from pathlib import Path

from tl_cli import require_tl

IDD = "idd"
SHAPE = "shape"
BECAUSE = "throughline shape: "

# The shape graph is the same shape every time, because the conversation is.
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
# The item type each register of the shape graph holds, by prefix.
SHAPING_TYPES = {prefix: item_type for item_type, prefix, _d, _t in SHAPING_REGISTERS}
# `tl register type`, which declares the type of a register that exists, is new
# in this release; only a shaping that needs it repaired asks for it.
REGISTER_TYPE_TL = ((5, 11, 0),
                    "the first release that declares the type of a register that exists")
SUFFIX = "-" + SHAPE
IN_PROGRESS_RE = re.compile(rf"^{SHAPE}(-[0-9]+)?$")
DEAD = {"deleted", "rejected"}
NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
PREFIX_RE = re.compile(r"^[A-Z][A-Z0-9]{1,15}$")
TYPE_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def die(msg: str, code: int = 2) -> None:
    print(f"shape: {msg}", file=sys.stderr)
    sys.exit(code)


# tl: implements skill/REQ-0009@e43dcbfe112b
def run(graph: Path, *args: str, quiet: bool = False,
        ok: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess:
    cmd = [require_tl(), "-C", str(graph), *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode not in ok:
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


# tl: implements skill/REQ-0003@0f49b897c80f
def shaped_name(shape: Path) -> str | None:
    """The name decision recorded in the shape graph, if one is live."""
    names = [i for i in local_items(shape)
             if i["type"] == "decision" and i.get("attrs", {}).get("kind") == "name"]
    if not names:
        return None
    if len(names) > 1:
        die(f"more than one live name decision in {shape.name}: "
            + ", ".join(i["uid"] for i in names) + " — reject all but one")
    name = names[0].get("attrs", {}).get("dir")
    if not name:
        die(f"{names[0]['uid']} is the name decision but carries no dir attribute")
    return name


def is_shaping(d: Path) -> bool:
    """A directory under idd/ holding a shape graph, by the names the skill gives one."""
    return ((d / "throughline.toml").exists()
            and (bool(IN_PROGRESS_RE.match(d.name)) or d.name.endswith(SUFFIX)))


def shapings(repo: Path) -> list[Path]:
    idd = repo / IDD
    return sorted(d for d in idd.iterdir() if d.is_dir() and is_shaping(d)) if idd.is_dir() else []


def in_progress(repo: Path) -> list[Path]:
    return [d for d in shapings(repo) if IN_PROGRESS_RE.match(d.name)]


# tl: implements skill/REQ-0010@d46c90a84b98
def resolve(repo: Path, a, required: bool = True) -> Path | None:
    """The shaping a command acts on: the one named, else the one in progress,
    else the only one there is (REQ-0010)."""
    if a.shape:
        d = repo / IDD / a.shape
        if not is_shaping(d):
            die(f"no shape graph at {d}")
        return d
    found = shapings(repo)
    if not found:
        if required:
            die(f"no shape graph under {repo / IDD} — run `init` first")
        return None
    going = in_progress(repo)
    if len(going) == 1:
        return going[0]
    if len(found) == 1:
        return found[0]
    if not required:
        return None
    die("more than one shaping here — name one with --shape: "
        + ", ".join(d.name for d in (going or found)))


# tl: implements skill/REQ-0002@1da7cc6bf70c
def free_in_progress_name(repo: Path) -> str:
    n = 1
    while True:
        name = SHAPE if n == 1 else f"{SHAPE}-{n}"
        if not (repo / IDD / name).exists():
            return name
        n += 1


# tl: implements skill/REQ-0002@1da7cc6bf70c
def name_shaping(repo: Path, shape: Path, name: str) -> Path:
    """Rename a written shaping after the graph it produced: the directory after
    the graph's directory, the project after the graph's project, so two shape
    graphs in one repository never share a project name while their graphs don't."""
    final = repo / IDD / (name + SUFFIX)
    project = config(repo / IDD / name)["project"]["name"] + SUFFIX
    if shape == final:
        return shape
    if final.exists():
        die(f"{final} already exists — cannot name {shape.name} after {name}")
    shape.rename(final)
    cfg = final / "throughline.toml"
    text = cfg.read_text()
    head, sep, rest = text.partition("[project]")
    rest = re.sub(r'(?m)^name = "[^"]*"', f'name = "{project}"', rest, count=1)
    cfg.write_text(head + sep + rest)
    return final


def register_types(graph: Path) -> dict[str, str | None]:
    """The item type each of the graph's own registers declares, None where none."""
    out = json.loads(run(graph, "dump", quiet=True).stdout)
    return {r["prefix"]: r.get("type") for r in out.get("registers", [])
            if ":" not in r["prefix"]}


def decided_types(shape: Path) -> dict[str, str]:
    """The item type each live register decision in the shaping gives its prefix."""
    out = {}
    for i in local_items(shape):
        at = i.get("attrs", {})
        if i["type"] == "decision" and at.get("kind") == "register" \
                and at.get("prefix") and at.get("item_type"):
            out[at["prefix"]] = at["item_type"]
    return out


# tl: implements skill/REQ-0012@a4173c98a2b2
def migrate(shape: Path) -> None:
    """`tl migrate` the shaping and every graph it composes by path, the second
    graph among them, so that each is in the format the running tl reads: tl
    reads the shaping only with its sources, so they go first. Migration may end
    with findings only because a register still declares no type, which
    `repair` then declares."""
    for src in config(shape).get("sources", []):
        other = shape / src.get("path", "")
        if src.get("path") and (other / "throughline.toml").exists():
            run(other, "migrate", quiet=True, ok=(0, 1))
    run(shape, "migrate", quiet=True, ok=(0, 1))


# tl: implements skill/REQ-0012@a4173c98a2b2
def repair(graph: Path, wanted: dict[str, str]) -> tuple[list[str], list[str]]:
    """Declare, with `tl register type`, the item type of each register of a
    migrated graph that declares none and whose type the shaping records — a
    register laid down by an older version of this script, which passed no
    --type. Returns the registers typed, as `PREFIX = type`, and the prefixes
    still untyped because the shaping did not make them."""
    typed, left = [], []
    for prefix, item_type in register_types(graph).items():
        if item_type:
            continue
        if prefix not in wanted:
            left.append(prefix)
            continue
        require_tl(*REGISTER_TYPE_TL)
        run(graph, "register", "type", prefix, wanted[prefix], quiet=True)
        typed.append(f"{prefix} = {wanted[prefix]}")
    return typed, left


def report_repair(graph: Path, typed: list[str], left: list[str]) -> None:
    if typed:
        print(f"{graph}: declared the item type of {len(typed)} register(s): "
              + ", ".join(typed))
    for prefix in left:
        print(f"{graph}: register {prefix} declares no item type and this shaping did "
              f"not make it — `tl -C {graph} register type {prefix} <type>`")


# ---------------------------------------------------------------- commands

# tl: implements skill/REQ-0001@7f04bbb468ac, skill/REQ-0002@1da7cc6bf70c, skill/REQ-0008@f949d8dcb4c7
def cmd_init(repo: Path, a) -> None:
    if (repo / IDD / "throughline.toml").exists():
        die(f"{repo / IDD} is itself a graph root; the shape layout needs "
            f"{IDD}/ to hold sibling graphs, not to be one")
    found = shapings(repo)
    if found and not a.another:
        die(f"this repo has been shaped before ({', '.join(d.name for d in found)}); "
            "run `status`, read the prior reasoning back, and re-confirm it "
            "rather than starting again — or, for other work, `init --another`", 1)
    shape = repo / IDD / free_in_progress_name(repo)
    run(shape, "init", "--bare", "--name", shape.name)
    for item_type, prefix, d, title in SHAPING_REGISTERS:
        declare_type(shape, item_type, f"the shaping conversation records {title.lower()}")
        for spec in SHAPING_ATTRS.get(item_type, []):
            run(shape, "schema", "attr", "add", item_type, *spec,
                "--because", BECAUSE + f"a {item_type} carries its {spec[0]}")
        if item_type in SHAPING_ROOTS:
            declare_root(shape, item_type, SHAPING_ROOTS[item_type],
                         f"a {item_type} is a premise of the shaping")
        # tl: implements skill/REQ-0012@a4173c98a2b2
        run(shape, "register", "new", prefix, d, "--title", title, "--type", item_type)
    print(f"shape graph laid down at {shape}; every item you author "
          "enters as origin ai, status proposed")


def overview(repo: Path) -> list[dict]:
    rows = []
    for d in shapings(repo):
        name = shaped_name(d)
        rows.append({"shape": d.name, "in_progress": bool(IN_PROGRESS_RE.match(d.name)),
                     "name": name,
                     "shaped_exists": bool(name) and (repo / IDD / name / "throughline.toml").exists()})
    return rows


def status_data(repo: Path, shape: Path | None) -> dict:
    if shape is None:
        return {"shape": None, "shapings": overview(repo)}
    items = local_items(shape)
    by_type: dict[str, list] = {}
    for i in items:
        by_type.setdefault(i["type"], []).append(
            {"uid": i["uid"], "title": i["title"], "status": i["status"],
             "attrs": i.get("attrs", {})})
    name = shaped_name(shape)
    pointer = any(s.get("namespace") == name
                  for s in config(shape).get("sources", []))
    return {
        "shape": str(shape),
        "items": by_type,
        "name": name,
        "shaped_graph": str(repo / IDD / name) if name else None,
        "shaped_exists": bool(name) and (repo / IDD / name / "throughline.toml").exists(),
        "pointer_recorded": pointer,
        "shapings": overview(repo),
    }


def cmd_status(repo: Path, a) -> None:
    data = status_data(repo, resolve(repo, a, required=False))
    if a.json:
        print(json.dumps(data, indent=2))
        return
    if data["shape"] is None:
        if not data["shapings"]:
            print(f"no shape graph under {repo / IDD} — run `init` to start discovery")
            return
        print(f"shapings under {repo / IDD} — name one with --shape:")
        for r in data["shapings"]:
            state = "in progress" if r["in_progress"] else "written"
            graph = r["name"] or "not yet named"
            if r["name"]:
                graph += " (exists)" if r["shaped_exists"] else " (not yet written)"
            print(f"  {r['shape']}  [{state}]  shaped graph: {graph}")
        return
    print(f"shape graph: {data['shape']}")
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


# tl: implements skill/REQ-0005@2733b556d7a4
def cmd_new(repo: Path, a) -> None:
    graph = repo / IDD / a.graph if a.graph else resolve(repo, a)
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


# tl: implements skill/REQ-0001@7f04bbb468ac, skill/REQ-0002@1da7cc6bf70c, skill/REQ-0003@0f49b897c80f, skill/REQ-0004@a8eb459a52e8

# tl: implements skill/REQ-0011
def record_lineage(repo: Path, shape: Path, target: Path) -> None:
    """Write, into the second graph's throughline.toml, where it was shaped: the
    shape graph (by its path from the second graph) and, for each register, the
    decision that made it. tl reads past a table it does not know, so this is
    configuration and nothing else; a reader such as history.iddn.uk draws the
    lineage from it without opening the shape graph. Written once, and never
    over a [shaped_by] already there."""
    cfg = target / "throughline.toml"
    if "shaped_by" in config(target):
        return
    regs = {i["attrs"]["prefix"]: i["uid"] for i in local_items(shape)
            if i["type"] == "decision" and i.get("attrs", {}).get("kind") == "register"
            and i.get("attrs", {}).get("prefix")}
    pairs = ", ".join(f'{prefix} = "{uid}"' for prefix, uid in sorted(regs.items()))
    with cfg.open("a") as f:
        f.write(
            "\n# Where this graph was shaped (tl:shape): the shape graph holding the\n"
            "# reasoning behind its name and registers, and the decision that made each\n"
            "# register. A source declared later for a reason the shape graph records\n"
            "# carries its own `shaped_by = [\"<UID>\", ...]`, naming items there.\n"
            "[shaped_by]\n"
            f'graph = "../{shape.name}"\n'
            f"registers = {{ {pairs} }}\n")

def cmd_write(repo: Path, a) -> None:
    shape = resolve(repo, a)
    # A shaping laid down by an older tl may be in a format the running tl
    # refuses to read, or by an older version of this script with registers that
    # declare no type; repair brings it to what the running tl reads, the format
    # the second graph is laid down in below. A no-op on a current shaping.
    # tl: implements skill/REQ-0012@a4173c98a2b2
    migrate(shape)
    report_repair(shape, *repair(shape, SHAPING_TYPES))
    name = shaped_name(shape)
    if not name:
        die(f"no live name decision in {shape.name} — record one (a decision with "
            "kind=name and dir=<name>) before writing the second graph")
    if (not NAME_RE.match(name) or IN_PROGRESS_RE.match(name)
            or name.endswith(SUFFIX)):
        die(f"{name!r} is not a usable directory name (lower-case, digits, "
            f"hyphens; not {SHAPE!r}, {SHAPE}-<n> or ending {SUFFIX!r}, which "
            "name shape graphs)")
    target = repo / IDD / name
    pointer = any(s.get("namespace") == name for s in config(shape).get("sources", []))
    if (target / "throughline.toml").exists():
        if pointer and shape.name != name + SUFFIX:
            # Written before shape graphs were named after their graph: name it now.
            final = name_shaping(repo, shape, name)
            record_lineage(repo, final, target)
            print(f"{target} was written from this shaping; renamed {shape.name} to {final.name}"
                  " and recorded its lineage")
            return
        die(f"{target} already exists — the second graph has been written; add "
            "registers to it with `tl register new --type` by hand if a new decision "
            "calls for one", 1)
    if (repo / IDD / (name + SUFFIX)).exists():
        die(f"{repo / IDD / (name + SUFFIX)} already exists — another shaping "
            f"produced a graph named {name}")

    decisions = [i for i in local_items(shape)
                 if i["type"] == "decision" and i.get("attrs", {}).get("kind") == "register"]
    if not decisions:
        die(f"no live register decisions in {shape.name} — nothing to write")
    grounds = {i["uid"] for i in local_items(shape) if i["type"] in ("need", "constraint")}
    regs = []
    for d in decisions:
        at = d.get("attrs", {})
        if not any(l.get("target") in grounds for l in d.get("links", [])):
            die(f"{d['uid']} is a register decision grounded in no live need or "
                "constraint — registers come from the needs, after they are "
                "confirmed; link it to the need or standard that calls for it")
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
        # tl: implements skill/REQ-0012@a4173c98a2b2
        run(target, "register", "new", prefix, d, "--title", title, "--type", item_type)

    cfg = shape / "throughline.toml"
    if not any(s.get("namespace") == name for s in config(shape).get("sources", [])):
        with cfg.open("a") as f:
            f.write(
                "\n# The graph this shaping produced. Composed so `tl context`\n"
                "# here shows the whole picture.\n"
                "[[sources]]\n"
                f'namespace = "{name}"\n'
                f'path = "../{name}"\n')
    final = name_shaping(repo, shape, name)
    record_lineage(repo, final, target)
    print(f"wrote {target} with {len(regs)} register(s), recorded the pointer and the "
          f"lineage, and named the shape graph {final}\nnext: run `check`; the new graph reports "
          "empty-registers as a warning until its first layer is authored")


# tl: implements skill/REQ-0012@a4173c98a2b2
def cmd_repair(repo: Path, a) -> None:
    shape = resolve(repo, a)
    migrate(shape)
    report_repair(shape, *repair(shape, SHAPING_TYPES))
    name = shaped_name(shape)
    target = repo / IDD / name if name else None
    if target is not None and (target / "throughline.toml").exists():
        report_repair(target, *repair(target, decided_types(shape)))
    print(f"repaired {shape.name}" + (f" and {name}" if target is not None
                                     and target.exists() else "")
          + " — `tl new <PREFIX>` needs no --type where the shaping made the register")


# tl: implements skill/REQ-0007@14bac9f5d8ac
def cmd_check(repo: Path, a) -> None:
    shape = resolve(repo, a)
    graphs = [shape]
    name = shaped_name(shape)
    if name and (repo / IDD / name / "throughline.toml").exists():
        graphs.append(repo / IDD / name)
    rc = 0
    for g in graphs:
        cmd = [require_tl(), "-C", str(g), "check"] + (["--strict"] if a.strict else [])
        print(f"== {' '.join(cmd)}", flush=True)
        proc = subprocess.run(cmd, text=True)
        rc = max(rc, proc.returncode)
        print()
    sys.exit(rc)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog=__doc__.split("Usage:")[1])
    p.add_argument("-C", "--repo", default=".", help="repository root (default: .)")
    p.add_argument("--shape", help="the shaping's directory under idd/")
    sub = p.add_subparsers(dest="command", required=True)
    i = sub.add_parser("init")
    i.add_argument("--another", action="store_true",
                   help="start a shaping for other work beside the existing ones")
    s = sub.add_parser("status")
    s.add_argument("--json", action="store_true")
    n = sub.add_parser("new")
    n.add_argument("prefix")
    n.add_argument("--graph", help="a graph under idd/ (default: the shaping)")
    n.add_argument("--type", required=True)
    n.add_argument("--title", required=True)
    n.add_argument("--text", required=True)
    n.add_argument("--rationale")
    n.add_argument("--ground", action="append")
    n.add_argument("--ground-type")
    n.add_argument("--attr", action="append")
    sub.add_parser("write")
    sub.add_parser("repair")
    c = sub.add_parser("check")
    c.add_argument("--strict", action="store_true")
    a = p.parse_args(argv)
    repo = Path(a.repo).resolve()
    {"init": cmd_init, "status": cmd_status, "new": cmd_new,
     "write": cmd_write, "repair": cmd_repair, "check": cmd_check}[a.command](repo, a)


if __name__ == "__main__":
    main()
