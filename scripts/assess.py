#!/usr/bin/env python3
"""Objective measures of a piece of work done on a throughline graph.

Reads the graph as the JSON that `tl dump` emits,
the repository's git history, the generated documents, a test result file and
the Claude Code session transcripts, and reports numbers a person did not
choose: item counts by type, status and origin; who ratified; sources composed
and links into them; commits, authors, tags and the span of days; items amended
after ratification; words of generated documents; tests; wall-clock and active
time per session; tokens in and out; tool calls. `done` says whether the work
meets the done criteria. `record` writes the whole assessment as JSON and as a
Markdown skeleton whose narrative sections a person fills in.

Standard library only. Every measuring command exits 0; `done` exits 1 when a
criterion fails, so it can gate. A command that runs `tl` needs throughline
3.11.0 or later, which composes the graph's sources, and exits 2 on an older one.

Usage:
  assess.py graph    -C ROOT [--dump FILE]
  assess.py git      -C ROOT [--repo DIR] [--paths PATH...]
  assess.py docs     -C ROOT
  assess.py tests    --glob PATTERN [--results FILE] [--repo DIR]
  assess.py sessions FILE... [--idle-gap MINUTES] [--since ISO] [--until ISO]
  assess.py done     -C ROOT [--repo DIR] [--results FILE]
  assess.py provenance -C ROOT [--repo DIR]
  assess.py record   -C ROOT --name NAME [--repo DIR] [--sessions FILE...]
                     [--tests-glob PATTERN] [--results FILE] [--out DIR]
                     [--collection DIR] [--label TEXT] [--paths PATH...]
  assess.py migrate  FILE.json... [--repo DIR]

A record holds no absolute path: the graph root is named relative to the
repository, the repository by its origin, a transcript by its file name, a
session's working directory relative to the repository and the script relative
to the plugin. `migrate` brings a record written before that rule to the same
form in place, its numbers untouched.
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import glob
import json
import os
import re
import shutil
import platform
import subprocess
import sys
import tomllib
from collections import Counter, defaultdict
from pathlib import Path

from tl_cli import require_tl

UID_RE = re.compile(r"(?<![\w:])(?:([A-Za-z][\w-]*):)?([A-Z][A-Z0-9]*-\d{3,})\b")
ITEM_FILE_RE = re.compile(r"(^|/)[A-Z][A-Z0-9]*-\d{3,}\.ya?ml$")
LIVE_STATUSES = {"proposed", "draft", "ratified", "implemented", "deferred", "verified"}


# ── helpers ────────────────────────────────────────────────────────────────

def run(cmd: list[str], cwd: str | None = None, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=check)


# tl: implements tl-assess/REQ-0001@45cc4507dcfd, tl-assess/REQ-0009@2a17db5c5743
def load_dump(root: str | None, dump: str | None) -> dict:
    if dump:
        with open(dump) as fh:
            return json.load(fh)
    if not root:
        raise SystemExit("give -C ROOT or --dump FILE")
    out = run([require_tl(), "-C", root, "dump"], check=True)
    return json.loads(out.stdout)


def items_of(dumped: dict) -> list[dict]:
    items = dumped.get("items", dumped)
    return list(items.values()) if isinstance(items, dict) else list(items)


def is_local(uid: str) -> bool:
    return ":" not in uid


def repo_of(root: str | None, repo: str | None) -> str:
    if repo:
        return os.path.realpath(repo)
    out = run(["git", "-C", root or ".", "rev-parse", "--show-toplevel"])
    if out.returncode != 0:
        raise SystemExit(f"not a git repository: {root}")
    return out.stdout.strip()


# ── portability ─────────────────────────────────────────────────────────────
# A record is committed to a repository that may be public and copied into a
# collection read on other machines, so it names nothing by where one machine
# kept it. The measuring commands print what they measured; the record is made
# portable once, just before it is written, and migrate does the same to a
# record written before this rule.

# tl: implements tl-assess/REQ-0010@22d2f73d74d9
def relative_to_repo(path: str, repo: str) -> str:
    """PATH relative to the repository root, as a POSIX path. A path outside
    the repository has no such name and is refused."""
    rel = os.path.relpath(os.path.realpath(path), os.path.realpath(repo))
    if rel == os.pardir or rel.startswith(os.pardir + os.sep):
        raise SystemExit(f"{path} is not inside the repository {repo}; "
                         "a record names the graph root relative to the repository")
    return rel.replace(os.sep, "/")


# tl: implements tl-assess/REQ-0010@22d2f73d74d9
def session_cwd(cwd: str | None, repo: str) -> str | None:
    """A session's working directory relative to the repository: '.' or a
    subdirectory when it sat inside, a run of '..' when it sat above, None when
    it sat elsewhere, since naming that would name the machine's layout."""
    if not cwd:
        return None
    rel = os.path.relpath(os.path.realpath(cwd), os.path.realpath(repo))
    parts = rel.split(os.sep)
    if os.pardir in parts and any(part != os.pardir for part in parts):
        return None
    return rel.replace(os.sep, "/")


