"""Fixture tests for the assess skill's script.

tl-assess TEST-0001 to TEST-0009, TEST-0011 and TEST-0012; TEST-0010 is in
test_tl_floor.py. Each test
builds a throwaway graph or repository with the real CLI, or a synthetic
transcript, and asserts the numbers the script reports. Needs tl from
throughline 3.11.0 or later on PATH: pip install 'throughline>=3.11.0'.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "assess.py"
RATIFIER = "Ada Lovelace"

if shutil.which("tl") is None:
    raise RuntimeError("tl is not on PATH: pip install 'throughline>=3.11.0'")


def run(*args, cwd=None, check=True):
    r = subprocess.run(list(args), cwd=cwd, text=True, capture_output=True)
    if check and r.returncode != 0:
        raise AssertionError(f"{args} failed: {r.stdout}\n{r.stderr}")
    return r


def assess(*args, cwd=None, check=True):
    r = run(sys.executable, str(SCRIPT), *args, cwd=cwd, check=check)
    return json.loads(r.stdout) if r.stdout.strip().startswith("{") else r


def git(repo, *args):
    return run("git", "-C", str(repo), *args)


def item(path: Path, uid: str, type_: str, title: str, status="proposed", links=(), attrs=None, ratified=False):
    # Only a requirement is normative: its priority attribute is declared so.
    normative = "true" if type_ == "requirement" else "false"
    body = [f"uid: {uid}", f"type: {type_}", f"status: {status}", f"title: {title}", f"text: {title}.", f"normative: {normative}"]
    if links:
        body.append("links:")
        for target, kind in links:
            body.append(f"- target: {target}")
            body.append(f"  type: {kind}")
    body.append("attrs:")
    for k, v in (attrs or {"origin": "ai"}).items():
        body.append(f"  {k}: {v}")
    if ratified:
        body.append(f"  ratified_by: {RATIFIER}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(body) + "\n")


@pytest.fixture
def repo(tmp_path):
    repo = tmp_path / "work"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "t@example.org")
    git(repo, "config", "user.name", "Tester")
    (repo / "idd").mkdir()
    run("tl", "init", "--no-demo", cwd=repo / "idd")
    return repo


def graph_with_items(repo):
    idd = repo / "idd"
    item(idd / "vision" / "INT-0001.yml", "INT-0001", "intent", "The root")
    run("tl", "-C", str(idd), "ratify", "INT-0001", "--by", RATIFIER, check=False)
    item(idd / "requirements" / "REQ-0001.yml", "REQ-0001", "requirement", "A ratified requirement",
         links=[("INT-0001", "derives_from")], attrs={"priority": "must", "origin": "ai"})
    item(idd / "requirements" / "REQ-0002.yml", "REQ-0002", "requirement", "A proposed requirement",
         links=[("INT-0001", "derives_from")], attrs={"priority": "should", "origin": "human"})
    item(idd / "tests" / "TEST-0001.yml", "TEST-0001", "test", "A test", links=[("REQ-0001", "verifies")],
         attrs={"origin": "ai", "method": "automated"})
    item(idd / "tests" / "TEST-0002.yml", "TEST-0002", "test", "Another test", links=[("REQ-0002", "verifies")],
         attrs={"origin": "ai", "method": "manual"})
    return idd


# tl: verifies tl-assess/TEST-0001@59f051e4a8e0
def test_graph_measure_counts_the_fixture(repo):  # TEST-0001
    idd = graph_with_items(repo)
    run("tl", "-C", str(idd), "ratify", "REQ-0001", "--by", RATIFIER, check=False)
    run("tl", "-C", str(idd), "ratify", "TEST-0001", "--by", RATIFIER, check=False)
    g = assess("graph", "-C", str(idd))
    assert g["items_local"] == 5
    assert g["by_type"] == {"intent": 1, "requirement": 2, "test": 2}
    assert g["by_origin"] == {"ai": 4, "human": 1}
    assert g["by_status"]["proposed"] == 2
    assert g["ratified_by"] == {RATIFIER: 3}
    assert g["tests_by_method"] == {"automated": 1, "manual": 1}
    assert g["citations"] == 0 and g["local_links"] == 4


# tl: verifies tl-assess/TEST-0002@0193c71f7fae
def test_git_measure_counts_commits_tags_citations_and_amendments(repo):  # TEST-0002
    idd = graph_with_items(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "A graph (INT-0001)")
    git(repo, "tag", "v0.1.0")
    run("tl", "-C", str(idd), "ratify", "REQ-0001", "--by", RATIFIER, check=False)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "Ratified: REQ-0001")
    p = idd / "requirements" / "REQ-0001.yml"
    p.write_text(p.read_text().replace("A ratified requirement.", "A ratified requirement, amended."))
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "An amendment with no item named")
    git(repo, "tag", "v0.2.0")
    run("tl", "-C", str(idd), "ratify", "REQ-0001", "--by", RATIFIER, "--accept-change", check=False)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "Re-ratified REQ-0001, which is not an amendment")
    g = assess("git", "-C", str(idd))
    assert g["commits"] == 4
    assert g["editions"] == 2 and [t["tag"] for t in g["tags"]] == ["v0.1.0", "v0.2.0"]
    assert g["commits_citing_an_item"] == 3
    assert g["items_ratified"] >= 1
    assert g["items_amended_after_ratification"] == 1 and g["amending_commits"] == 1
    assert g["authors"] == {"Tester": 4}


# tl: verifies tl-assess/TEST-0009@fb5cb4b78fe3
def test_git_measure_follows_a_rename(repo):  # TEST-0009
    idd = graph_with_items(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "A graph (INT-0001)")
    run("tl", "-C", str(idd), "ratify", "REQ-0001", "--by", RATIFIER, check=False)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "Ratified: REQ-0001")
    git(repo, "mv", "idd", "graph")
    p = repo / "graph" / "requirements" / "REQ-0001.yml"
    p.write_text(p.read_text().replace("A ratified requirement.", "A ratified requirement, amended in the move."))
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "The graph moved and REQ-0001 amended in the same commit")
    run("tl", "-C", str(repo / "graph"), "ratify", "REQ-0001", "--by", RATIFIER, "--accept-change", check=False)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "Re-ratified REQ-0001")
    g = assess("git", "-C", str(repo / "graph"))
    assert g["items_ratified"] >= 1
    assert g["items_amended_after_ratification"] == 1 and g["amending_commits"] == 1
    git(repo, "mv", "graph", "moved")
    git(repo, "commit", "-q", "-m", "Moved again, nothing amended")
    g = assess("git", "-C", str(repo / "moved"))
    assert g["items_amended_after_ratification"] == 1 and g["amending_commits"] == 1


# tl: verifies tl-assess/TEST-0003@1ef21dc350ce
def test_docs_and_tests_are_measured_not_invented(repo, tmp_path):  # TEST-0003
    idd = graph_with_items(repo)
    (idd / "docs").mkdir()
    (idd / "docs" / "a.md").write_text("one two three\n")
    (idd / "docs" / "b.md").write_text("four five\n")
    d = assess("docs", "-C", str(idd))
    assert d["words"] == 5 and d["documents"] == {"a.md": 3, "b.md": 2}
    assert d["docs_check_ok"] in (True, False)
    results = tmp_path / "results.txt"
    results.write_text("# tests 3\n# pass 2\n# fail 1\n")
    (repo / "tests").mkdir()
    (repo / "tests" / "TEST-0001.test.ts").write_text("")
    t = assess("tests", "--glob", "tests/TEST-*.test.ts", "--results", str(results), "--repo", str(repo))
    assert t == {"test_files": 1, "pattern": "tests/TEST-*.test.ts", "passed": 2, "failed": 1}
    t2 = assess("tests", "--glob", "tests/TEST-*.test.ts", "--repo", str(repo))
    assert "passed" not in t2


def transcript(path: Path, cwd: str = "/w"):
    def ts(minutes):
        return f"2026-09-01T10:{minutes:02d}:00.000Z"
    usage = {"input_tokens": 10, "output_tokens": 100, "cache_creation_input_tokens": 1000,
             "cache_read_input_tokens": 5000, "output_tokens_details": {"thinking_tokens": 40}}
    lines = [
        {"type": "user", "sessionId": "s1", "cwd": cwd, "timestamp": ts(0), "message": {"role": "user", "content": "start"}},
        {"type": "assistant", "timestamp": ts(1), "message": {"role": "assistant", "model": "m", "usage": usage,
                                                              "content": [{"type": "tool_use", "name": "Bash", "input": {}}]}},
        {"type": "user", "timestamp": ts(2), "toolUseResult": {"stdout": ""}, "message": {"role": "user", "content": [{"type": "tool_result"}]}},
        {"type": "assistant", "timestamp": ts(3), "message": {"role": "assistant", "model": "m", "usage": usage,
                                                              "content": [{"type": "tool_use", "name": "Bash", "input": {}}, {"type": "tool_use", "name": "Read", "input": {}}]}},
        "this line is not json",
        {"type": "user", "timestamp": ts(33), "message": {"role": "user", "content": "after a long gap"}},
        {"type": "assistant", "timestamp": ts(34), "message": {"role": "assistant", "model": "m", "usage": usage, "content": [{"type": "text", "text": "done"}]}},
    ]
    path.write_text("\n".join(json.dumps(l) if not isinstance(l, str) else l for l in lines) + "\n")


# tl: verifies tl-assess/TEST-0004@e2b170726990
def test_sessions_measure_a_synthetic_transcript(tmp_path):  # TEST-0004
    p = tmp_path / "s1.jsonl"
    transcript(p)
    s = assess("sessions", str(p), "--idle-gap", "10")
    one = s["sessions"][0]
    assert one["session_id"] == "s1" and one["cwd"] == "/w"
    assert one["wall_clock_hours"] == pytest.approx(34 / 60, abs=0.01)
    assert one["active_hours"] == pytest.approx(4 / 60, abs=0.01)
    assert one["user_turns"] == 2 and one["assistant_turns"] == 3 and one["tool_results"] == 1
    assert one["tool_calls_by_name"] == {"Bash": 2, "Read": 1} and one["api_calls"] == 3
    assert one["tokens"] == {"input_tokens": 30, "output_tokens": 300, "cache_creation_input_tokens": 3000,
                             "cache_read_input_tokens": 15000, "thinking_tokens": 120}
    assert s["totals"]["tokens_output_tokens"] == 300
    windowed = assess("sessions", str(p), "--until", "2026-09-01T10:10:00Z")
    assert windowed["sessions"][0]["user_turns"] == 1 and windowed["sessions"][0]["api_calls"] == 2


# tl: verifies tl-assess/TEST-0005@42136a1e4c1f
def test_done_fails_per_criterion_then_passes(repo, tmp_path):  # TEST-0005
    idd = graph_with_items(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "A graph (INT-0001)")
    r = run(sys.executable, str(SCRIPT), "done", "-C", str(idd), check=False)
    assert r.returncode == 1 and json.loads(r.stdout)["criteria"]["nothing_awaiting_ratification"] is False
    for uid in ("REQ-0001", "REQ-0002", "TEST-0001", "TEST-0002"):
        run("tl", "-C", str(idd), "ratify", uid, "--by", RATIFIER, check=False)
    r = run(sys.executable, str(SCRIPT), "done", "-C", str(idd), check=False)
    assert json.loads(r.stdout)["criteria"]["working_tree_clean"] is False
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "Ratified (REQ-0001)")
    results = tmp_path / "r.txt"
    results.write_text("# pass 1\n# fail 1\n")
    r = run(sys.executable, str(SCRIPT), "done", "-C", str(idd), "--results", str(results), check=False)
    assert r.returncode == 1 and json.loads(r.stdout)["criteria"]["tests_green"] is False
    results.write_text("# pass 2\n# fail 0\n")
    r = run(sys.executable, str(SCRIPT), "done", "-C", str(idd), "--results", str(results), check=False)
    out = json.loads(r.stdout)
    assert r.returncode == 0 and out["done"] is True, out


# tl: verifies tl-assess/TEST-0006@797486ae00bb
def test_record_writes_files_keeps_earlier_ones_and_indexes_the_collection(repo, tmp_path):  # TEST-0006
    idd = graph_with_items(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "A graph (INT-0001)")
    t = tmp_path / "s1.jsonl"
    transcript(t)
    coll = tmp_path / "collection"
    first = assess("record", "-C", str(idd), "--name", "fixture", "--label", "A fixture", "--sessions", str(t), "--collection", str(coll))
    second = assess("record", "-C", str(idd), "--name", "fixture", "--label", "A fixture", "--sessions", str(t), "--collection", str(coll))
    md = Path(second["written"][1]).read_text()
    for heading in ("## Measured", "## What was built", "## Defects found after the first \"done\"", "## What the graph caught", "## Human effort", "## Verdict"):
        assert heading in md
    assert "| Tools | tl: " in md and "| Skill | tl:assess " in md and second["provenance"]["repository_commit"]
    assert "| Human turns / AI turns | 2 / 3 |" in md
    assert len(list((repo / "docs" / "assessment").glob("*.json"))) == 2
    index = (coll / "README.md").read_text()
    assert index.count("| fixture |") == 2


# tl: verifies tl-assess/TEST-0007@eaacde118d2e
def test_provenance_names_commit_pins_tools_and_plugin(repo):  # TEST-0007
    idd = graph_with_items(repo)
    toml = idd / "throughline.toml"
    toml.write_text(toml.read_text() + '\n[[sources]]\nnamespace = "wcag"\nurl = "https://github.com/rhodium-org/throughline-wcag"\nref = "v2.2.3"\n')
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "A graph (INT-0001)")
    p = assess("provenance", "-C", str(idd))
    assert p["repository_commit"] == git(repo, "rev-parse", "HEAD").stdout.strip()
    assert p["working_tree_clean"] is True
    assert p["sources"] == [{"namespace": "wcag", "url": "https://github.com/rhodium-org/throughline-wcag", "ref": "v2.2.3"}]
    record = assess("record", "-C", str(idd), "--name", "pins", "--out", str(repo / "out"))
    md = next((repo / "out").glob("*-pins.md")).read_text()
    assert "| Source pins | wcag v2.2.3 |" in md
    assert set(p["tools"]) == {"tl", "tl-ratify"}
    for tool in ("tl", "tl-ratify"):
        expected = subprocess.run([tool, "--version"], text=True, capture_output=True) if shutil.which(tool) else None
        assert p["tools"][tool] == ((expected.stdout or expected.stderr).strip().splitlines()[0] if expected else None)
    manifest = json.loads((Path(__file__).resolve().parents[1] / ".claude-plugin" / "plugin.json").read_text())
    assert p["plugin_version"] == manifest["version"] and len(p["plugin_commit"] or "") == 40
    assert p["script"].endswith("scripts/assess.py") and p["python"].count(".") == 2
    (idd / "scratch.txt").write_text("dirty\n")
    assert assess("provenance", "-C", str(idd))["working_tree_clean"] is False


# tl: verifies tl-assess/TEST-0008@ccb7a46d4a49
def test_git_measure_scoped_to_paths(repo):  # TEST-0008
    idd = graph_with_items(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "A graph (INT-0001)")
    git(repo, "tag", "v0.1.0")
    (repo / "other").mkdir()
    (repo / "other" / "thing.txt").write_text("elsewhere\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "Other work, no item named")
    git(repo, "tag", "other-1")
    (repo / "scripts").mkdir()
    (repo / "scripts" / "tool.py").write_text("print(1)\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "The tool (REQ-0001)")
    scoped = assess("git", "-C", str(idd), "--paths", "idd", "scripts")
    assert scoped["scope"] == ["idd", "scripts"]
    assert scoped["commits"] == 2 and scoped["commits_citing_an_item"] == 2 and scoped["citing_ratio"] == 1.0
    assert [t["tag"] for t in scoped["tags"]] == ["v0.1.0"] and scoped["editions"] == 1
    assert scoped["lines_added"] == sum(1 for _ in open(repo / "scripts" / "tool.py")) + sum(
        len(p.read_text().splitlines()) for p in idd.rglob("*") if p.is_file())
    whole = assess("git", "-C", str(idd))
    assert whole["scope"] == "repository" and whole["commits"] == 3 and whole["editions"] == 2


def strings_in(value):
    """Every string in a JSON value, however deep."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from strings_in(v)
    elif isinstance(value, list):
        for v in value:
            yield from strings_in(v)


