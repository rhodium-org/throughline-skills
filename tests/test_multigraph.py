"""Fixture tests for the multigraph skill.

tl-multigraph TEST-0006, TEST-0007 and TEST-0012. Each test builds
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


def add_source(root, namespace, path):
    block = f'\n[[sources]]\nnamespace = "{namespace}"\npath = "{path}"\n'
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


# ── TEST-0006: ratify in the owning graph, over the union ───────────────────

# tl: verifies tl-multigraph/TEST-0006@56dab54d3632
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

# tl: verifies tl-multigraph/TEST-0007@65b0e264a17a
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


# ── TEST-0012: composition is read from tl context, not restated here ────────

# tl: verifies tl-multigraph/TEST-0012@0c0604e5a23d
def test_skill_defers_composition_to_tl_context():
    text = SKILL.read_text()
    flat = re.sub(r"\s+", " ", text)
    assert "tl -C <graph> context" in text and "composition section" in flat
    for mechanic in ("alias =", "reexport", "TL_OFFLINE", "--local", "~/.cache/throughline",
                     "to any depth"):
        assert mechanic not in text, mechanic


# ── TEST-0013: a merge collision is resolved in every graph ─────────────────

def git(root, *args):
    r = run("git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", *args)
    assert r.returncode == 0, r.stderr
    return r


def skill_shells(heading):
    """Every ```sh fence under a heading of SKILL.md, up to the next heading."""
    text = SKILL.read_text()
    tail = text[text.index(heading) + len(heading):]
    section = tail[:tail.find("\n## ")] if "\n## " in tail else tail
    return re.findall(r"```sh\n(.*?)```", section, re.S)


# tl: verifies tl-multigraph/TEST-0013@3fa513732046
def test_resolve_collision_across_graphs(tmp_path):
    anchor = init(tmp_path / "anchor", "anchor")
    assert new(anchor, "INT", "The shared subject").returncode == 0
    consumer = init(tmp_path / "consumer", "consumer")
    add_source(consumer, "anchor", "../anchor")
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "base")
    git(tmp_path, "checkout", "-q", "-b", "feat")
    assert new(anchor, "REQ", "Feat subject", ground="INT-0001").returncode == 0
    assert new(consumer, "REQ", "Feat team", ground="anchor:REQ-0001").returncode == 0
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "feat")
    git(tmp_path, "checkout", "-q", "main")
    assert new(anchor, "REQ", "Main subject", ground="INT-0001").returncode == 0
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "main")
    git(tmp_path, "checkout", "-q", "feat")
    merge = run("git", "-C", str(tmp_path), "merge", "main")
    assert merge.returncode != 0 and "CONFLICT (add/add)" in merge.stdout

    resolve, listing, repoint = skill_shells("## A merge stopped on a UID collision")
    r = sh(resolve, cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "move REQ-0001 -> REQ-0002  (ours)" in r.stdout
    assert "title: Feat subject" in item_file(anchor, "REQ-0002").read_text()

    # The consumer's link still names the old UID, which now means main's item.
    listing = re.sub(r"^moved=\S+ OLD=\S+", "moved=HEAD OLD=REQ-0001", listing, flags=re.M)
    r = sh(listing, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "consumer/requirements/REQ-0001.yml: - target: anchor:REQ-0001"

    assert "link " in repoint and "unlink " in repoint
    assert run("tl", "-C", str(consumer), "link", "REQ-0001", "anchor:REQ-0002",
               "--type", "derives_from").returncode == 0
    assert run("tl", "-C", str(consumer), "unlink", "REQ-0001",
               "anchor:REQ-0001").returncode == 0
    trace = run("tl", "-C", str(consumer), "trace", "REQ-0001").stdout
    assert "anchor:REQ-0002" in trace and "Feat subject" in trace