# tl: implements tl-assess/REQ-0010@22d2f73d74d9
def repository_identity(repo: str) -> str:
    """The origin URL with any credentials and a trailing .git removed, or the
    directory's name when the repository has no origin."""
    if not os.path.isdir(repo):
        raise SystemExit(f"the repository {repo} is not on this machine; give --repo")
    out = run(["git", "-C", repo, "remote", "get-url", "origin"])
    url = out.stdout.strip() if out.returncode == 0 else ""
    if not url:
        return Path(repo).name
    url = re.sub(r"://[^/@]+@", "://", url)
    return url[:-4] if url.endswith(".git") else url


# tl: implements tl-assess/REQ-0010@22d2f73d74d9
def portable(rec: dict, repo: str | None = None) -> dict:
    """The record with every path made relative: the graph root and each
    session's working directory to the repository the record names, each
    transcript to its file name, the script to the plugin root above its own
    directory; and the repository named by its identity, read from REPO or
    from the directory the record names. A record already portable is
    returned as it is. A record from before the repository was named, or that
    named it as a dot, finds it from the graph root, as record does."""
    if not os.path.isabs(rec["graph_root"]):
        return rec
    base = rec.get("repository") or ""
    if not os.path.isabs(base):
        base = repo_of(rec["graph_root"], repo)
    out: dict = {}
    for key, value in rec.items():
        if key == "repository":
            continue  # written beside the graph root, whichever form the record had
        out[key] = value
        if key == "graph_root":
            out["graph_root"] = relative_to_repo(value, base)
            out["repository"] = repository_identity(repo or base)
    for s in out["sessions"]["sessions"]:
        s["file"] = os.path.basename(s["file"])
        s["cwd"] = session_cwd(s.get("cwd"), base)
    script = Path(out["provenance"]["script"])
    out["provenance"]["script"] = script.relative_to(script.parent.parent).as_posix()
    return out


# ── graph ───────────────────────────────────────────────────────────────────

# tl: implements tl-assess/REQ-0001@45cc4507dcfd
def measure_graph(dumped: dict) -> dict:
    items = items_of(dumped)
    local = [i for i in items if is_local(str(i.get("uid", "")))]
    borrowed = [i for i in items if not is_local(str(i.get("uid", "")))]
    by_type = Counter(i.get("type", "?") for i in local)
    by_status = Counter(i.get("status", "?") for i in local)
    by_origin = Counter((i.get("attrs") or {}).get("origin", "unset") for i in local)
    ratifiers = Counter((i.get("attrs") or {}).get("ratified_by") for i in local
                        if (i.get("attrs") or {}).get("ratified_by"))
    test_methods = Counter((i.get("attrs") or {}).get("method", "unset") for i in local if i.get("type") == "test")
    normative = sum(1 for i in local if i.get("normative"))
    sources: dict[str, int] = Counter(str(i["uid"]).split(":", 1)[0] for i in borrowed)
    citations = Counter()
    stamped = 0
    unstamped = 0
    local_links = 0
    for i in local:
        for link in i.get("links") or []:
            target = str(link.get("target", ""))
            if is_local(target):
                local_links += 1
                continue
            citations[target.split(":", 1)[0]] += 1
            if link.get("stamp"):
                stamped += 1
            else:
                unstamped += 1
    live = [i for i in local if i.get("status") in LIVE_STATUSES]
    accepted = sum(1 for i in live if i.get("status") in ("ratified", "implemented", "verified"))
    return {
        "items_local": len(local),
        "items_live": len(live),
        "items_accepted": accepted,
        "acceptance_ratio": round(accepted / len(live), 3) if live else None,
        "by_type": dict(by_type),
        "by_status": dict(by_status),
        "by_origin": dict(by_origin),
        "ratified_by": dict(ratifiers),
        "normative": normative,
        "tests_by_method": dict(test_methods),
        "sources_composed": dict(sources),
        "citations_by_source": dict(citations),
        "citations": sum(citations.values()),
        "citations_stamped": stamped,
        "citations_unstamped": unstamped,
        "local_links": local_links,
    }


