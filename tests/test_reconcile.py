"""Fixture tests for the reconcile skill's script.

tl-reconcile TEST-0001 to TEST-0011 and TEST-0017, one per requirement the
script carries. Each test builds a throwaway git repository holding graphs made
with the real CLI and code citing their items, and drives scripts/reconcile.py
over it. TEST-0012 to TEST-0016 are read against SKILL.md by a person.
Needs tl from throughline 3.11.0 or later on PATH.
"""
import ast
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "reconcile.py"
MARK = "tl:"                       # kept apart so this file's own lines cite nothing
TL = shutil.which("tl")

if TL is None:
    raise RuntimeError("tl is not on PATH: pip install 'throughline>=3.11.0'")


# ── helpers ─────────────────────────────────────────────────────────────────

def run(*args, cwd=None, env=None):
    return subprocess.run(list(args), cwd=cwd, env=env, text=True, capture_output=True)


def ok(*args, **kw):
    r = run(*args, **kw)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def reconcile(repo, *args, env=None):
    return run(sys.executable, str(SCRIPT), "-C", str(repo), *args, env=env)


def scan(repo, *args, env=None):
    r = reconcile(repo, "scan", "--json", *args, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout)


def cite(link, refs, opener="#", closer=""):
    return f"{opener} {MARK} {link} {refs}{closer}".strip()


def kinds(report):
    return sorted((f["kind"], f.get("ref", "")) for f in report["findings"])


class Graph:
    def __init__(self, repo, d, name):
        self.root = repo / d
        ok(TL, "-C", str(self.root), "init", "--no-demo", "--name", name)
        ok(TL, "-C", str(self.root), "schema", "attr", "add", "test", "method", "--kind", "enum",
           "--values", "automated,manual,document", "--because", "fixture")
        self.new("INT", "The root", type_="intent", origin="human")

    def tl(self, *args):
        return ok(TL, "-C", str(self.root), *args)

    def new(self, prefix, title, *, text=None, ground=(), ground_type=None, type_=None,
            origin="ai", attrs=()):
        args = ["new", prefix, "--title", title, "--text", text or f"{title}.", "--origin", origin,
                "--status", "proposed", "--no-interactive"]
        if type_:
            args += ["--type", type_]
        for g in ground:
            args += ["--ground", g]
        if ground_type:
            args += ["--ground-type", ground_type]
        for kv in attrs:
            args += ["--attr", kv]
        return re.search(r"created ([A-Z]+-\d+)", self.tl(*args)).group(1)

    def req(self, title, *, ratified=True, **kw):
        uid = self.new("REQ", title, ground=kw.pop("ground", ["INT-0001"]),
                       attrs=["priority=must"], **kw)
        if ratified:
            self.ratify(uid)
        return uid

    def ratify(self, uid):
        self.tl("ratify", uid, "--by", "Tester")

    def item(self, uid):
        return next(i for i in json.loads(self.tl("dump"))["items"] if i["uid"] == uid)


@pytest.fixture
def repo(tmp_path):
    repo = tmp_path / "work"
    repo.mkdir()
    ok("git", "init", "-q", str(repo))
    ok("git", "-C", str(repo), "config", "user.email", "t@example.com")
    ok("git", "-C", str(repo), "config", "user.name", "Tester")
    return repo


def write(repo, rel, *lines):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n")
    return p


def commit(repo, msg="c", when=None):
    env = dict(os.environ)
    if when:
        env.update(GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when)
    ok("git", "-C", str(repo), "add", "-A")
    ok("git", "-C", str(repo), "commit", "-q", "-m", msg, env=env)
    return ok("git", "-C", str(repo), "rev-parse", "HEAD").strip()


# ── one test per requirement ────────────────────────────────────────────────

