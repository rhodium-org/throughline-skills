"""Fixture tests for the shape skill's script.

skill TEST-0001 to TEST-0008, one per requirement. Each test drives
scripts/shape.py over a throwaway repository with the real CLIs, and where
the skill text gives shell to run, the shell is read out of SKILL.md so that
what is tested is what a reader follows. Needs tl and tl-compose on PATH:
pip install throughline-compose.
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "shape.py"
SKILL = ROOT / "skills" / "shape" / "SKILL.md"
TL_INIT_REGISTERS = {"vision", "requirements", "nonfunctional", "non-goals", "tests"}
SHAPE_REGISTERS = {"sources", "domain", "needs", "decisions", "non-goals", "constraints"}

for _tool in ("tl", "tl-compose"):
    if shutil.which(_tool) is None:
        raise RuntimeError(f"{_tool} is not on PATH: pip install throughline-compose")


# ── helpers ─────────────────────────────────────────────────────────────────

def run(*args, cwd=None):
    return subprocess.run(list(args), cwd=cwd, text=True, capture_output=True)


def shape(repo, *args):
    return run(sys.executable, str(SCRIPT), "-C", str(repo), *args)


def new(repo, prefix, type_, title, *, ground=(), attrs=(), rationale=None, graph=None):
    args = ["new", prefix, "--type", type_, "--title", title, "--text", f"{title}."]
    for g in ground:
        args += ["--ground", g]
    for kv in attrs:
        args += ["--attr", kv]
    if rationale:
        args += ["--rationale", rationale]
    if graph:
        args += ["--graph", graph]
    r = shape(repo, *args)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout.strip()


def skill_shell(heading, index=0):
    """The ```sh fences under a heading of SKILL.md, verbatim, before the next heading."""
    text = SKILL.read_text()
    tail = text[text.index(heading) + len(heading):]
    cut = re.search(r"\n#", tail)
    section = tail[: cut.start()] if cut else tail
    return re.findall(r"```sh\n(.*?)```", section, re.S)[index]


def skill_run(repo, heading, index=0):
    """Run a fence from SKILL.md with $S bound to the script and <repo> to the repo."""
    script = skill_shell(heading, index).replace("<repo>", str(repo))
    env = dict(os.environ, S=str(SCRIPT))
    return subprocess.run(["bash", "-c", script], cwd=repo, env=env, text=True, capture_output=True)


def dump(graph):
    binary = "tl-compose" if "[[sources]]" in (graph / "throughline.toml").read_text() else "tl"
    r = run(binary, "-C", str(graph), "dump")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def local_items(graph):
    return [i for i in dump(graph)["items"] if not i.get("source")]


def registers(graph):
    return {p.parent.name for p in graph.rglob(".register.yml")}


def snapshot(root):
    return {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}


# ── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def repo(tmp_path):
    repo = tmp_path / "work"
    repo.mkdir()
    (repo / "docs").mkdir()
    (repo / "docs" / "brief.md").write_text("# Brief\n\nAn estate run for tenants.\n")
    return repo


@pytest.fixture
def discovered(repo):
    """A repo taken through the discovery with the script: one source, a domain
    citing it, the name `estate`, one need, two register decisions grounded in
    the need, one rejected register, and the fixed layout from init."""
    r = skill_run(repo, "If there is no `idd/shape/`:")
    assert r.returncode == 0, r.stdout + r.stderr
    src = new(repo, "SRC", "source", "The brief", attrs=["path=docs/brief.md"])
    dom = new(repo, "DOM", "domain", "A hosting estate run for tenants", ground=[src])
    new(repo, "DEC", "decision", "Name the graph estate", ground=[dom],
        attrs=["kind=name", "dir=estate"])
    need = new(repo, "NEED", "need", "Every control traces to a threat", ground=[dom],
               rationale="The audit will ask.")
    new(repo, "DEC", "decision", "Vision register", ground=[need],
        attrs=["kind=register", "prefix=INT", "dir=vision", "item_type=intent"])
    new(repo, "DEC", "decision", "Threats register", ground=[need],
        attrs=["kind=register", "prefix=THR", "dir=threats", "item_type=threat",
               "grounding=delivery-root"])
    ng = new(repo, "NG", "non_goal", "No risk register", ground=[need],
             rationale="Considered because tl init would have offered one.")
    return repo, {"src": src, "dom": dom, "need": need, "ng": ng}


@pytest.fixture
def written(discovered):
    repo, uids = discovered
    r = skill_run(repo, "### 5. Write, gate, hand off", 0)
    assert r.returncode == 0, r.stdout + r.stderr
    return repo, uids


# ── one test per requirement ────────────────────────────────────────────────

def test_layout_comes_from_discovery_not_tl_init(written):  # TEST-0001 / REQ-0001
    repo, uids = written
    estate = repo / "idd" / "estate"
    assert registers(estate) == {"vision", "threats"}
    assert not (registers(estate) & (TL_INIT_REGISTERS - {"vision"}))
    assert local_items(estate) == []
    assert not (estate / "docs").exists()
    cfg = (estate / "throughline.toml").read_text()
    assert "threat" in dump(estate)["config"]["grounding"]["delivery_roots"]
    assert re.search(r"# throughline shape: DEC-\d+ — Threats register", cfg)
    assert registers(repo / "idd" / "shape") == SHAPE_REGISTERS
    # provenance: the source carries where and when it was read, the domain cites it
    src = next(i for i in local_items(repo / "idd" / "shape") if i["uid"] == uids["src"])
    assert src["attrs"]["path"] == "docs/brief.md"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(src["attrs"]["read"]))
    dom = next(i for i in local_items(repo / "idd" / "shape") if i["uid"] == uids["dom"])
    assert {"target": uids["src"], "type": "derives_from"} in dom["links"]


def test_shape_graph_is_always_at_that_name(repo, tmp_path):  # TEST-0002 / REQ-0002
    r = skill_run(repo, "If there is no `idd/shape/`:")
    assert r.returncode == 0, r.stdout + r.stderr
    cfg = repo / "idd" / "shape" / "throughline.toml"
    assert cfg.exists()
    assert dump(repo / "idd" / "shape")["config"]["project"]["name"] == "shape"
    assert registers(repo / "idd" / "shape") == SHAPE_REGISTERS
    assert {p.name for p in (repo / "idd").iterdir()} == {"shape"}
    # a repo whose idd/ is itself a graph root cannot take the layout
    other = tmp_path / "rooted"
    other.mkdir()
    assert run("tl", "-C", str(other / "idd"), "init", "--no-demo").returncode == 0
    r = shape(other, "init")
    assert r.returncode == 2
    assert "itself a graph root" in r.stderr
    assert not (other / "idd" / "shape").exists()


def test_second_graph_named_in_discovery_never_defaulted(repo):  # TEST-0003 / REQ-0003
    assert shape(repo, "init").returncode == 0
    dom = new(repo, "DOM", "domain", "A hosting estate run for tenants")
    need = new(repo, "NEED", "need", "Traceability", ground=[dom])
    new(repo, "DEC", "decision", "Vision register", ground=[need],
        attrs=["kind=register", "prefix=INT", "dir=vision", "item_type=intent"])
    r = shape(repo, "write")
    assert r.returncode == 2
    assert "no live name decision" in r.stderr
    assert {p.name for p in (repo / "idd").iterdir()} == {"shape"}
    for bad in ("shape", "Estate", "my estate"):
        uid = new(repo, "DEC", "decision", f"Name it {bad}", ground=[dom],
                  attrs=["kind=name", f"dir={bad}"])
        r = shape(repo, "write")
        assert r.returncode == 2, bad
        assert "not a usable directory name" in r.stderr, bad
        assert run("tl", "-C", str(repo / "idd" / "shape"), "status", uid, "rejected").returncode == 0
    new(repo, "DEC", "decision", "Name the graph estate", ground=[dom],
        attrs=["kind=name", "dir=estate"])
    r = shape(repo, "write")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (repo / "idd" / "estate" / "throughline.toml").exists()
    sources = dump(repo / "idd" / "shape")["config"]["sources"]
    assert {"namespace": "estate", "path": "../estate"} == {k: sources[0][k] for k in ("namespace", "path")}
    status = json.loads(shape(repo, "status", "--json").stdout)
    assert status["name"] == "estate" and status["shaped_exists"] and status["pointer_recorded"]


def test_registers_come_after_needs(repo):  # TEST-0004 / REQ-0004
    text = SKILL.read_text()
    stages = ["### 1. Sources", "### 2. Domain", "### 3. Specific needs",
              "### 4. Registers", "### 5. Write, gate, hand off"]
    positions = [text.index(s) for s in stages]
    assert positions == sorted(positions)
    before_registers = " ".join(text[text.index("## The discovery, in order"):text.index("### 4. Registers")].split())
    assert "Not until they are confirmed do you say the word *register*" in before_registers
    # the script refuses to write a register that no need or standard called for
    assert shape(repo, "init").returncode == 0
    dom = new(repo, "DOM", "domain", "A hosting estate run for tenants")
    new(repo, "DEC", "decision", "Name the graph estate", ground=[dom], attrs=["kind=name", "dir=estate"])
    early = new(repo, "DEC", "decision", "Vision register", ground=[dom],
                attrs=["kind=register", "prefix=INT", "dir=vision", "item_type=intent"])
    r = shape(repo, "write")
    assert r.returncode == 2
    assert early in r.stderr and "no live need or constraint" in r.stderr
    assert not (repo / "idd" / "estate").exists()
    need = new(repo, "NEED", "need", "A vision to trace to", ground=[dom])
    assert run("tl", "-C", str(repo / "idd" / "shape"), "link", early, need, "--type", "derives_from").returncode == 0
    r = shape(repo, "write")
    assert r.returncode == 0, r.stdout + r.stderr


def test_every_item_is_ai_and_proposed_and_the_script_cannot_ratify(written):  # TEST-0005 / REQ-0005
    repo, _ = written
    items = local_items(repo / "idd" / "shape")
    assert len(items) == 7
    assert all(i["attrs"]["origin"] == "ai" and i["status"] == "proposed" for i in items)
    # the same binding holds for an item authored into the second graph
    new(repo, "INT", "intent", "The estate is run for its tenants", graph="estate")
    (intent,) = local_items(repo / "idd" / "estate")
    assert intent["attrs"]["origin"] == "ai" and intent["status"] == "proposed"
    r = shape(repo, "ratify", intent["uid"])
    assert r.returncode == 2 and "invalid choice" in r.stderr
    # and the skill text tells the agent to decline when asked
    assert "Ratification is a human act. If asked to do it, decline" in " ".join(SKILL.read_text().split())
    assert "ratify" not in SCRIPT.read_text().replace("Ratification", "").lower().replace("never ratif", "")


def test_rejected_register_is_recorded_with_its_rationale(discovered):  # TEST-0006 / REQ-0006
    repo, uids = discovered
    ng = next(i for i in local_items(repo / "idd" / "shape") if i["uid"] == uids["ng"])
    assert ng["type"] == "non_goal"
    assert ng["rationale"] == "Considered because tl init would have offered one."
    assert {"target": uids["need"], "type": "derives_from"} in ng["links"]
    assert (repo / "idd" / "shape" / "non-goals" / f"{ng['uid']}.yml").exists()
    status = shape(repo, "status").stdout
    considered = status[status.index("Registers considered and not created"):]
    assert ng["uid"] in considered.split("\n\n")[0]


def test_hands_back_on_zero_errors_in_both_graphs(written):  # TEST-0007 / REQ-0007
    repo, _ = written
    r = skill_run(repo, "### 5. Write, gate, hand off", 1)
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout + r.stderr
    commands = re.findall(r"^== (\S+) -C (\S+) check", out, re.M)
    assert [(b, Path(p).name) for b, p in commands] == [("tl-compose", "shape"), ("tl", "estate")]
    assert "empty-registers" in out
    assert out.count("0 error(s)") == 2 and "[ERROR]" not in out
    assert local_items(repo / "idd" / "estate") == []   # nothing authored to silence the warning
    strict = shape(repo, "check", "--strict")
    assert strict.returncode != 0
    assert "unratified" in strict.stdout + strict.stderr


def test_rerun_reconfirms_and_never_overwrites(written):  # TEST-0008 / REQ-0008
    repo, uids = written
    before = snapshot(repo / "idd")
    r = skill_run(repo, "If there is no `idd/shape/`:")
    assert r.returncode == 1
    assert "shaped before" in r.stderr
    r = shape(repo, "write")
    assert r.returncode == 1
    assert "already exists" in r.stderr
    assert snapshot(repo / "idd") == before
    r = skill_run(repo, "## Has this repo been shaped before?")
    assert r.returncode == 0, r.stderr
    for uid in uids.values():
        assert uid in r.stdout
    assert "shaped graph:" in r.stdout and "estate" in r.stdout