# tl: verifies tl-assess/TEST-0011@23b00d29b823
def test_record_holds_no_absolute_path(repo, tmp_path):  # TEST-0011
    idd = graph_with_items(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "A graph (INT-0001)")
    git(repo, "remote", "add", "origin", "https://ada:s3cret@example.org/org/work.git")
    inside, above = tmp_path / "inside.jsonl", tmp_path / "above.jsonl"
    transcript(inside, cwd=str(repo))
    transcript(above, cwd=str(tmp_path))
    rec = assess("record", "-C", str(idd), "--name", "portable", "--sessions", str(inside), str(above))
    assert rec["graph_root"] == "idd"
    assert rec["repository"] == "https://example.org/org/work"
    assert [s["file"] for s in rec["sessions"]["sessions"]] == ["inside.jsonl", "above.jsonl"]
    assert [s["cwd"] for s in rec["sessions"]["sessions"]] == [".", ".."]
    assert rec["provenance"]["script"] == "scripts/assess.py"
    written = json.loads(Path(rec["written"][0]).read_text())
    assert [s for s in strings_in(written) if os.path.isabs(s)] == []
    md = Path(rec["written"][1]).read_text()
    assert "from `idd` in https://example.org/org/work." in md and str(repo.resolve()) not in md
    # A session that sat elsewhere is not placed: placing it would name the machine's layout.
    elsewhere = tmp_path / "elsewhere.jsonl"
    transcript(elsewhere, cwd=str(tmp_path / "other" / "work"))
    rec = assess("record", "-C", str(idd), "--name", "portable", "--sessions", str(elsewhere))
    assert rec["sessions"]["sessions"][0]["cwd"] is None
    # A graph outside the repository has no repository-relative name, so the record is refused.
    outside = tmp_path / "outside" / "idd"
    outside.mkdir(parents=True)
    run("tl", "init", "--no-demo", cwd=outside)
    r = run(sys.executable, str(SCRIPT), "record", "-C", str(outside), "--name", "x", "--repo", str(repo), check=False)
    assert r.returncode == 1 and "not inside the repository" in r.stderr


