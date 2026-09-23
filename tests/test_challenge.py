"""Fixture tests for the challenge skill's script.

tl-challenge TEST-0007; TEST-0008 is in test_tl_floor.py. Each test builds a
throwaway graph with the real CLI and asserts what the script's verification
command reports for it. Needs tl from throughline 3.11.0 or later on PATH:
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

def test_requirement_branch_counts_the_test_on_its_head(graph):
    out = verification(graph, "requirement")
    assert branch_line(out, "REQ-0001") == "members=2 tests: automated=1, manual=1"
    assert branch_line(out, "REQ-0003") == "members=1 tests: manual=1  <- NO AUTOMATED CHECK"
    assert branch_line(out, "REQ-0002") == (
        "members=1 tests: none  untested: REQ-0002  <- NO AUTOMATED CHECK")
    assert flagged(out) == 2


def test_intent_branch_reads_the_same_tests(graph):
    out = verification(graph, "intent")
    assert branch_line(out, "INT-0001") == (
        "members=3 tests: automated=1, manual=1  untested: REQ-0002")
    assert flagged(out) == 0


def test_a_test_on_a_root_head_is_counted_but_the_root_is_never_untested(graph):
    new(graph, "TEST", "An automated test of the intent itself", type_="test",
        attrs=["method=automated"], ground="INT-0001", ground_type="verifies")
    out = verification(graph, "intent")
    assert branch_line(out, "INT-0001") == (
        "members=3 tests: automated=2, manual=1  untested: REQ-0002")


def test_a_deleted_test_no_longer_verifies(graph):
    new(graph, "TEST", "A test later withdrawn", type_="test",
        attrs=["method=automated"], ground="REQ-0002", ground_type="verifies")
    assert branch_line(verification(graph, "requirement"), "REQ-0002") == (
        "members=1 tests: automated=1")

    run("tl", "-C", str(graph), "delete", "TEST-0003", "--reason", "fixture")
    assert branch_line(verification(graph, "requirement"), "REQ-0002") == (
        "members=1 tests: none  untested: REQ-0002  <- NO AUTOMATED CHECK")