# tl: verifies tl-reconcile/TEST-0001
def test_each_comment_form_parses_and_a_broken_marker_is_reported(repo, tmp_path):
    spec = Graph(tmp_path, "spec", "spec")             # outside the repo: borrowed, not counted
    spec.req("A borrowed clause")
    g = Graph(repo, "g", "app")
    r1, r2 = g.req("One"), g.req("Two")
    with (g.root / "throughline.toml").open("a") as fh:
        fh.write(f'\n[[sources]]\nnamespace = "spec"\npath = "{spec.root}"\n')
    stamp = g.item(r1)["attrs"]["ratified_fingerprint"].split(":")[1][:8]
    write(repo, "src/forms.txt",
          cite("implements", r1, "#"), cite("implements", r1, "//"), cite("implements", r1, "--"),
          cite("implements", r1, ";"), cite("implements", r1, "%"),
          cite("implements", r1, "/*", " */"), cite("implements", r1, " *"),
          cite("implements", r1, "<!--", " -->"), cite("implements", r1, "   "),
          cite("implements", f"{r1}, {r2}"),
          cite("satisfies", "spec:REQ-0001"),
          cite("implements", f"{r1}@{stamp}"),
          cite("implements", f"{r1}@{stamp[:7]}"),
          f"# {MARK}",
          f"# {MARK}shape is not the marker")
    commit(repo)
    report = scan(repo, "src")
    assert report["citations"] == 14                   # the last line is no citation at all
    assert report["references"] == 13 and report["stamped"] == 1
    malformed = [f for f in report["findings"] if f["kind"] == "malformed"]
    assert [f["line"] for f in malformed] == [13, 14]
    assert "shorter than 8" in malformed[0]["message"]
    assert not [f for f in report["findings"] if f["kind"] in
                ("unknown-graph", "unqualified", "no-such-item", "dead-item", "stale",
                 "unknown-link-type")]
    # a second graph in the repository makes every bare reference ambiguous
    Graph(repo, "other", "other")
    write(repo, "src/qualified.txt", cite("implements", f"app/{r1}"))
    commit(repo)
    report = scan(repo, "src")
    unqualified = [f for f in report["findings"] if f["kind"] == "unqualified"]
    assert len(unqualified) == 13                      # every bare reference, the borrowed one too
    assert not [f for f in report["findings"] if f.get("path") == "src/qualified.txt"]


# tl: verifies tl-reconcile/TEST-0002
def test_untracked_graph_and_excluded_files_are_not_read(repo):
    g = Graph(repo, "g", "app")
    r1 = g.req("One")
    write(repo, "src/a.py", cite("implements", r1))
    write(repo, "g/notes.md", cite("implements", "REQ-0099"))
    write(repo, "vendor/c.py", cite("implements", "REQ-0099"))
    commit(repo)
    write(repo, "src/untracked.py", cite("implements", "REQ-0099"))
    report = scan(repo, "--exclude", "vendor")
    assert report["files"] == 1 and report["citations"] == 1
    assert not [f for f in report["findings"] if f.get("path")]
    text = reconcile(repo, "scan", "--exclude", "vendor").stdout
    assert text.startswith("read 1 file(s), found 1 citation(s)")


# tl: verifies tl-reconcile/TEST-0002
def test_a_graph_at_the_root_skips_only_its_own_files(repo):
    g = Graph(repo, ".", "app")
    r1 = g.req("One")
    write(repo, "src/a.py", cite("implements", r1))
    write(repo, "requirements/notes.md", cite("implements", "REQ-0099"))
    commit(repo)
    report = scan(repo)
    assert report["files"] == 1 and report["citations"] == 1
    assert not [f for f in report["findings"] if f.get("path")]


# tl: verifies tl-reconcile/TEST-0003
def test_every_unresolvable_citation_is_reported_with_file_and_line(repo):
    g = Graph(repo, "g", "app")
    live, gone, rejected = g.req("Live"), g.req("Gone", ratified=False), g.req("No", ratified=False)
    g.tl("delete", gone)
    g.tl("status", rejected, "rejected")
    Graph(repo, "d1", "dup")
    Graph(repo, "d2", "dup")
    write(repo, "src/x.py",
          cite("implements", f"app/{live}"),
          cite("implements", "app/REQ-0099"),
          cite("implements", f"app/{gone}"),
          cite("implements", f"app/{rejected}"),
          cite("builds", f"app/{live}"),
          cite("implements", f"nope/{live}"),
          cite("implements", "dup/INT-0001"))
    commit(repo)
    report = scan(repo, "src", "--graph", "app")
    located = [(f["kind"], f["line"]) for f in report["findings"] if f.get("path") == "src/x.py"]
    assert sorted(located) == sorted([("no-such-item", 2), ("dead-item", 3), ("dead-item", 4),
                                      ("unknown-link-type", 5), ("unknown-graph", 6),
                                      ("ambiguous-graph", 7)])


# tl: verifies tl-reconcile/TEST-0004
def test_uncited_items_are_listed_apart_from_parents_realised_by_children(repo):
    g = Graph(repo, "g", "app")
    cited, uncited, parent = g.req("Cited"), g.req("Uncited"), g.req("Parent")
    child = g.req("Child", ratified=False)
    g.tl("link", child, parent, "--type", "refines")
    g.ratify(child)
    proposed = g.req("Proposed", ratified=False)
    nfr = g.new("NFR", "Fast", ground=["INT-0001"])
    g.ratify(nfr)
    write(repo, "src/x.py", cite("implements", cited), cite("implements", child))
    commit(repo)
    report = scan(repo)
    assert [f["ref"] for f in report["findings"] if f["kind"] == "uncited"] == [uncited]
    assert [f["ref"] for f in report["realised_through_children"]] == [parent]
    assert proposed not in json.dumps(report["findings"])
    report = scan(repo, "--types", "requirement,nfr")
    assert {f["ref"] for f in report["findings"] if f["kind"] == "uncited"} == {uncited, nfr}