# ── git ─────────────────────────────────────────────────────────────────────

# tl: implements tl-assess/REQ-0002@8886c117c6c0, tl-assess/REQ-0008@017bcd6c17c0
def measure_git(repo: str, items_dir: str | None, paths: list[str] | None = None) -> dict:
    scope = ["--", *paths] if paths else []
    log = run(["git", "-C", repo, "log", "--format=%H%x1f%aI%x1f%an%x1f%s", "--reverse", *scope], check=True).stdout
    commits = [line.split("\x1f") for line in log.splitlines() if line]
    if not commits:
        return {"commits": 0, "scope": paths or "repository"}
    first, last = commits[0][1], commits[-1][1]
    span = (dt.datetime.fromisoformat(last) - dt.datetime.fromisoformat(first))
    authors = Counter(c[2] for c in commits)
    citing = sum(1 for c in commits if UID_RE.search(c[3]))
    # A lightweight tag has no creator date of its own; the commit's date serves both kinds.
    tag_names = run(["git", "-C", repo, "tag", "--sort=creatordate"]).stdout.split()
    in_scope = {c[0] for c in commits}
    tags = []
    for t in tag_names:
        commit = run(["git", "-C", repo, "rev-list", "-n", "1", t]).stdout.strip()
        if not paths or commit in in_scope:
            tags.append({"tag": t, "date": run(["git", "-C", repo, "log", "-1", "--format=%aI", t]).stdout.strip()})
    numstat = run(["git", "-C", repo, "log", "--numstat", "--format=", *scope], check=True).stdout
    added = removed = 0
    for line in numstat.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            added += int(parts[0])
            removed += int(parts[1])
    amended: dict = {"items_ratified": 0, "items_amended_after_ratification": 0, "amending_commits": 0}
    if items_dir:
        files = [f for f in run(["git", "-C", repo, "ls-files", items_dir]).stdout.splitlines() if ITEM_FILE_RE.search(f)]
        for f in files:
            # The item's history at whatever path it had, oldest first: a rename
            # must hide neither the ratification before it nor an amendment made in it.
            # (--follow stops at the rename when combined with --reverse, so reverse here.)
            log = run(["git", "-C", repo, "log", "--follow", "--format=%x1e%H", "--name-only", "--", f]).stdout
            states = []
            for block in log.split("\x1e"):
                lines = [l for l in block.splitlines() if l.strip()]
                if len(lines) >= 2:
                    states.append((lines[0], lines[-1]))
            states.reverse()
            contents = [run(["git", "-C", repo, "show", f"{c}:{path}"]).stdout for c, path in states]
            first_ratified = next((i for i, c in enumerate(contents) if "ratified_by" in c), None)
            if first_ratified is None:
                continue
            amended["items_ratified"] += 1
            # A later change counts as an amendment only if it touched a line other than the
            # ratification record and the status: a re-ratification alone is the human's act,
            # not a change to the item, and a move alone changes no line at all.
            amending = 0
            for i in range(first_ratified + 1, len(contents)):
                diff = difflib.unified_diff(contents[i - 1].splitlines(), contents[i].splitlines(), lineterm="", n=0)
                changed = [l for l in diff if (l.startswith("+") or l.startswith("-"))
                           and not l.startswith(("+++", "---"))
                           and not re.match(r"[+-]\s*(ratified_by|ratified_fingerprint|ratified_id|status):", l)]
                if changed:
                    amending += 1
            if amending:
                amended["items_amended_after_ratification"] += 1
                amended["amending_commits"] += amending
    return {
        "scope": paths or "repository",
        "commits": len(commits),
        "first_commit": first,
        "last_commit": last,
        "span_days": round(span.total_seconds() / 86400, 2),
        "authors": dict(authors),
        "commits_citing_an_item": citing,
        "citing_ratio": round(citing / len(commits), 3),
        "tags": tags,
        "editions": len(tags),
        "lines_added": added,
        "lines_removed": removed,
        **amended,
    }


# ── docs ────────────────────────────────────────────────────────────────────

