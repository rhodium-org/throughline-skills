"""Fixture tests for the challenge skill's script.

tl-challenge TEST-0001, TEST-0007 and TEST-0009; TEST-0008 is in
test_tl_floor.py. Each test builds a throwaway graph with the real CLI and
asserts what the script's commands report for it. Needs tl from throughline 3.11.0 or later on PATH:
pip install 'throughline>=3.11.0'.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "challenge.py"

if shutil.which("tl") is None:
    raise RuntimeError("tl is not on PATH: pip install 'throughline>=3.11.0'")


# ── helpers ─────────────────────────────────────────────────────────────────

def run(*args, cwd=None):
    r = subprocess.run(list(args), cwd=cwd, text=True, capture_output=True)
    assert r.returncode == 0, f"{args} failed: {r.stdout}\n{r.stderr}"
    return r


def new(root, prefix, title, *, type_, attrs=(), ground=None, ground_type=None):
    args = ["tl", "-C", str(root), "new", prefix, "--no-interactive", "--origin", "ai",
            "--status", "proposed", "--type", type_, "--title", title, "--text", f"{title}."]
    for a in attrs:
        args += ["--attr", a]
    if ground:
        args += ["--ground", ground]
    if ground_type:
        args += ["--ground-type", ground_type]
    return run(*args)


def verification(root, branch_types):
    r = run(sys.executable, str(SCRIPT), "-C", str(root), "verification",
            "--branch-types", branch_types)
    return r.stdout


def branch_line(output, head):
    """The report line under the branch headed by `head`: members, tests, flags."""
    m = re.search(rf"^branch\s+{head}\s.*\n(.*)$", output, re.M)
    assert m, f"no branch {head} in:\n{output}"
    return m.group(1).strip()


def flagged(output):
    return int(re.search(r"^# verification: (\d+) branch", output, re.M).group(1))


# ── fixture ─────────────────────────────────────────────────────────────────

@pytest.fixture
def graph(tmp_path):
    """One intent with two requirements under it. REQ-0001 is verified by an
    automated test on itself and refined by REQ-0003, which a manual test
    verifies; REQ-0002 has no test at all."""
    root = tmp_path / "graph"
    run("tl", "-C", str(root), "init", "--no-demo", "--name", "fixture")
    new(root, "INT", "The subject", type_="intent")
    new(root, "REQ", "A requirement verified directly", type_="requirement",
        attrs=["priority=must"], ground="INT-0001")
    new(root, "REQ", "A requirement nothing verifies", type_="requirement",
        attrs=["priority=must"], ground="INT-0001")
    new(root, "REQ", "A refinement of the first requirement", type_="requirement",
        attrs=["priority=should"], ground="REQ-0001")
    new(root, "TEST", "An automated test of the first requirement", type_="test",
        attrs=["method=automated"], ground="REQ-0001", ground_type="verifies")
    new(root, "TEST", "A manual test of the refinement", type_="test",
        attrs=["method=manual"], ground="REQ-0003", ground_type="verifies")
    return root


# ── TEST-0007: a branch's tests include those verifying its head ────────────

# tl: verifies tl-challenge/TEST-0007
def test_requirement_branch_counts_the_test_on_its_head(graph):
    out = verification(graph, "requirement")
    assert branch_line(out, "REQ-0001") == "members=2 tests: automated=1, manual=1"
    assert branch_line(out, "REQ-0003") == "members=1 tests: manual=1  <- NO AUTOMATED CHECK"
    assert branch_line(out, "REQ-0002") == (
        "members=1 tests: none  untested: REQ-0002  <- NO AUTOMATED CHECK")
    assert flagged(out) == 2


# tl: verifies tl-challenge/TEST-0007
def test_intent_branch_reads_the_same_tests(graph):
    out = verification(graph, "intent")
    assert branch_line(out, "INT-0001") == (
        "members=3 tests: automated=1, manual=1  untested: REQ-0002")
    assert flagged(out) == 0


# tl: verifies tl-challenge/TEST-0007
def test_a_test_on_a_root_head_is_counted_but_the_root_is_never_untested(graph):
    new(graph, "TEST", "An automated test of the intent itself", type_="test",
        attrs=["method=automated"], ground="INT-0001", ground_type="verifies")
    out = verification(graph, "intent")
    assert branch_line(out, "INT-0001") == (
        "members=3 tests: automated=2, manual=1  untested: REQ-0002")


# tl: verifies tl-challenge/TEST-0007
def test_a_deleted_test_no_longer_verifies(graph):
    new(graph, "TEST", "A test later withdrawn", type_="test",
        attrs=["method=automated"], ground="REQ-0002", ground_type="verifies")
    assert branch_line(verification(graph, "requirement"), "REQ-0002") == (
        "members=1 tests: automated=1")

    run("tl", "-C", str(graph), "delete", "TEST-0003", "--reason", "fixture")
    assert branch_line(verification(graph, "requirement"), "REQ-0002") == (
        "members=1 tests: none  untested: REQ-0002  <- NO AUTOMATED CHECK")


# tl: verifies tl-challenge/TEST-0009
def test_script_starts_without_sigpipe():
    """tl-challenge REQ-0009 / TEST-0009: Windows has no signal.SIGPIPE."""
    code = ("import runpy, signal, sys\n"
            f"sys.path.insert(0, {str(SCRIPT.parent)!r})\n"
            "del signal.SIGPIPE\n"
            f"sys.argv = [{str(SCRIPT)!r}, '--help']\n"
            f"runpy.run_path({str(SCRIPT)!r}, run_name='__main__')\n")
    r = subprocess.run([sys.executable, "-c", code], text=True, capture_output=True)
    assert "SIGPIPE" not in r.stderr, r.stderr
    assert r.returncode == 0, r.stderr


# ── TEST-0001: from a dump, in a clean interpreter, every deterministic check ──

def item(root, prefix, title, text, *, type_="requirement", ground="INT-0001",
         ground_type=None, status="proposed"):
    args = ["tl", "-C", str(root), "new", prefix, "--no-interactive", "--origin", "ai",
            "--status", status, "--type", type_, "--title", title, "--text", text]
    if type_ == "requirement":
        args += ["--attr", "priority=must"]
    if type_ == "test":
        args += ["--attr", f"method={ground_type and 'automated' or 'manual'}"]
    if ground:
        args += ["--ground", ground]
    if ground_type:
        args += ["--ground-type", ground_type]
    return re.search(r"created ([A-Z]+-\d+)", run(*args).stdout).group(1)


@pytest.fixture
def challenged(tmp_path):
    """A consumer graph composing a source, holding for each deterministic
    challenger requirement one item that should be found and one that should
    not, as the challenger's own tests describe them."""
    spec = tmp_path / "spec"
    run("tl", "-C", str(spec), "init", "--no-demo", "--name", "spec")
    item(spec, "INT", "The specification", "The specification.", type_="intent", ground=None)
    item(spec, "REQ", "A clause implemented locally", "A clause, and its absence fails.")
    item(spec, "REQ", "A clause nothing implements", "Another clause, and its absence fails.")
    app = tmp_path / "app"
    run("tl", "-C", str(app), "init", "--no-demo", "--name", "app")
    (app / "throughline.toml").open("a").write('\n[[sources]]\nnamespace = "spec"\npath = "../spec"\n')
    run("tl", "-C", str(app), "schema", "linktype", "add", "superseded_by", "--because", "fixture")
    run("tl", "-C", str(app), "schema", "attr", "add", "test", "method", "--kind", "enum",
        "--values", "automated,manual,document", "--because", "fixture")
    u = {}
    u["int"] = item(app, "INT", "The product", "The product.", type_="intent", ground=None)
    u["int2"] = item(app, "INT", "A second product line", "A second line.", type_="intent", ground=None)
    # universal (challenger REQ-0009): one narrow child is flagged, two mechanisms are not
    u["univ"] = item(app, "REQ", "Every page loads in two seconds",
                     "Every page always loads within two seconds, and a slower load fails.")
    u["univ_child"] = item(app, "REQ", "The home page loads in two seconds",
                           "The home page loads within two seconds, and a slower load fails.",
                           ground=u["univ"])
    u["univ_ok"] = item(app, "REQ", "Every form validates its input",
                        "Every form always validates its input, and an invalid entry is refused.")
    for title in ("The login form validates its input", "The signup form validates its input"):
        item(app, "REQ", title, f"{title}, and an invalid entry is refused.", ground=u["univ_ok"])
    # mentions (challenger REQ-0002): a UID in prose with no edge is flagged; with an edge,
    # or naming no item, it is not
    u["mention"] = item(app, "REQ", "A requirement citing another in prose",
                        f"Unlike {u['univ']}, this one refuses a slow page outright.")
    u["mention_ok"] = item(app, "REQ", "A requirement citing another with an edge",
                           f"Like {u['univ_ok']}, and unlike REQ-0999, this one refuses bad input.")
    run("tl", "-C", str(app), "link", u["mention_ok"], u["univ_ok"], "--type", "relates")
    # failure-case (challenger REQ-0007): only the wanted behaviour is flagged
    u["nofail"] = item(app, "REQ", "The page shows a banner", "The page shows a banner.")
    # untestable (challenger REQ-0005): a judgement no observation settles is flagged
    u["vague"] = item(app, "REQ", "The accent colour is used sparingly",
                      "The accent colour is used sparingly, and a page without it fails review.")
    # replacement (challenger REQ-0008): a live item pointing at its replacement is flagged;
    # a rejected one is not
    u["old"] = item(app, "REQ", "An old rule", "An old rule, and breaking it fails.")
    u["new"] = item(app, "REQ", "Its replacement", "Its replacement, and breaking it fails.")
    u["gone"] = item(app, "REQ", "A retired rule", "A retired rule, and breaking it fails.")
    for src in (u["old"], u["gone"]):
        run("tl", "-C", str(app), "link", src, u["new"], "--type", "superseded_by")
    run("tl", "-C", str(app), "status", u["gone"], "rejected")
    # verification (challenger REQ-0004): a branch settled only by inspection is flagged;
    # one with an automated check is not
    item(app, "TEST", "Inspect the home page", "Inspect it.", type_="test", ground=u["univ_child"])
    u["checked"] = item(app, "REQ", "A checked requirement", "It holds, and failing it fails.",
                        ground=u["int2"])
    item(app, "TEST", "Run the check", "Run it.", type_="test", ground=u["checked"],
         ground_type="verifies")
    # unstamped (challenger REQ-0010) and uncovered (challenger REQ-0011): a link into the
    # source without a stamp is listed, a stamped one is not; a source clause nothing
    # implements is listed, an implemented one is not
    u["impl"] = item(app, "REQ", "Implements the first clause", "It implements it, or fails.",
                     ground="spec:REQ-0001", ground_type="implements")
    u["stamped"] = item(app, "REQ", "Stamped against the specification",
                        "It derives from it, or fails.", ground="spec:INT-0001")
    run("tl", "-C", str(app), "link", u["stamped"], "spec:INT-0001", "--type", "derives_from",
        "--stamp")
    dump = tmp_path / "app.json"
    run("tl", "-C", str(app), "dump", "-o", str(dump))
    return app, dump, u