# tl: verifies tl-reconcile/TEST-0005
def test_status_contradictions_are_reported_both_ways(repo):
    g = Graph(repo, "g", "app")
    built = g.req("Claimed built")
    g.tl("status", built, "implemented")
    proposed = g.req("Proposed", ratified=False)
    deferred = g.req("Deferred", ratified=False)
    g.tl("status", deferred, "deferred")
    suspect = g.req("Suspect")
    g.tl("status", suspect, "suspect")
    write(repo, "src/x.py", cite("implements", proposed), cite("implements", deferred),
          cite("satisfies", suspect))
    commit(repo)
    found = kinds(scan(repo))
    assert ("claimed-absent", built) in found
    assert ("unaccepted", proposed) in found and ("unaccepted", deferred) in found
    assert ("under-question", suspect) in found


# tl: verifies tl-reconcile/TEST-0006
def test_unwired_tests_and_unrecorded_test_citations_are_reported(repo):
    g = Graph(repo, "g", "app")
    r1, r2 = g.req("Tested"), g.req("Untested")
    auto = g.new("TEST", "Automated", ground=[r1], ground_type="verifies", attrs=["method=automated"])
    manual = g.new("TEST", "Manual", ground=[r1], ground_type="verifies", attrs=["method=manual"])
    empty = g.new("TEST", "Verifies nothing", ground=["INT-0001"], attrs=["method=manual"])
    write(repo, "tests/t.py", cite("verifies", empty), cite("verifies", r2))
    commit(repo)
    found = kinds(scan(repo))
    assert ("not-wired", auto) in found and ("not-wired", manual) not in found
    assert ("unrecorded-test", empty) in found and ("unrecorded-test", r2) in found


# tl: verifies tl-reconcile/TEST-0007
def test_a_stamp_goes_stale_on_text_not_title_and_names_its_edition(repo):
    g = Graph(repo, "g", "app")
    r1 = g.req("Stamped", text="Does one thing.")
    r2 = g.req("Unstamped")
    stamp = g.item(r1)["attrs"]["ratified_fingerprint"].split(":")[1][:12]
    write(repo, "src/x.py", cite("implements", f"{r1}@{stamp}"), cite("implements", r2))
    commit(repo)
    g.tl("amend", r1, "--title", "Stamped, retitled")
    retitled = commit(repo)
    report = scan(repo)
    assert not [f for f in report["findings"] if f["kind"] == "stale"]
    g.tl("amend", r1, "--text", "Does another thing.")
    commit(repo)
    report = scan(repo)
    stale = [f for f in report["findings"] if f["kind"] == "stale"]
    assert len(stale) == 1 and stale[0]["ref"] == r1 and stale[0]["line"] == 1
    assert retitled[:12] in stale[0]["message"]
    assert report["stamped"] == 1 and report["references"] == 2
    assert not [f for f in report["findings"] if f.get("ref") == r2]


# tl: verifies tl-reconcile/TEST-0008
def test_restamp_touches_only_the_named_items_citations(repo):
    g = Graph(repo, "g", "app")
    r1, r2 = g.req("One"), g.req("Two")
    write(repo, "src/a.py", cite("implements", f"{r1}@deadbeef"))
    write(repo, "src/b.py", cite("implements", r1))
    write(repo, "src/c.py", cite("implements", f"{r2}@deadbeef"))
    commit(repo)
    r = reconcile(repo, "restamp", r1)
    assert r.returncode == 0, r.stdout + r.stderr
    fp = g.item(r1)["attrs"]["ratified_fingerprint"].split(":")[1][:12]
    assert (repo / "src/a.py").read_text().strip() == cite("implements", f"{r1}@{fp}")
    assert (repo / "src/b.py").read_text().strip() == cite("implements", f"{r1}@{fp}")
    assert "deadbeef" in (repo / "src/c.py").read_text()
    stale = [f["ref"] for f in scan(repo)["findings"] if f["kind"] == "stale"]
    assert stale == [r2]
    # there is no form that restamps everything at once
    assert reconcile(repo, "restamp").returncode == 2
    assert reconcile(repo, "restamp", "--all").returncode == 2
    assert "--all" not in reconcile(repo, "restamp", "--help").stdout


# tl: verifies tl-reconcile/TEST-0009
def test_unstamped_citations_whose_item_moved_are_listed_first(repo):
    g = Graph(repo, "g", "app")
    r1, r2 = g.req("Moves later"), g.req("Stays")
    write(repo, "src/a.py", cite("implements", r2))
    write(repo, "src/b.py", cite("implements", r1))
    commit(repo, when="2026-01-01T00:00:00Z")
    g.tl("amend", r1, "--text", "Moves later, and says so.")
    commit(repo, when="2026-02-01T00:00:00Z")
    report = scan(repo)
    order = [row["ref"] for row in report["review_order"]]
    assert order == [r1, r2]
    assert report["review_order"][0]["item_changed_after_code"] is True
    assert report["findings"] == []


