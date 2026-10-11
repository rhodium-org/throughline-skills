---
name: reconcile
description: Reconcile a codebase with the throughline IDD graph it claims to implement, and cite graph items in code while writing it. Use when asked to "reconcile", "check the code against the graph", "is the code aligned with the requirements", "which requirements are implemented", "trace requirements to code", or before handing off code written under a graph; and whenever you write or change code in a repository that holds a throughline.toml, so the code cites the items it serves. Code and graph are two records of one thing: this skill reports where they disagree and asks the human which side moves, and never makes them agree on its own.
user-invocable: true
---

# Reconcile code with its graph

A graph says what the work is for; the code is what was built. Where they
disagree, either can be the wrong one: the code drifted from a ratified item,
or the item is out of date, or neither is clearly wrong (code nothing
justifies, an item nothing builds). This skill finds the disagreements and puts
each to the human as a choice of which side moves. It is a check, not a tool
that makes the code match.

It has two parts. **Part A** is how code cites the graph, which you do every
time you write code under one. **Part B** reconciles a codebase through those
citations: a script for what needs no judgement, and reading for what does.

## First: is there a graph?

```sh
find . -name throughline.toml -not -path '*/.venv/*' -not -path '*/.git/*'
```

No graph, nothing to reconcile and nothing to cite; say so and stop. More than
one, and every citation must name its graph (below).

## Next: tools and the script

```sh
tl --version || pip install 'throughline>=3.11.0'
S="${CLAUDE_PLUGIN_ROOT}/scripts/reconcile.py"
python3 "$S" --help
```

The script needs only the Python standard library and `tl` from throughline
3.11.0, and exits 2 on an older one. Nothing else is installed, ever. If the
plugin root variable is unset, the script sits at `scripts/reconcile.py`
beside this file's plugin.

## Part A: cite the graph as you write

<!-- tl: implements tl-reconcile/REQ-0014 -->
When you write or change code in a repository holding a graph, cite the items
it serves **as you write it**, not afterwards: a citation written with the code
records what it was written for; one added later records what someone believes
it does. Put the citation at **the smallest unit that realises the item** —
the function, class, test or block — never as a file header listing everything
the file touches.

### The notation

A citation is one comment line: the marker `tl:`, a link type from the graph's
own vocabulary, and one or more comma-separated item references. Only the
start of a line counts; a trailing comment after code is not a citation.

| Language family | The line above the code |
|---|---|
| Python, shell, Ruby, YAML, TOML | `# tl: implements billing/REQ-0042` |
| C, Java, JS/TS, Go, Rust, Swift | `// tl: implements billing/REQ-0042` |
| SQL, Lua, Haskell | `-- tl: implements billing/REQ-0042` |
| Lisp, assembly, INI | `; tl: implements billing/REQ-0042` |
| TeX, Erlang, MATLAB | `% tl: implements billing/REQ-0042` |
| HTML, XML, Markdown | `<!-- tl: implements billing/REQ-0042 -->` |
| Block comments, docstrings | a line inside opening `tl:` or `* tl:` |

- **Link type.** `implements` or `satisfies` for code that builds an item,
  `verifies` for a test, read from the graph's `[links] types`. The script
  rejects a word outside the vocabulary.
- **Graph name.** In a repository with one graph, `REQ-0042` is enough. With
  more than one, every reference names its graph's project name and a slash:
  `billing/REQ-0042`. A borrowed item keeps its namespace: `billing/spec:SR-0032`.
- **Several items.** `# tl: implements billing/REQ-0042, billing/REQ-0043`.
- **Stamp, optional.** `billing/REQ-0042@3f9a1c0d4e2b` records the item's
  fingerprint when you wrote the code, at least eight hex digits. When the
  item's wording changes, the stamp goes stale and the scan says so. Stamp
  where it pays: items that change often, and code implementing a
  specification another repository owns. Write stamps with `restamp` (Part B),
  never by hand.

End the commit subject with the graph and the UIDs it serves, as this
repository does: `… (billing REQ-0042, TEST-0042)`.

### A standing instruction for the repository

<!-- tl: implements tl-reconcile/REQ-0015 -->
An agent that has not loaded this skill will not cite. The paragraph below,
added to the repository's `CLAUDE.md` or equivalent, makes it do so. Offer it
when a repository with a graph has none; **add it only when the person asks**.