# tl: verifies tl-assess/TEST-0012@978d95d456d5
def test_migrate_rewrites_an_earlier_record(repo, tmp_path):  # TEST-0012
    idd = graph_with_items(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "A graph (INT-0001)")
    t = tmp_path / "s1.jsonl"
    transcript(t, cwd=str(tmp_path))
    rec = assess("record", "-C", str(idd), "--name", "earlier", "--sessions", str(t))
    jp, mp = Path(rec["written"][0]), Path(rec["written"][1])
    today_json, today_md = jp.read_text(), mp.read_text()
    head_today = today_md[:today_md.index("\n## What was built\n")]
    # Age both files to the form written before the rule: the machine's own paths, and a narrative a person wrote.
    base = str(repo.resolve())
    aged = json.loads(today_json)
    aged["graph_root"], aged["repository"] = base + "/idd", base
    aged["sessions"]["sessions"][0]["file"], aged["sessions"]["sessions"][0]["cwd"] = str(t), str(tmp_path.resolve())
    aged["provenance"]["script"] = str(SCRIPT)
    jp.write_text(json.dumps(aged, indent=2) + "\n")
    narrative = today_md[len(head_today):].replace(
        "(One paragraph: the input, the output, and what a person can now use.)", "A fixture graph, built in a test.")
    mp.write_text(head_today.replace("from `idd` in work.", f"from `{base}/idd`.") + narrative)
    assert base in jp.read_text() and base in mp.read_text()
    assert assess("migrate", str(jp)) == {"migrated": [str(jp)], "unchanged": []}
    assert jp.read_text() == today_json
    assert mp.read_text() == head_today + narrative
    # Migrating again changes nothing: a record already in the current form is left alone.
    assert assess("migrate", str(jp)) == {"migrated": [], "unchanged": [str(jp)]}
    assert jp.read_text() == today_json and mp.read_text() == head_today + narrative
    # A record from before the repository was named finds it from the graph root, as record does.
    del aged["repository"]
    jp.write_text(json.dumps(aged, indent=2) + "\n")
    assert assess("migrate", str(jp))["migrated"] == [str(jp)]
    assert jp.read_text() == today_json