# tl: implements tl-assess/REQ-0003@a052f99c8c73
def measure_docs(root: str) -> dict:
    docs_dir = Path(root) / "docs"
    words: dict[str, int] = {}
    for p in sorted(docs_dir.glob("*.md")) if docs_dir.is_dir() else []:
        words[p.name] = len(p.read_text(errors="replace").split())
    check = run([require_tl(), "-C", root, "docs", "--check"])
    return {
        "documents": words,
        "words": sum(words.values()),
        "docs_check_ok": check.returncode == 0,
        "docs_check": (check.stdout + check.stderr).strip().splitlines()[-1:] ,
    }


# ── tests ───────────────────────────────────────────────────────────────────

# tl: implements tl-assess/REQ-0003@a052f99c8c73
def parse_results(path: str | None) -> dict:
    """A test result file: TAP-style '# pass N' / '# fail N' lines, or JSON {passed, failed}."""
    if not path:
        return {}
    text = Path(path).read_text(errors="replace")
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return {"passed": data.get("passed", data.get("pass")), "failed": data.get("failed", data.get("fail"))}
    except json.JSONDecodeError:
        pass
    m_pass = re.search(r"^#\s*pass\s+(\d+)", text, re.M)
    m_fail = re.search(r"^#\s*fail\s+(\d+)", text, re.M)
    return {"passed": int(m_pass.group(1)) if m_pass else None, "failed": int(m_fail.group(1)) if m_fail else None}


# tl: implements tl-assess/REQ-0003@a052f99c8c73
def measure_tests(pattern: str | None, results: str | None, repo: str | None) -> dict:
    files = sorted(glob.glob(os.path.join(repo or ".", pattern), recursive=True)) if pattern else []
    out = {"test_files": len(files), "pattern": pattern}
    out.update(parse_results(results))
    return out


# ── sessions ────────────────────────────────────────────────────────────────