def clean(dump, *command):
    """The script on a saved dump, in an interpreter that cannot see site-packages."""
    r = subprocess.run([sys.executable, "-S", "-E", "-s", str(SCRIPT), "--dump", str(dump),
                        *command], text=True, capture_output=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


# tl: verifies tl-challenge/TEST-0001
def test_every_deterministic_challenge_runs_from_a_dump_in_a_clean_interpreter(challenged):
    import ast
    local = {p.stem for p in SCRIPT.parent.glob("*.py")}
    for node in ast.walk(ast.parse(SCRIPT.read_text())):
        names = ([a.name for a in node.names] if isinstance(node, ast.Import) else
                 [node.module] if isinstance(node, ast.ImportFrom) else [])
        for name in names:
            assert name.split(".")[0] in sys.stdlib_module_names | local, name
    app, dump, u = challenged

    out = clean(dump, "--local-only", "mentions")                          # challenger REQ-0002
    assert re.search(rf"^mentions\s+{u['mention']} -> {u['univ']}\s", out, re.M)
    assert u["mention_ok"] not in out and "REQ-0999" not in out
    out = clean(dump, "--local-only", "universal")                         # challenger REQ-0009
    assert re.search(rf"^universal {u['univ']}\s.*one child: {u['univ_child']}", out, re.M)
    assert not re.search(rf"^universal {u['univ_ok']}\s", out, re.M)
    out = clean(dump, "--local-only", "failure-case")                      # challenger REQ-0007
    assert re.search(rf"^no-failure {u['nofail']}\s", out, re.M)
    assert not re.search(rf"^no-failure {u['univ']}\s", out, re.M)
    out = clean(dump, "--local-only", "untestable")                        # challenger REQ-0005
    assert re.search(rf"^untestable {u['vague']}\s+\[sparingly\]", out, re.M)
    assert not re.search(rf"^untestable {u['univ']}\s", out, re.M)
    out = clean(dump, "--local-only", "replacement")                       # challenger REQ-0008
    assert re.search(rf"^replacement {u['old']} --superseded_by--> {u['new']}", out, re.M)
    assert not re.search(rf"^replacement {u['gone']}\s", out, re.M)
    out = clean(dump, "verification", "--branch-types", "intent")          # challenger REQ-0004
    assert "<- NO AUTOMATED CHECK" in branch_line(out, u["int"])
    assert "NO AUTOMATED CHECK" not in branch_line(out, u["int2"])
    out = clean(dump, "unstamped", "--namespace", "spec")                  # challenger REQ-0010
    assert re.search(rf"^unstamped {u['impl']} --implements--> spec:REQ-0001$", out, re.M)
    assert not re.search(rf"^unstamped {u['stamped']} --derives_from--> spec:INT-0001$", out, re.M)
    out = clean(dump, "uncovered", "--namespace", "spec", "--types", "requirement",
                "--links", "implements")                                   # challenger REQ-0011
    assert re.search(r"^uncovered spec:REQ-0002\s", out, re.M)
    assert not re.search(r"^uncovered spec:REQ-0001\s", out, re.M)

    # given a graph root, the script runs tl itself, and every check it names runs
    out = run(sys.executable, str(SCRIPT), "-C", str(app), "all").stdout
    for check in ("mentions", "universal", "verification", "failure-case", "untestable",
                  "replacement", "unstamped"):
        assert f"── {check} ──" in out and f"# {check}:" in out, check
