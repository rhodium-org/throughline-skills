---
name: assess
description: Record an objective assessment of a piece of work done on a throughline IDD graph when it reaches "done" — item counts and acceptance, sources and citations, commits and editions, items amended after ratification, generated documents, tests, session wall-clock and active time, tokens and tool calls — then write the narrative beside the numbers and file it in a collection of examples. Use when asked to "assess this", "record the assessment", "how much did this cost", "are we done", or when a throughline-managed piece of work (a specification, an implementation, a document set, a skill) is finished and its case should join the evidence for or against working this way.
user-invocable: true
---

# Assess a piece of throughline work

Every piece of work done on a graph is an experiment: did the graph earn its
keep, or did it add cost and let errors through? This skill records one such
case objectively enough that a pile of them can answer that question. The
numbers come from a script and from things a person did not choose after the
fact: the graph, the git history, the generated documents, the test results
and the session transcripts. The narrative is written beside the numbers and
never in place of them.

The unit of assessment is one piece of work with a graph root: a specification,
an implementation, a document set, a tool, a skill. A repository holding two
graphs is two assessments.

## First: is there a graph, and is the work done?

```sh
find . -name throughline.toml -not -path '*/.venv/*' -not -path '*/.git/*'
```

No graph, nothing to assess under this skill; say so and stop.

"Done" is a fixed point, not a feeling. The script's `done` command applies
these criteria and exits 1 if any fails:

- the strict check reports no error;
- the generated documents are current (`docs --check`);
- nothing is `proposed` or `draft`: every live item has been accepted by a human;
- the working tree is clean;
- where a test result file is given, no test failed.

Assess at "done", not before. If the work is not done, record what stands in
the way and stop; an assessment of half-done work measures the wrong thing.
If the work will never reach done (abandoned, superseded), assess it anyway
and say so in the label: an abandoned case is evidence too.

## Next: tools and the script

```sh
tl --version || pip install 'throughline>=3.11.0'
S="${CLAUDE_PLUGIN_ROOT}/scripts/assess.py"
python3 "$S" --help
```

The script needs nothing beyond the Python standard library. A command that
runs `tl` needs throughline ≥ 3.11.0, the release from which `tl` composes a
graph's sources, and exits 2 on an older `tl` rather than measure half a graph.
If the plugin root variable is unset, the script sits at `scripts/assess.py`
beside this file's plugin.

## Gather the inputs

1. **Graph root.** The directory holding `throughline.toml`.
2. **Repository, and the paths the work lives in.** The repository is found
   from the graph root; pass `--repo` if the graph is not in the repository it
   describes. When the repository holds more than this piece of work (a plugin
   with one graph per skill, a repository with several graphs), pass `--paths`
   with the repository-relative directories and files that are this work, so
   the git measure counts only the commits that touched them. The scope is
   recorded; without it the whole repository is measured.
3. **Session transcripts.** Claude Code writes one `.jsonl` per session under
   `~/.claude/projects/<slugified working directory>/`. Find the sessions that
   did this work: grep the transcripts for the project's name and keep the
   ones where it is the main subject, not a mention.

   ```sh
   for f in ~/.claude/projects/*/*.jsonl; do printf "%6d %s\n" "$(grep -c -i '<project name>' "$f")" "$f"; done | sort -rn | head
   ```

   A session whose working directory is a parent of many projects may have
   done other work too; include it if the project dominates, and say so in the
   narrative. The `--idle-gap` (default 10 minutes) separates active time from
   wall-clock time: a gap longer than that between two transcript entries is
   counted as idle. Do not tune it to make a number look better.
4. **Test results.** A file with the suite's summary: TAP-style `# pass N` and
   `# fail N` lines (Node's test runner, pytest's tap plugin), or JSON with
   `passed` and `failed`. Capture it from the real run, do not type it.
5. **A name and a label.** The name is a slug that stays the same across
   re-assessments of the same work (`crookham-specification`); the label is
   one line saying what the work was.

## Record

```sh
python3 "$S" record -C <graph root> --name <slug> --label "<one line>" \
  --sessions <transcript.jsonl ...> \
  --tests-glob 'tests/TEST-*.test.ts' --results <summary file> \
  --paths <dirs and files that are this work, when the repository holds more> \
  --collection <path to the assessments repository>
```

This writes `docs/assessment/<date>T<time>-<name>.json` (the measured record,
never edited by hand) and `docs/assessment/<date>T<time>-<name>.md` (the numbers as a table
followed by the narrative sections to fill in) under the repository, copies
both into `<collection>/<name>/`, and regenerates the collection's `README.md`
index. Commit the two files in the work's repository citing the item that
grounds the assessment; commit the copies in the collection.

Each measuring command can also be run alone (`graph`, `git`, `docs`, `tests`,
`sessions`, `done`) and prints JSON.

## Write the narrative

Fill the sections of the `.md` from the transcript and the git history, and
from nothing else. Rules that keep it an assessment rather than a story:

- **What was built.** Input, output, and what a person can now use. One paragraph.
- **Defects found after the first "done".** One row per defect a person
  reported after the work was first called done: what it was, who found it
  (the human, a resident, a gate), and whether a gate that exists or could
  exist would have caught it. This table is the cost side; keep it complete
  even when it is long. Read the transcript for the human's own words
  ("this is confusing", "that's wrong") and count them all.
- **What the graph caught before a person did.** Findings from `tl check`,
  the challenger, stamps on moved sources and document gates that stopped a
  defect before it shipped. This is the benefit side; cite the finding, not
  the feeling.
- **Human effort.** What only the human did: decisions, ratifications,
  corrections, the reading of a statute or a standard. Count ratification
  hand-offs; they are in the transcript.
- **Verdict.** In the measured terms above: what the graph cost (turns, hours,
  tokens, items amended after ratification) and what it returned (defects
  caught, documents that could not drift, an implementation pinned to a
  specification). Then one judgement, in one sentence, that a reader could
  disagree with. Do not average across cases here; the collection's index is
  where cases are compared.

Where a number in the table surprises you, do not explain it away in prose;
check the input (a session that did other work, a transcript that was
compacted, a test file that lists no results) and re-record with the input
corrected.

## Re-assessing

The same work reaches "done" more than once as its specification moves. Record
again under the same name; the date and time in the file name keep the records apart
and the collection's index shows the trend. Never overwrite an earlier record.

## What this skill is not

It does not judge the work's quality by reading the code or the items; the
challenger does that. It does not compare tools; a case records what happened
with this one. It does not estimate what the work would have cost without a
graph: no such number exists, and a made-up one would poison the collection.