def parse_ts(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


# tl: implements tl-assess/REQ-0004@87bbcfd68939
def measure_session(path: str, idle_gap_min: float, since: dt.datetime | None = None, until: dt.datetime | None = None) -> dict:
    first = last = prev = None
    active = dt.timedelta()
    gap = dt.timedelta(minutes=idle_gap_min)
    user_turns = assistant_turns = tool_results = compactions = api_calls = 0
    tools: Counter = Counter()
    models: Counter = Counter()
    usage = Counter()
    session_id = None
    cwd = None
    with open(path, errors="replace") as fh:
        for line in fh:
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            session_id = session_id or o.get("sessionId")
            cwd = cwd or o.get("cwd")
            ts = o.get("timestamp")
            if ts:
                t = parse_ts(ts)
                if (since and t < since) or (until and t > until):
                    continue
                first = first or t
                if prev is not None and t > prev:
                    d = t - prev
                    if d <= gap:
                        active += d
                prev = t if prev is None or t > prev else prev
                last = t if last is None or t > last else last
            kind = o.get("type")
            msg = o.get("message") if isinstance(o.get("message"), dict) else None
            if o.get("isCompactSummary"):
                compactions += 1
            if kind == "user":
                content = (msg or {}).get("content")
                if o.get("toolUseResult") is not None or (isinstance(content, list) and any(
                        isinstance(b, dict) and b.get("type") == "tool_result" for b in content)):
                    tool_results += 1
                elif not o.get("isMeta"):
                    user_turns += 1
            elif kind == "assistant" and msg:
                assistant_turns += 1
                if msg.get("model") and msg["model"] != "<synthetic>":
                    models[msg["model"]] += 1
                u = msg.get("usage")
                if isinstance(u, dict):
                    api_calls += 1
                    for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
                        usage[k] += int(u.get(k) or 0)
                    usage["thinking_tokens"] += int(((u.get("output_tokens_details") or {}).get("thinking_tokens")) or 0)
                for b in msg.get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        tools[b.get("name", "?")] += 1
    wall = (last - first) if first and last else dt.timedelta()
    return {
        "file": path,
        "session_id": session_id,
        "cwd": cwd,
        "first": first.isoformat() if first else None,
        "last": last.isoformat() if last else None,
        "wall_clock_hours": round(wall.total_seconds() / 3600, 2),
        "active_hours": round(active.total_seconds() / 3600, 2),
        "idle_gap_minutes": idle_gap_min,
        "since": since.isoformat() if since else None,
        "until": until.isoformat() if until else None,
        "user_turns": user_turns,
        "assistant_turns": assistant_turns,
        "tool_results": tool_results,
        "tool_calls": sum(tools.values()),
        "tool_calls_by_name": dict(tools.most_common()),
        "api_calls": api_calls,
        "models": dict(models),
        "compactions": compactions,
        "tokens": dict(usage),
    }


# tl: implements tl-assess/REQ-0004@87bbcfd68939
def measure_sessions(paths: list[str], idle_gap_min: float, since: str | None = None, until: str | None = None) -> dict:
    s = parse_ts(since) if since else None
    u = parse_ts(until) if until else None
    sessions = [measure_session(p, idle_gap_min, s, u) for p in paths]
    totals: Counter = Counter()
    tools: Counter = Counter()
    for s in sessions:
        for k in ("wall_clock_hours", "active_hours", "user_turns", "assistant_turns", "tool_calls", "api_calls", "compactions"):
            totals[k] += s[k]
        for k, v in s["tokens"].items():
            totals["tokens_" + k] += v
        tools.update(s["tool_calls_by_name"])
    return {"sessions": sessions, "count": len(sessions), "totals": {k: round(v, 2) for k, v in totals.items()},
            "tool_calls_by_name": dict(tools.most_common())}


# ── provenance ──────────────────────────────────────────────────────────────

# tl: implements tl-assess/REQ-0007@66eebc854fe7
def tool_version(name: str) -> str | None:
    """What `<tool> --version` prints, or None when the tool is not on the path."""
    if not shutil.which(name):
        return None
    out = run([name, "--version"])
    return (out.stdout or out.stderr).strip().splitlines()[0] if (out.stdout or out.stderr).strip() else "unknown"


def plugin_root() -> Path:
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    return Path(env) if env else Path(__file__).resolve().parent.parent


# tl: implements tl-assess/REQ-0007@66eebc854fe7
def measure_provenance(root: str, repo: str) -> dict:
    head = run(["git", "-C", repo, "rev-parse", "HEAD"]).stdout.strip() or None
    clean = run(["git", "-C", repo, "status", "--porcelain"]).stdout.strip() == ""
    sources = []
    toml = Path(root) / "throughline.toml"
    if toml.exists():
        try:
            cfg = tomllib.loads(toml.read_text())
        except tomllib.TOMLDecodeError:
            cfg = {}
        for s in cfg.get("sources", []) or []:
            # A source is declared under `namespace`; `name` is read for a graph written before that key.
            sources.append({k: s.get(k) for k in ("namespace", "name", "url", "path", "ref") if s.get(k) is not None})
    plugin = plugin_root()
    manifest = plugin / ".claude-plugin" / "plugin.json"
    plugin_version = None
    if manifest.exists():
        try:
            plugin_version = json.loads(manifest.read_text()).get("version")
        except json.JSONDecodeError:
            plugin_version = None
    plugin_commit = run(["git", "-C", str(plugin), "rev-parse", "HEAD"]).stdout.strip() or None
    return {
        "repository_commit": head,
        "working_tree_clean": clean,
        "sources": sources,
        "tools": {name: tool_version(name) for name in ("tl", "tl-ratify")},
        "plugin_version": plugin_version,
        "plugin_commit": plugin_commit,
        "script": str(Path(__file__).resolve()),
        "python": platform.python_version(),
    }


# ── done ────────────────────────────────────────────────────────────────────

# tl: implements tl-assess/REQ-0005@6bda53c41f10
def measure_done(root: str, repo: str, results: str | None) -> dict:
    check = run([require_tl(), "-C", root, "check", "--strict"])
    m = re.search(r"(\d+) error\(s\), (\d+) warning\(s\)", check.stdout + check.stderr)
    errors = int(m.group(1)) if m else (0 if check.returncode == 0 else -1)
    docs = run([require_tl(), "-C", root, "docs", "--check"])
    dumped = load_dump(root, None)
    proposed = sum(1 for i in items_of(dumped) if is_local(str(i.get("uid", ""))) and i.get("status") in ("proposed", "draft"))
    clean = run(["git", "-C", repo, "status", "--porcelain"]).stdout.strip() == ""
    res = parse_results(results)
    criteria = {
        "strict_check_clean": errors == 0,
        "docs_current": docs.returncode == 0,
        "nothing_awaiting_ratification": proposed == 0,
        "working_tree_clean": clean,
    }
    if res.get("failed") is not None:
        criteria["tests_green"] = res["failed"] == 0
    return {"criteria": criteria, "done": all(criteria.values()), "strict_errors": errors, "proposed": proposed, **res}


# ── record ──────────────────────────────────────────────────────────────────

# tl: implements tl-assess/REQ-0006@de9d5e7acb9e
def record(args) -> dict:
    root = args.path
    repo = repo_of(root, args.repo)
    dumped = load_dump(root, None)
    rec = {
        "name": args.name,
        "label": args.label,
        "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "graph_root": os.path.realpath(root),
        "repository": repo,
        "graph": measure_graph(dumped),
        "git": measure_git(repo, relative_to_repo(root, repo), args.paths),
        "docs": measure_docs(root),
        "tests": measure_tests(args.tests_glob, args.results, repo),
        "sessions": measure_sessions(args.sessions or [], args.idle_gap, args.since, args.until),
        "done": measure_done(root, repo, args.results),
        "provenance": measure_provenance(root, repo),
    }
    rec = portable(rec)
    out_dir = Path(args.out or os.path.join(repo, "docs", "assessment"))
    out_dir.mkdir(parents=True, exist_ok=True)
    # Date and time in the name: a second record on the same day never overwrites the first.
    stem = f"{rec['recorded_at'][:19].replace(':', '')}-{args.name}"
    # Never overwrite: a record taken in the same second as another gets a suffix.
    base, n = stem, 1
    while (out_dir / f"{stem}.json").exists() or (args.collection and (Path(args.collection) / args.name / f"{stem}.json").exists()):
        n += 1
        stem = f"{base}-{n}"
    (out_dir / f"{stem}.json").write_text(json.dumps(rec, indent=2) + "\n")
    (out_dir / f"{stem}.md").write_text(markdown(rec))
    written = [str(out_dir / f"{stem}.json"), str(out_dir / f"{stem}.md")]
    if args.collection:
        coll = Path(args.collection) / args.name
        coll.mkdir(parents=True, exist_ok=True)
        for w in written:
            shutil.copy(w, coll / Path(w).name)
        written.append(str(coll))
        write_index(Path(args.collection))
    rec["written"] = written
    return rec


def hours(x: float) -> str:
    return f"{x:.1f} h"


NARRATIVE_START = "## What was built"


# tl: implements tl-assess/REQ-0006@de9d5e7acb9e
def measured_head(rec: dict) -> list[str]:
    """The Markdown's measured part: the title, the label, where the record was
    taken from, and the numbers as one table. Everything below is narrative."""
    g, git, d, t, s, done = rec["graph"], rec["git"], rec["docs"], rec["tests"], rec["sessions"], rec["done"]
    prov = rec.get("provenance", {})
    tot = s["totals"]
    rows = [
        ("Items in the graph (local, live)", f"{g['items_live']} of {g['items_local']}"),
        ("Accepted (ratified, implemented or verified)", f"{g['items_accepted']} ({g['acceptance_ratio']})"),
        ("Origin", ", ".join(f"{k} {v}" for k, v in g["by_origin"].items())),
        ("Ratified by", ", ".join(f"{k} {v}" for k, v in g["ratified_by"].items()) or "nobody yet"),
        ("Sources composed", ", ".join(f"{k} ({v} items)" for k, v in g["sources_composed"].items()) or "none"),
        ("Links into sources", f"{g['citations']} ({g['citations_stamped']} stamped, {g['citations_unstamped']} not)"),
        ("Tests by method", ", ".join(f"{k} {v}" for k, v in g["tests_by_method"].items()) or "none"),
        # A record from before the measure could be scoped was measured repository-wide and carries no scope.
        ("Git scope", "whole repository" if git.get("scope", "repository") == "repository" else ", ".join(git["scope"])),
        ("Commits", f"{git.get('commits', 0)} over {git.get('span_days', 0)} days, {git.get('editions', 0)} tags"),
        ("Commits naming an item", f"{git.get('commits_citing_an_item', 0)} ({git.get('citing_ratio', 0)})"),
        ("Items amended after ratification", f"{git.get('items_amended_after_ratification', 0)} of {git.get('items_ratified', 0)}"),
        ("Lines added / removed", f"{git.get('lines_added', 0)} / {git.get('lines_removed', 0)}"),
        ("Generated documents", f"{len(d['documents'])} files, {d['words']} words, {'current' if d['docs_check_ok'] else 'STALE'}"),
        ("Test files", f"{t.get('test_files', 0)}" + (f", {t.get('passed')} pass, {t.get('failed')} fail" if t.get("passed") is not None else "")),
        ("Sessions", f"{s['count']}"),
        ("Wall clock / active", f"{hours(tot.get('wall_clock_hours', 0))} / {hours(tot.get('active_hours', 0))}"),
        ("Human turns / AI turns", f"{int(tot.get('user_turns', 0))} / {int(tot.get('assistant_turns', 0))}"),
        ("Tool calls / API calls", f"{int(tot.get('tool_calls', 0))} / {int(tot.get('api_calls', 0))}"),
        ("Tokens out", f"{int(tot.get('tokens_output_tokens', 0)):,} (thinking {int(tot.get('tokens_thinking_tokens', 0)):,})"),
        ("Tokens in (fresh / cache written / cache read)",
         f"{int(tot.get('tokens_input_tokens', 0)):,} / {int(tot.get('tokens_cache_creation_input_tokens', 0)):,} / {int(tot.get('tokens_cache_read_input_tokens', 0)):,}"),
        ("Done", "yes" if done["done"] else "NO: " + ", ".join(k for k, v in done["criteria"].items() if not v)),
        ("Measured at commit", f"{(prov.get('repository_commit') or '')[:12]}{'' if prov.get('working_tree_clean', True) else ' (tree not clean)'}"),
        ("Source pins", "; ".join(f"{x.get('namespace') or x.get('name')} {x.get('ref') or x.get('path') or ''}".strip() for x in prov.get("sources", [])) or "none"),
        ("Tools", "; ".join(f"{k}: {v or 'absent'}" for k, v in (prov.get("tools") or {}).items())),
        ("Skill", f"tl:assess {prov.get('plugin_version') or '?'} at {(prov.get('plugin_commit') or '')[:12]}, Python {prov.get('python')}"),
    ]
    table = "| Measure | Value |\n|---|---|\n" + "\n".join(f"| {k} | {v} |" for k, v in rows)
    return [
        f"# Assessment: {rec['name']}",
        "",
        f"{rec['label'] or ''}".strip(),
        "",
        f"Recorded {rec['recorded_at']} from `{rec['graph_root']}` in {rec['repository']}.",
        "",
        "## Measured",
        "",
        table,
        "",
    ]


NARRATIVE_SKELETON = [
    NARRATIVE_START,
    "",
    "(One paragraph: the input, the output, and what a person can now use.)",
    "",
    "## Defects found after the first \"done\"",
    "",
    "| Defect | Found by | Would a gate have caught it? | Which |",
    "|---|---|---|---|",
    "| | | | |",
    "",
    "## What the graph caught before a person did",
    "",
    "(Findings from `tl check`, the challenger, stamps and document gates that stopped a defect.)",
    "",
    "## Human effort",
    "",
    "(Turns, ratifications, decisions and corrections. What only the human could do.)",
    "",
    "## Verdict",
    "",
    "(Did the graph earn its keep here? Benefits and costs in the measured terms above, then a judgement.)",
    "",
]


# tl: implements tl-assess/REQ-0006@de9d5e7acb9e
def markdown(rec: dict) -> str:
    return "\n".join(measured_head(rec) + NARRATIVE_SKELETON)


# tl: implements tl-assess/REQ-0010@22d2f73d74d9
def migrate(files: list[str], repo: str | None) -> dict:
    """Bring records written before the portability rule to the current form,
    in place: the JSON through portable, its numbers untouched; the Markdown's
    measured head re-rendered from it above the narrative, which is kept as
    written. A record already in the current form is left alone."""
    migrated, unchanged = [], []
    for f in files:
        p = Path(f)
        rec = json.loads(p.read_text())
        if not os.path.isabs(rec["graph_root"]):
            unchanged.append(str(p))
            continue
        rec = portable(rec, repo)
        md = p.with_suffix(".md")
        narrative = None
        if md.exists():
            text = md.read_text()
            at = text.find("\n" + NARRATIVE_START + "\n")
            if at < 0:
                raise SystemExit(f"{md}: no '{NARRATIVE_START}' heading, so the measured head "
                                 "cannot be told from the narrative")
            narrative = text[at:]
        p.write_text(json.dumps(rec, indent=2) + "\n")
        if narrative is not None:
            md.write_text("\n".join(measured_head(rec)) + narrative)
        migrated.append(str(p))
    return {"migrated": migrated, "unchanged": unchanged}


# tl: implements tl-assess/REQ-0006@de9d5e7acb9e
def write_index(collection: Path) -> None:
    rows = []
    for p in sorted(collection.glob("*/*.json")):
        try:
            r = json.loads(p.read_text())
        except json.JSONDecodeError:
            continue
        tot = r["sessions"]["totals"]
        rows.append((r["recorded_at"][:10], r["name"], r["graph"]["items_live"], r["graph"]["acceptance_ratio"],
                     r["git"].get("editions", 0), hours(tot.get("active_hours", 0)),
                     f"{int(tot.get('tokens_output_tokens', 0)):,}", "yes" if r["done"]["done"] else "no",
                     p.with_suffix(".md").relative_to(collection)))
    head = ("# Throughline assessments\n\nOne folder per piece of work, each with the measured record (`.json`) and the "
            "written assessment (`.md`). Produced by the `tl:assess` skill.\n\n"
            "| Recorded | Work | Live items | Accepted | Editions | Active time | Tokens out | Done | Assessment |\n|---|---|---|---|---|---|---|---|---|\n")
    body = "\n".join(f"| {a} | {b} | {c} | {d} | {e} | {f} | {g} | {h} | [{i}]({i}) |" for a, b, c, d, e, f, g, h, i in rows)
    (collection / "README.md").write_text(head + body + "\n")


# ── cli ─────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def root_args(p, dump=False):
        p.add_argument("-C", dest="path", help="graph root (the directory holding throughline.toml)")
        if dump:
            p.add_argument("--dump", help="a saved `tl dump` instead of running the tool")

    p = sub.add_parser("graph"); root_args(p, dump=True)
    p = sub.add_parser("git"); root_args(p); p.add_argument("--repo"); p.add_argument("--paths", nargs="*", help="repository-relative paths the work lives in; default the whole repository")
    p = sub.add_parser("docs"); root_args(p)
    p = sub.add_parser("tests"); p.add_argument("--glob", required=True); p.add_argument("--results"); p.add_argument("--repo")
    p = sub.add_parser("sessions"); p.add_argument("files", nargs="+"); p.add_argument("--idle-gap", type=float, default=10.0)
    p.add_argument("--since", help="count transcript entries from this instant (ISO 8601)"); p.add_argument("--until", help="count transcript entries up to this instant (ISO 8601)")
    p = sub.add_parser("done"); root_args(p); p.add_argument("--repo"); p.add_argument("--results")
    p = sub.add_parser("provenance"); root_args(p); p.add_argument("--repo")
    p = sub.add_parser("record"); root_args(p)
    p.add_argument("--name", required=True, help="a slug for the work, one word or hyphenated")
    p.add_argument("--label", help="one line saying what the work was")
    p.add_argument("--repo"); p.add_argument("--sessions", nargs="*"); p.add_argument("--idle-gap", type=float, default=10.0)
    p.add_argument("--since"); p.add_argument("--until")
    p.add_argument("--paths", nargs="*", help="repository-relative paths the work lives in, for the git measure")
    p.add_argument("--tests-glob"); p.add_argument("--results"); p.add_argument("--out"); p.add_argument("--collection")
    p = sub.add_parser("migrate"); p.add_argument("files", nargs="+", help="record .json files; the .md beside each gets its measured head re-rendered")
    p.add_argument("--repo", help="the repository the records describe, when it is no longer at the path they name")
    args = ap.parse_args(argv)

    if args.cmd == "graph":
        out = measure_graph(load_dump(args.path, args.dump))
    elif args.cmd == "git":
        repo = repo_of(args.path, args.repo)
        out = measure_git(repo, os.path.relpath(args.path, repo) if args.path else None, args.paths)
    elif args.cmd == "docs":
        out = measure_docs(args.path)
    elif args.cmd == "tests":
        out = measure_tests(args.glob, args.results, args.repo)
    elif args.cmd == "sessions":
        out = measure_sessions(args.files, args.idle_gap, args.since, args.until)
    elif args.cmd == "provenance":
        out = measure_provenance(args.path, repo_of(args.path, args.repo))
    elif args.cmd == "done":
        out = measure_done(args.path, repo_of(args.path, args.repo), args.results)
        print(json.dumps(out, indent=2))
        return 0 if out["done"] else 1
    elif args.cmd == "migrate":
        out = migrate(args.files, args.repo)
    else:
        out = record(args)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