```text
## Citing the graph in code

This repository holds a throughline graph. When you write or change code,
cite the graph items it serves at the time you write it, in a comment line
directly above the function, class, test or block that realises the item:
the marker tl:, a link type from the graph's vocabulary (implements or
satisfies for code, verifies for tests), then the item references,
comma-separated, as in `# tl: implements REQ-0042` (in a repository with
more than one graph, name it: `# tl: implements billing/REQ-0042`). Never
cite in a file header. End each commit subject with the graph and UIDs it
serves, as in (billing REQ-0042, TEST-0042).
```

## Part B: reconcile a codebase

### 1. Scan

```sh
python3 "$S" -C <repo> scan                       # the whole repository
python3 "$S" -C <repo> scan src tests --exclude 'vendor/**' --graph billing
```

The scan reads only files git tracks, skips every graph root and anything
`--exclude` names, and starts by saying how many files and citations it read:
if that count is wrong, the paths are wrong, and nothing below it means
anything. `--graph` limits the graph-side findings to the graphs named; in a
repository of several graphs, scope it to the one the code serves. `--json`
gives the same report for a machine; `--gate` makes any finding exit 1, for
CI once a repository is ready for it.

### 2. Read what the script found

| Finding | What disagrees | The question for the human |
|---|---|---|
| `malformed`, `unknown-link-type` | a citation that does not parse | none if the intent is plain (fix it); else which item was meant |
| `unknown-graph`, `ambiguous-graph`, `unqualified` | a reference that names no one graph | none if only one graph holds the UID (qualify it); else which graph |
| `no-such-item`, `dead-item` | code citing what the graph does not hold | is the code obsolete, or is an item missing from the graph? |
| `uncited` | an accepted item no code builds | is it unbuilt, built without a citation, or no longer wanted? |
| `claimed-absent` | an item at `implemented` no code builds | was it built uncited, or is the status wrong? |
| `unaccepted` | code building an item nobody has accepted | should the item be ratified, or the code removed? |
| `under-question` | code resting on a suspect item | does the code still hold once the item is settled? |
| `not-wired`, `unrecorded-test` | a test the graph and the test code do not both record | add the test, or the item, or the link? |
| `stale` | a stamp written against an earlier wording | does the code still meet the item as it now reads? |

Items realised through their children are listed apart and are not findings:
a parent requirement is usually built by what refines it. The review order
for unstamped citations (item changed after the code first) is where to start
reading, never a finding in itself.

### 3. Read each cited location against its item

<!-- tl: implements tl-reconcile/REQ-0013 -->
The script proves a citation resolves; it cannot tell whether the code does
what the item says. For each citation in scope, open the item
(`tl -C <graph root> context <UID>`) and the code beside it, and read the
code against the item's **text and its priority** (a `must` read as `should`
is a finding). Report where the code does **less** than the item says, **more**
than it says, or **other** than it says. Then look at the code in scope that
cites nothing and ask what item justifies it; code that traces to nothing is
reported, not cited into a convenient item.

<!-- tl: implements tl-reconcile/REQ-0016 -->
If the repository already holds a structural graph of its code (a code-graph
tool's output, an index), you may use it to find where an uncited item is
probably built. Install no such tool. A code graph only narrows the search: it
never closes a finding, because a structural link is not a written citation.

### 4. Put each disagreement to the human

<!-- tl: implements tl-reconcile/REQ-0012 -->
Report every finding with **both sides as they stand**: the item (UID,
status, text) and the code (file, line, what it does). Then ask which side is
wrong. Until the human has said:

- **never amend an item** to match the code, and never reword one to make a
  finding go away;
- **never revert or withdraw a ratification**, and never touch `ratified_by`;
- **never change code** to match an item, or delete it because nothing cites it.

What you settle alone is only the mechanical:

- a **malformed or unqualified citation with exactly one possible target**:
  fix its form, or add the graph name that alone holds the UID;
- a **stamp you have re-read the code to confirm**: read the item as it now
  stands and the code it cites, and only if the code still meets it, restamp.

```sh
python3 "$S" -C <repo> restamp billing/REQ-0042          # every citation of one item
python3 "$S" -C <repo> restamp src/charge.py:41          # the citations on one line
```

There is deliberately no form that restamps everything: a stamp records that
someone re-read the code, and a bulk restamp would record that without anyone
having done it.

When the human decides, the change goes through the usual routes: an item is
amended with `tl amend` and re-ratified by the human; code is changed and its
tests run; then scan again.

### 5. The citation table, for generated documents

```sh
python3 "$S" -C <repo> table                         # print it
python3 "$S" -C <repo> table --write docs/trace.md   # between the markers
python3 "$S" -C <repo> table --check docs/trace.md   # exit 1 when stale; for CI
```

The table lists every cited item with each citation's link type, file and
line. `--write` replaces whatever sits between a `<!-- reconcile:begin -->`
line and a `<!-- reconcile:end -->` line in the file, which you add once. Run
it beside `tl docs` so the documents say where each requirement is built and
tested.

### Report shape

Lead with the scan's count line. Then, for each finding: its kind, the item
as it stands, the code as it stands, and the question for the human, stated as
a question. Then what you settled alone, and why each was mechanical. Then
your reading of cited locations (less, more, other) and the uncited code that
traces to nothing. Say plainly when there are no findings.

## Traps

- **New files are invisible until git tracks them.** `git add` before you scan
  code you have just written.
- **Examples in documentation are citations too** when a line opens with the
  marker; put them in a table or mid-line, as this file does, or `--exclude`
  the file.
- **A trailing comment is not a citation.** `x = 1  # tl: implements …`
  is ignored; the citation goes on its own line above.
- **In a repository of several graphs, scope with `--graph`.** Otherwise every
  graph's uncited items are listed, most of them nothing to do with the code
  you scanned.
- **A stale stamp is a question, not a fault.** The item moved; whether the
  code must follow is the human's call, and the report names the commit of
  the edition you stamped so the two can be compared.
