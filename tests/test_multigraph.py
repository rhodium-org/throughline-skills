"""Fixture tests for the multigraph skill.

tl-multigraph TEST-0003, TEST-0005, TEST-0006 and TEST-0007. Each test builds
throwaway graphs with the real CLI, and where the skill text gives shell to
run, the shell is read out of SKILL.md so that what is tested is what a reader
follows. Needs tl from throughline 3.11.0 or later on PATH:
pip install 'throughline>=3.11.0'.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1] / "skills" / "multigraph" / "SKILL.md"
RATIFIER = "Ada Lovelace"

if shutil.which("tl") is None:
    raise RuntimeError("tl is not on PATH: pip install 'throughline>=3.11.0'")


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


def init(root, name):
    r = run("tl", "-C", str(root), "init", "--no-demo", "--name", name)
    assert r.returncode == 0, r.stderr
    return root


def add_source(root, namespace, path, extra=""):
    block = f'\n[[sources]]\nnamespace = "{namespace}"\npath = "{path}"\n{extra}'
    (root / "throughline.toml").open("a").write(block)


def new(root, prefix, title, *, ground=None, ground_type=None, status=None):
    args = ["tl", "-C", str(root), "new", prefix, "--no-interactive", "--origin", "human",
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
    assert new(anchor, "INT", "The shared subject").returncode == 0
    consumer = init(tmp_path / "consumer", "consumer")
    add_source(consumer, "anchor", "../anchor")
    r = new(consumer, "REQ", "Consumer item grounded through the anchor",
            ground="anchor:INT-0001", status="proposed")
    assert r.returncode == 0, r.stderr
    return anchor, consumer


@pytest.fixture
def three_graphs(tmp_path):
    """An external standard, an anchor that implements one of its items by
    path, and a consumer wired to the anchor only."""
    ext = init(tmp_path / "ext", "ext")
    assert new(ext, "INT", "The external standard").returncode == 0
    anchor = init(tmp_path / "anchor", "anchor")
    add_source(anchor, "ext", "../ext")
    assert new(anchor, "INT", "The shared subject").returncode == 0
    r = new(anchor, "REQ", "Anchor item implementing the standard",
            ground="ext:INT-0001", ground_type="implements")
    assert r.returncode == 0, r.stderr
    consumer = init(tmp_path / "consumer", "consumer")
    pristine = (consumer / "throughline.toml").read_text()
    add_source(consumer, "anchor", "../anchor")
    return ext, anchor, consumer, pristine


# ── TEST-0003: one command, and it sees the seam ────────────────────────────

def test_tl_sees_the_seam(two_graphs):
    anchor, consumer = two_graphs
    c = str(consumer)

    healthy = run("tl", "-C", c, "check")
    assert healthy.returncode == 0, healthy.stdout + healthy.stderr
    assert "composed: anchor (path ../anchor)" in healthy.stdout + healthy.stderr

    r = run("tl", "-C", str(anchor), "delete", "INT-0001", "--reason", "fixture")
    assert r.returncode == 0, r.stderr

    broken = run("tl", "-C", c, "check")
    assert broken.returncode != 0
    assert re.search(r"deleted-link-target .*'anchor:INT-0001'", broken.stdout), broken.stdout


def test_skill_names_one_command():
    shell = "\n".join(re.findall(r"```sh\n(.*?)```", SKILL.read_text(), re.S))
    assert re.search(r"^\s*tl -C ", shell, re.M)
    # Every throughline command a reader is given is tl, and none is chosen by
    # what a graph's config declares.
    assert set(re.findall(r"(?<![\w./-])tl[\w-]*", shell)) == {"tl"}
    assert "[[sources" not in shell


# ── TEST-0005: a source's sources come with it ──────────────────────────────

def test_transitive_namespace(three_graphs):
    ext, anchor, consumer, pristine = three_graphs
    c = str(consumer)

    composed = run("tl", "-C", c, "check")
    assert composed.returncode == 0, composed.stdout + composed.stderr
    assert re.search(r"ext \(path \.\./ext\) \[\w+\] via anchor", composed.stdout + composed.stderr)

    r = new(consumer, "REQ", "Consumer item grounded through the anchor", ground="anchor:INT-0001")
    assert r.returncode == 0, r.stderr
    r = new(consumer, "REQ", "Consumer item citing the standard directly",
            ground="ext:INT-0001", ground_type="implements")
    assert r.returncode == 0, r.stderr
    assert run("tl", "-C", c, "check").returncode == 0

    # Declaring the transitive source as well binds it once.
    add_source(consumer, "ext", "../ext")
    both = run("tl", "-C", c, "check")
    assert both.returncode == 0, both.stdout + both.stderr

    # Adopting a source cost the sources blocks and nothing else.
    final = (consumer / "throughline.toml").read_text()
    assert final.startswith(pristine)
    extra = final[len(pristine):]
    assert set(re.findall(r"^\[.*\]$", extra, re.M)) == {"[[sources]]"}


def test_alias_renames_a_transitive_label(tmp_path, three_graphs):
    ext, anchor, _, _ = three_graphs
    consumer = init(tmp_path / "aliased", "aliased")
    add_source(consumer, "anchor", "../anchor", 'alias = { ext = "standard" }\n')
    r = new(consumer, "REQ", "Consumer item citing the standard by its alias",
            ground="standard:INT-0001", ground_type="implements")
    assert r.returncode == 0, r.stderr
    checked = run("tl", "-C", str(consumer), "check")
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert "standard (path ../ext)" in checked.stdout + checked.stderr
    old_label = new(consumer, "REQ", "Consumer item citing the old label",
                    ground="ext:INT-0001", ground_type="implements")
    assert old_label.returncode != 0


def test_reexport_is_refused(three_graphs):
    _, _, consumer, _ = three_graphs
    toml = consumer / "throughline.toml"
    toml.write_text(toml.read_text().replace('path = "../anchor"\n', 'path = "../anchor"\nreexport = ["ext"]\n'))
    r = run("tl", "-C", str(consumer), "check")
    assert r.returncode == 2
    assert "'reexport'" in r.stderr and "withdrawn" in r.stderr


# ── TEST-0006: ratify in the owning graph, over the union ───────────────────

def test_ratify_owning_graph_over_union(two_graphs):
    anchor, consumer = two_graphs
    c = str(consumer)
    local = item_file(consumer, "REQ-0001")
    borrowed = item_file(anchor, "INT-0001")
    borrowed_before = borrowed.read_text()

    foreign = run("tl", "-C", c, "ratify", "anchor:INT-0001", "--by", RATIFIER)
    assert foreign.returncode == 2
    assert "does not exist" in foreign.stderr
    assert borrowed.read_text() == borrowed_before

    # Without the source the item reaches no root, so ratify refuses it: the
    # grounding that lets it through below is the union's.
    toml = consumer / "throughline.toml"
    config = toml.read_text()
    toml.write_text(config[:config.index("\n[[sources]]")] + "\n")
    unsourced = run("tl", "-C", c, "ratify", "REQ-0001", "--by", RATIFIER)
    assert unsourced.returncode == 2
    assert "not grounded" in unsourced.stderr
    assert "ratified_by" not in local.read_text()
    toml.write_text(config)

    composed = run("tl", "-C", c, "ratify", "REQ-0001", "--by", RATIFIER)
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
    assert new(sound, "INT", "A sound graph").returncode == 0
    assert run("tl", "-C", str(anchor), "delete", "INT-0001", "--reason", "fixture").returncode == 0

    loop = skill_shell("## Gate every graph")
    r = sh(loop, cwd=tmp_path)
    assert r.returncode != 0

    groups = re.findall(r"^::group::(\S+) -C (\S+) check", r.stdout, re.M)
    assert sorted(Path(g).name for _, g in groups) == ["anchor", "consumer", "sound"], r.stdout
    assert {b for b, _ in groups} == {"tl"}
    assert "deleted-link-target" in r.stdout
