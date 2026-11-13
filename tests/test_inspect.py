"""Fixture tests for the inspect skill's script and page.

tl-inspect TEST-0001 to TEST-0005 and TEST-0007 to TEST-0010; TEST-0006 is
read in a browser. Each test builds throwaway graphs with the real CLI and
asserts what the script makes of them. Needs tl from throughline 5.2.0 or
later on PATH: pip install 'throughline>=5.2.0'.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "inspect_graph.py"
SKILL = ROOT / "skills" / "inspect" / "SKILL.md"
TEMPLATE = ROOT / "skills" / "inspect" / "page.html"
SIGNER = "A Person"

if shutil.which("tl") is None:
    raise RuntimeError("tl is not on PATH: pip install 'throughline>=5.2.0'")


# ── helpers ─────────────────────────────────────────────────────────────────

def run(*args, env=None, cwd=None, ok=(0,)):
    r = subprocess.run([str(a) for a in args], text=True, capture_output=True, env=env, cwd=cwd)
    assert r.returncode in ok, f"{args} exited {r.returncode}: {r.stdout}\n{r.stderr}"
    return r


def init(root, name):
    run("tl", "-C", root, "init", "--no-demo", "--name", name)
    return root


def new(root, prefix, title, *, ground=None, ground_type=None, text=None, attrs=()):
    args = ["tl", "-C", root, "new", prefix, "--no-interactive", "--origin", "ai",
            "--title", title, "--text", text or f"{title}."]
    for a in attrs:
        args += ["--attr", a]
    if ground:
        args += ["--ground", ground]
    if ground_type:
        args += ["--ground-type", ground_type]
    run(*args)


def borrow(root, namespace, path):
    with (root / "throughline.toml").open("a") as fh:
        fh.write(f'\n[[sources]]\nnamespace = "{namespace}"\npath = "{path}"\n')


def inspect(repo, graph, uid, *extra):
    return run(sys.executable, SCRIPT, "--repo", repo, "-C", graph, uid, *extra)


def view(repo, graph, uid, *extra):
    return json.loads(inspect(repo, graph, uid, "--json", "-", *extra).stdout)


def names(data, role):
    return sorted(f"{n['graph']}/{n['uid']}" for n in data["nodes"] if n["role"] == role)


def node(data, graph, uid):
    return next(n for n in data["nodes"] if n["graph"] == graph and n["uid"] == uid)


def dumped(root, uid):
    items = json.loads(run("tl", "-C", root, "dump").stdout)["items"]
    return next(i for i in items if i["uid"] == uid)


def tree_hash(repo):
    h = hashlib.sha256()
    for p in sorted(repo.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(repo)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


# ── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def repo(tmp_path):
    """spec: an intent, a requirement under it and a test of the requirement.
    app borrows spec by path: one requirement implements spec's with a stamp,
    another satisfies it with none. lone is joined to neither."""
    spec = init(tmp_path / "spec", "spec")
    new(spec, "INT", "The subject")
    new(spec, "REQ", "What the subject must do", ground="INT-0001", attrs=["priority=must"],
        text="A long wording, kept whole.\nWith a second line, and a mark: <b>bold</b>.")
    new(spec, "TEST", "A test of it", ground="REQ-0001", ground_type="verifies")

    app = init(tmp_path / "app", "app")
    borrow(app, "spec", "../spec")
    new(app, "INT", "The build")
    new(app, "REQ", "The part that does it", ground="INT-0001", attrs=["priority=must"])
    new(app, "REQ", "A choice made for it", ground="INT-0001", attrs=["priority=should"])
    run("tl", "-C", app, "link", "REQ-0001", "spec:REQ-0001", "--type", "implements", "--stamp")
    run("tl", "-C", app, "link", "REQ-0002", "spec:REQ-0001", "--type", "satisfies")

    lone = init(tmp_path / "lone", "lone")
    new(lone, "INT", "Something else")
    new(lone, "REQ", "Nothing to do with it", ground="INT-0001", attrs=["priority=must"])
    return tmp_path


# ── TEST-0001: the view joins graphs that path sources connect ──────────────

# tl: verifies tl-inspect/TEST-0001@00d8aedb6395
def test_dependents_in_a_second_graph_appear_once_under_their_owner(repo):
    data = view(repo, repo / "spec", "REQ-0001")
    assert names(data, "focus") == ["spec/REQ-0001"]
    assert names(data, "trace") == ["spec/INT-0001"]
    assert names(data, "blast") == ["app/REQ-0001", "app/REQ-0002", "spec/TEST-0001"]
    ids = [n["id"] for n in data["nodes"]]
    assert len(ids) == len(set(ids))
    assert node(data, "app", "REQ-0001")["other"] and not node(data, "spec", "TEST-0001")["other"]


# tl: verifies tl-inspect/TEST-0001@00d8aedb6395
def test_an_item_in_the_borrowing_graph_rests_on_the_owner_s_items(repo):
    data = view(repo, repo / "app", "REQ-0001")
    assert names(data, "trace") == ["app/INT-0001", "spec/INT-0001", "spec/REQ-0001"]
    assert node(data, "spec", "REQ-0001")["root"] == "spec"


# tl: verifies tl-inspect/TEST-0001@00d8aedb6395
def test_a_graph_nothing_joins_is_not_read(repo):
    for graph, uid in ((repo / "spec", "REQ-0001"), (repo / "app", "REQ-0001")):
        data = view(repo, graph, uid, "--depth", "0")
        assert not [n for n in data["nodes"] if n["graph"] == "lone"]
        assert not [c for c in data["checks"] if c["graph"] == "lone"]


# ── TEST-0002: content reaches the view unchanged ───────────────────────────

# tl: verifies tl-inspect/TEST-0002@69385b64fd74
def test_text_attributes_links_and_signature_reach_the_view_unchanged(repo):
    spec = repo / "spec"
    run("tl", "-C", spec, "amend", "REQ-0001", "--rationale", "Because the subject needs it.")
    run("tl", "-C", spec, "ratify", "INT-0001", "--by", SIGNER)
    data = view(repo, spec, "REQ-0001")
    for uid in ("REQ-0001", "INT-0001"):
        held, shown = dumped(spec, uid), node(data, "spec", uid)
        for field in ("type", "status", "title", "text"):
            assert shown[field] == held[field]
        assert shown["rationale"] == (held.get("rationale") or "")
        assert shown["attrs"] == (held.get("attrs") or {})
    req = node(data, "spec", "REQ-0001")
    assert "<b>bold</b>" in req["text"] and "\n" in req["text"]
    assert [(l["type"], l["target"]) for l in req["links"]] == [("derives_from", "INT-0001")]
    assert [s["by"] for s in node(data, "spec", "INT-0001")["signed"]] == [SIGNER]
    assert req["unsigned"] and not node(data, "spec", "INT-0001")["unsigned"]


# ── TEST-0003: the state of a stamp ─────────────────────────────────────────

def stamps(data):
    return {(e["from"].split("#")[1], e["type"]): e["stamp"] for e in data["edges"]
            if e["to"] == data["focus"]}


# tl: verifies tl-inspect/TEST-0003@6193726a7c3e
def test_a_stamp_reads_current_then_stale_and_a_bare_link_out_reads_unstamped(repo):
    spec = repo / "spec"
    before = stamps(view(repo, spec, "REQ-0001"))
    assert before[("REQ-0001", "implements")] == "current"
    assert before[("REQ-0002", "satisfies")] == "unstamped"
    assert before[("TEST-0001", "verifies")] is None          # inside one graph

    run("tl", "-C", spec, "amend", "REQ-0001", "--text", "Reworded since the stamp was written.")
    after = stamps(view(repo, spec, "REQ-0001"))
    assert after[("REQ-0001", "implements")] == "stale"

    said = inspect(repo, spec, "REQ-0001").stdout
    assert "stale or unstamped: 2" in said
    assert re.search(r"REQ-0001 -implements-> REQ-0001\s+stale", said)
    assert re.search(r"REQ-0002 -satisfies-> REQ-0001\s+unstamped", said)


# ── TEST-0004: the layout ───────────────────────────────────────────────────

# tl: verifies tl-inspect/TEST-0004@b376a07ed6f2
def test_no_box_overlaps_another_and_the_item_sits_between(tmp_path):
    g = init(tmp_path / "g", "g")
    new(g, "INT", "The subject")
    new(g, "REQ", "A requirement", ground="INT-0001", attrs=["priority=must"])
    new(g, "REQ", "A refinement of it", ground="REQ-0001", attrs=["priority=must"])
    for n in range(6):
        new(g, "TEST", f"Test {n}", ground="REQ-0002", ground_type="verifies")
    data = view(tmp_path, g, "REQ-0002")
    size, boxes = data["size"], {n["id"]: n for n in data["nodes"]}
    assert len(boxes) == 9
    for n in boxes.values():
        assert 0 <= n["x"] and n["x"] + size["box_w"] <= size["width"]
        assert 0 <= n["y"] and n["y"] + size["box_h"] <= size["height"]
    placed = list(boxes.values())
    for i, a in enumerate(placed):
        for b in placed[i + 1:]:
            apart = (a["x"] + size["box_w"] <= b["x"] or b["x"] + size["box_w"] <= a["x"]
                     or a["y"] + size["box_h"] <= b["y"] or b["y"] + size["box_h"] <= a["y"])
            assert apart, (a["uid"], b["uid"])
    focus = boxes[data["focus"]]
    assert all(n["y"] < focus["y"] for n in placed if n["role"] == "trace")
    assert all(n["y"] > focus["y"] for n in placed if n["role"] == "blast")
    assert len({n["y"] for n in placed if n["role"] == "blast"}) == 2     # six wrap onto two rows
    assert node(data, "g", "INT-0001")["y"] < node(data, "g", "REQ-0001")["y"]
    for e in data["edges"]:
        assert boxes[e["from"]]["y"] != boxes[e["to"]]["y"]


# ── TEST-0005: one file that loads nothing ──────────────────────────────────

class Loads(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags, self.urls = [], []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.urls += [v for k, v in attrs if k in ("src", "href", "srcset", "data", "action") and v]


# tl: verifies tl-inspect/TEST-0005@0343975d16ce
def test_the_page_names_no_host_and_holds_graph_text_as_data(tmp_path):
    g = init(tmp_path / "g", "g")
    hostile = 'A wording </script><img src="https://example.org/x.png"> that tries to be markup.'
    new(g, "INT", "The subject", text=hostile)
    page = inspect(tmp_path, g, "INT-0001", "--html", "-").stdout
    seen = Loads()
    seen.feed(page)
    assert page.lower().startswith("<!doctype html>")
    assert seen.urls == [], seen.urls
    assert seen.tags.count("script") == 1 and "img" not in seen.tags
    assert "https://" not in page.replace("https://example.org/x.png", "")
    assert json.dumps(hostile).replace("</", "<\\/")[1:-1] in page

    fragment = inspect(tmp_path, g, "INT-0001", "--fragment", "-").stdout
    assert fragment in page
    for mark in ("<!doctype", "<html", "<head", "<body"):
        assert mark not in fragment.lower()
    assert "/*VIEW*/null" not in fragment


# ── TEST-0007: nothing is written and nothing is signed ─────────────────────

# tl: verifies tl-inspect/TEST-0007@fc3bbc0471cd
def test_the_script_changes_no_graph_and_signing_is_left_to_a_person(repo, tmp_path_factory):
    out = tmp_path_factory.mktemp("out") / "view.html"
    before = tree_hash(repo)
    inspect(repo, repo / "spec", "REQ-0001", "--html", out)
    inspect(repo, repo / "app", "REQ-0001")
    assert tree_hash(repo) == before
    page = out.read_text(encoding="utf-8")
    assert "it signs nothing" in page
    assert '$("ig-cmds").textContent' in page and '" ratify "' in page
    skill = " ".join(SKILL.read_text(encoding="utf-8").split())
    assert "Never run `tl ratify` yourself" in skill
    assert "the repository, the branch checked out at that path, and the graph root" in skill


# ── TEST-0008: the tl floor ─────────────────────────────────────────────────

def stand_in(bin_dir, version):
    bin_dir.mkdir()
    tl = bin_dir / "tl"
    tl.write_text(f"#!/bin/sh\necho 'tl {version}'\n")
    tl.chmod(0o755)


def floor_run(root, path):
    env = dict(os.environ, PATH=path)
    return subprocess.run([sys.executable, str(SCRIPT), "-C", str(root), "REQ-0001"],
                          cwd=root, env=env, text=True, capture_output=True)


# tl: verifies tl-inspect/TEST-0008@5eeee4a55013
def test_an_older_tl_is_refused_naming_the_floor(tmp_path):
    stand_in(tmp_path / "bin", "5.1.1")
    root = tmp_path / "work"
    root.mkdir()
    r = floor_run(root, f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}")
    assert r.returncode == 2, r.stdout + r.stderr
    assert "tl 5.1.1 is older than 5.2.0" in r.stderr
    assert "pip install --upgrade 'throughline>=5.2.0'" in r.stderr
    assert list(root.iterdir()) == []


# tl: verifies tl-inspect/TEST-0008@5eeee4a55013
def test_no_tl_is_refused_naming_the_install(tmp_path):
    (tmp_path / "empty").mkdir()
    root = tmp_path / "work"
    root.mkdir()
    r = floor_run(root, str(tmp_path / "empty"))
    assert r.returncode == 2, r.stdout + r.stderr
    assert "tl is not on PATH" in r.stderr and "throughline>=5.2.0" in r.stderr


# tl: verifies tl-inspect/TEST-0008@5eeee4a55013
def test_the_floor_itself_is_accepted(tmp_path):
    stand_in(tmp_path / "bin", "5.2.0")
    root = tmp_path / "work"
    root.mkdir()
    r = floor_run(root, f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}")
    assert "older than 5.2.0" not in r.stderr and "not on PATH" not in r.stderr


# ── TEST-0009: each graph's check result ────────────────────────────────────

# tl: verifies tl-inspect/TEST-0009@89db7ce0caa4
def test_each_graph_shown_reports_its_errors_and_warnings(repo):
    data = view(repo, repo / "spec", "REQ-0001")
    assert sorted(c["graph"] for c in data["checks"]) == ["app", "spec"]
    for c in data["checks"]:
        said = run("tl", "-C", repo / c["root"], "check", ok=(0, 1))
        m = re.search(r"(\d+) error\(s\), (\d+) warning\(s\)", said.stdout + said.stderr)
        assert (c["errors"], c["warnings"]) == (int(m.group(1)), int(m.group(2)))
    assert re.search(r"tl check spec: \d+ error", inspect(repo, repo / "spec", "REQ-0001").stdout)
    assert view(repo, repo / "spec", "REQ-0001", "--no-check")["checks"] == []


# ── TEST-0010: a view bounded by depth ──────────────────────────────────────

# tl: verifies tl-inspect/TEST-0010@f79851a7835a
def test_a_chain_longer_than_the_depth_is_cut_and_counted(tmp_path):
    g = init(tmp_path / "g", "g")
    new(g, "INT", "The subject")
    new(g, "REQ", "First", ground="INT-0001", attrs=["priority=must"])
    for n in (1, 2, 3):
        new(g, "REQ", f"Rests on {n}", ground=f"REQ-000{n}", attrs=["priority=must"])

    default = view(tmp_path, g, "REQ-0001", "--no-check")
    assert names(default, "blast") == ["g/REQ-0002", "g/REQ-0003"]
    assert default["beyond"] == {"trace": 0, "blast": 1} and default["depth"] == 2
    said = inspect(tmp_path, g, "REQ-0001", "--no-check").stdout
    assert "rests on it: 2 item(s), 1 more beyond depth 2" in said

    one = view(tmp_path, g, "REQ-0001", "--no-check", "--depth", "1")
    assert names(one, "blast") == ["g/REQ-0002"] and one["beyond"]["blast"] == 2

    whole = view(tmp_path, g, "REQ-0001", "--no-check", "--depth", "0")
    assert names(whole, "blast") == ["g/REQ-0002", "g/REQ-0003", "g/REQ-0004"]
    assert whole["beyond"] == {"trace": 0, "blast": 0}
    page = inspect(tmp_path, g, "REQ-0001", "--no-check", "--html", "-").stdout
    assert "--depth 0" in page
