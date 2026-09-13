"""Fixture tests for the multigraph skill.

tl-multigraph TEST-0003, TEST-0005, TEST-0006 and TEST-0007. Each test builds
throwaway graphs with the real CLIs, and where the skill text gives shell to
run, the shell is read out of SKILL.md so that what is tested is what a reader
follows. Needs tl and tl-compose on PATH: pip install throughline-compose.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1] / "skills" / "multigraph" / "SKILL.md"
RATIFIER = "Ada Lovelace"

for _tool in ("tl", "tl-compose"):
    if shutil.which(_tool) is None:
        raise RuntimeError(f"{_tool} is not on PATH: pip install throughline-compose")


# ── helpers ─────────────────────────────────────────────────────────────────

def run(*args, cwd=None):
    return subprocess.run(list(args), cwd=cwd, text=True, capture_output=True)


def sh(script, cwd):
    return subprocess.run(["bash", "-c", script], cwd=cwd, text=True, capture_output=True)


def skill_shell(heading):
    """The first ```sh fence under a heading of SKILL.md, verbatim."""
    text = SKILL.read_text()
    tail = text[text.index(heading):]
    return re.search(r"```sh\n(.*?)```", tail, re.S).group(1)


def finding_codes(check_output):
    """The set of finding codes a check printed, e.g. {'orphan', 'coverage'}."""
    return set(re.findall(r"^\[(?:ERROR|warn )\]\s+\S*\s+(\S+)", check_output, re.M))


def init(root, name):
    r = run("tl", "-C", str(root), "init", "--no-demo", "--name", name)
    assert r.returncode == 0, r.stderr
    return root


def add_source(root, namespace, path, reexport=None):
    block = f'\n[[sources]]\nnamespace = "{namespace}"\npath = "{path}"\n'
    if reexport:
        block += f"reexport = {reexport!r}\n".replace("'", '"')
    (root / "throughline.toml").open("a").write(block)


def new(binary, root, prefix, title, *, ground=None, ground_type=None, status=None):
    args = [binary, "-C", str(root), "new", prefix, "--no-interactive", "--origin", "human",
            "--title", title, "--text", f"{title}."]
    if prefix == "REQ":
        args += ["--type", "requirement", "--attr", "priority=must"]
    else:
        args += ["--type", "intent"]
    if ground:
        args += ["--ground", ground]
    if ground_type:
        args += ["--ground-type", ground_type]
    if status:
        args += ["--status", status]
    return run(*args)


def item_file(root, uid):
    return next(root.rglob(f"{uid}.yml"))


# ── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def two_graphs(tmp_path):
    """An anchor with one root, and a consumer wired to it by path whose only
    item is grounded on that root, at proposed."""
    anchor = init(tmp_path / "anchor", "anchor")
    assert new("tl", anchor, "INT", "The shared subject").returncode == 0
    consumer = init(tmp_path / "consumer", "consumer")
    add_source(consumer, "anchor", "../anchor")
    r = new("tl-compose", consumer, "REQ", "Consumer item grounded through the anchor",
            ground="anchor:INT-0001", status="proposed")
    assert r.returncode == 0, r.stderr
    return anchor, consumer


@pytest.fixture
def three_graphs(tmp_path):
    """An external standard, an anchor that implements one of its items by
    path, and a consumer wired to the anchor only."""
    ext = init(tmp_path / "ext", "ext")
    assert new("tl", ext, "INT", "The external standard").returncode == 0
    anchor = init(tmp_path / "anchor", "anchor")
    add_source(anchor, "ext", "../ext")
    assert new("tl-compose", anchor, "INT", "The shared subject").returncode == 0
    r = new("tl-compose", anchor, "REQ", "Anchor item implementing the standard",
            ground="ext:INT-0001", ground_type="implements")
    assert r.returncode == 0, r.stderr
    consumer = init(tmp_path / "consumer", "consumer")
    pristine = (consumer / "throughline.toml").read_text()
    add_source(consumer, "anchor", "../anchor")
    return ext, anchor, consumer, pristine


# ── TEST-0003: the binary rule ──────────────────────────────────────────────

def test_binary_rule_grep(two_graphs):
    anchor, consumer = two_graphs
    line = skill_shell("## The binary rule").strip()
    assert "<graph>" in line
    for graph, expected in ((anchor, "tl"), (consumer, "tl-compose")):
        r = sh(line.replace("<graph>", str(graph)), cwd=graph.parent)
        assert r.stdout.strip() == expected, (graph.name, r.stdout, r.stderr)


def test_bare_tl_cannot_see_the_seam(two_graphs):
    anchor, consumer = two_graphs
    c = str(consumer)

    healthy_compose = run("tl-compose", "-C", c, "check")
    assert healthy_compose.returncode == 0, healthy_compose.stdout + healthy_compose.stderr
    healthy_bare = run("tl", "-C", c, "check")
    assert healthy_bare.returncode != 0
    assert "namespace-unresolved" in healthy_bare.stdout

    r = run("tl", "-C", str(anchor), "delete", "INT-0001", "--reason", "fixture")
    assert r.returncode == 0, r.stderr

    broken_compose = run("tl-compose", "-C", c, "check")
    assert broken_compose.returncode != 0
    assert "deleted-link-target" in broken_compose.stdout
    broken_bare = run("tl", "-C", c, "check")
    assert broken_bare.returncode != 0
    assert "deleted-link-target" not in broken_bare.stdout
    # Bare tl reports exactly what it reported when the graph was healthy:
    # it does not see the seam, so it cannot gate it.
    assert finding_codes(broken_bare.stdout) == finding_codes(healthy_bare.stdout)


# ── TEST-0005: composition is one level deep ────────────────────────────────

def _declare_ext_on_consumer(consumer):
    add_source(consumer, "ext", "../ext")


def _reexport_ext_through_anchor(consumer):
    toml = consumer / "throughline.toml"
    text = toml.read_text().replace('path = "../anchor"\n', 'path = "../anchor"\nreexport = ["ext"]\n')
    toml.write_text(text)


@pytest.mark.parametrize("remedy", [_declare_ext_on_consumer, _reexport_ext_through_anchor],
                         ids=["consumer-declares-ext", "consumer-reexports-ext-via-anchor"])
def test_transitive_namespace(three_graphs, remedy):
    ext, anchor, consumer, pristine = three_graphs
    c = str(consumer)

    undeclared = run("tl-compose", "-C", c, "check")
    assert undeclared.returncode == 2
    assert "'ext'" in undeclared.stderr and "not a declared [[sources]] namespace" in undeclared.stderr

    remedy(consumer)
    r = new("tl-compose", consumer, "REQ", "Consumer item grounded through the anchor",
            ground="anchor:INT-0001")
    assert r.returncode == 0, r.stderr
    fixed = run("tl-compose", "-C", c, "check")
    assert fixed.returncode == 0, fixed.stdout + fixed.stderr
    composed = fixed.stdout + fixed.stderr
    assert ("re-exported from 'anchor'" in composed) == (remedy is _reexport_ext_through_anchor)

    if remedy is _reexport_ext_through_anchor:
        r = new("tl-compose", consumer, "REQ", "Consumer item citing the standard directly",
                ground="ext:INT-0001", ground_type="implements")
        assert r.returncode == 0, r.stderr
        assert run("tl-compose", "-C", c, "check").returncode == 0

    # Adopting a source cost the sources blocks and nothing else.
    final = (consumer / "throughline.toml").read_text()
    assert final.startswith(pristine)
    extra = final[len(pristine):]
    assert set(re.findall(r"^\[.*\]$", extra, re.M)) == {"[[sources]]"}


# ── TEST-0006: ratify in the owning graph, over the union ───────────────────

def test_ratify_owning_graph_over_union(two_graphs):
    anchor, consumer = two_graphs
    c = str(consumer)
    local = item_file(consumer, "REQ-0001")
    borrowed = item_file(anchor, "INT-0001")
    borrowed_before = borrowed.read_text()

    bare = run("tl", "-C", c, "ratify", "REQ-0001", "--by", RATIFIER)
    assert bare.returncode == 2
    assert "not grounded" in bare.stderr
    assert "ratified_by" not in local.read_text()

    foreign = run("tl-compose", "-C", c, "ratify", "anchor:INT-0001", "--by", RATIFIER)
    assert foreign.returncode == 2
    assert "does not exist" in foreign.stderr
    assert borrowed.read_text() == borrowed_before

    composed = run("tl-compose", "-C", c, "ratify", "REQ-0001", "--by", RATIFIER)
    assert composed.returncode == 0, composed.stderr
    text = local.read_text()
    assert "status: ratified" in text
    assert f"ratified_by: {RATIFIER}" in text

    skill = re.sub(r"\s+", " ", SKILL.read_text())
    assert "use exactly what they give you" in skill
    assert "never invent, guess or reuse a name" in skill


# ── TEST-0007: the gate loop ────────────────────────────────────────────────

def test_gate_loop(tmp_path, two_graphs):
    anchor, consumer = two_graphs
    sound = init(tmp_path / "sound", "sound")
    assert new("tl", sound, "INT", "A sound graph").returncode == 0
    assert run("tl", "-C", str(anchor), "delete", "INT-0001", "--reason", "fixture").returncode == 0

    loop = skill_shell("## Gate every graph")
    r = sh(loop, cwd=tmp_path)
    assert r.returncode != 0

    groups = re.findall(r"^::group::(\S+) -C (\S+) check", r.stdout, re.M)
    assert len(groups) == 3, r.stdout
    by_graph = {Path(g).name: b for b, g in groups}
    assert by_graph == {"anchor": "tl", "sound": "tl", "consumer": "tl-compose"}
    assert "deleted-link-target" in r.stdout