# tl: verifies tl-reconcile/TEST-0010
def test_the_table_is_stable_written_between_markers_and_checked(repo):
    g = Graph(repo, "g", "app")
    r1, r2 = g.req("One"), g.req("Two")
    write(repo, "src/a.py", cite("implements", r1))
    write(repo, "docs/trace.md", "# Trace", "", "<!-- reconcile:begin -->",
          "<!-- reconcile:end -->", "", "After.")
    commit(repo)
    first, second = reconcile(repo, "table").stdout, reconcile(repo, "table").stdout
    assert first == second and f"`{r1}`" in first and "`src/a.py:1`" in first
    assert reconcile(repo, "table", "--write", "docs/trace.md").returncode == 0
    doc = (repo / "docs/trace.md").read_text()
    assert first in doc and doc.startswith("# Trace") and doc.rstrip().endswith("After.")
    assert reconcile(repo, "table", "--check", "docs/trace.md").returncode == 0
    write(repo, "src/b.py", cite("implements", r2))
    commit(repo)
    assert reconcile(repo, "table", "--check", "docs/trace.md").returncode == 1
    assert reconcile(repo, "table", "--write", "docs/trace.md").returncode == 0
    assert reconcile(repo, "table", "--check", "docs/trace.md").returncode == 0


# tl: verifies tl-reconcile/TEST-0011
def test_standard_library_only_old_tl_refused_gate_only_when_asked(repo, tmp_path):
    local = {p.stem for p in SCRIPT.parent.glob("*.py")}
    for node in ast.walk(ast.parse(SCRIPT.read_text())):
        names = ([a.name for a in node.names] if isinstance(node, ast.Import) else
                 [node.module] if isinstance(node, ast.ImportFrom) else [])
        for name in names:
            top = name.split(".")[0]
            assert top in sys.stdlib_module_names or top in local, name
    g = Graph(repo, "g", "app")
    g.req("One")
    write(repo, "src/a.py", cite("implements", "REQ-0099"))
    write(repo, "docs/trace.md", "<!-- reconcile:begin -->", "<!-- reconcile:end -->")
    commit(repo)
    assert reconcile(repo, "scan").returncode == 0
    assert reconcile(repo, "scan", "--gate").returncode == 1
    assert reconcile(repo, "table", "--check", "docs/trace.md").returncode == 1   # stale, no --gate
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "tl").write_text("#!/bin/sh\necho 'tl 3.10.0'\n")
    (bin_dir / "tl").chmod(0o755)
    env = dict(os.environ, PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    r = reconcile(repo, "scan", env=env)
    assert r.returncode == 2 and "older than 3.11.0" in r.stderr


# tl: verifies tl-reconcile/TEST-0017
def test_a_fingerprint_disagreeing_with_tl_stops_the_run(repo, tmp_path):
    g = Graph(repo, "g", "app")
    r1 = g.req("Stamped")
    fp = g.item(r1)["attrs"]["ratified_fingerprint"]
    write(repo, "src/a.py", cite("implements", f"{r1}@{fp.split(':')[1][:12]}"))
    commit(repo)
    report = scan(repo)
    assert not [f for f in report["findings"] if f["kind"] == "stale"]
    # a ratification tl itself reads as stale is not the script's to dispute
    item_file = g.root / "requirements" / f"{r1}.yml"
    original = item_file.read_text()
    item_file.write_text(original.replace(fp, "sha256:" + "0" * 64))
    assert "ratified-stale" in run(TL, "-C", str(g.root), "check").stdout
    assert reconcile(repo, "scan").returncode == 0
    item_file.write_text(original)
    # a tl whose dump drops the normative attribute makes the computation disagree
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "tl").write_text(
        f"#!{sys.executable}\n"
        "import json, subprocess, sys\n"
        f"p = subprocess.run([{TL!r}, *sys.argv[1:]], capture_output=True, text=True)\n"
        "out = p.stdout\n"
        "if 'dump' in sys.argv[1:]:\n"
        "    d = json.loads(out)\n"
        "    for i in d['items']:\n"
        "        i.get('attrs', {}).pop('priority', None)\n"
        "    out = json.dumps(d)\n"
        "sys.stdout.write(out); sys.stderr.write(p.stderr); sys.exit(p.returncode)\n")
    (bin_dir / "tl").chmod(0o755)
    env = dict(os.environ, PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    r = reconcile(repo, "scan", env=env)
    assert r.returncode == 2, r.stdout + r.stderr
    assert r1 in r.stderr and "disagrees" in r.stderr
