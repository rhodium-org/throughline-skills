---
name: challenge
description: Run a challenge pass over a throughline IDD graph before handing proposed items to a human to ratify, and re-check an implementation graph against a specification it composes once that specification has been re-ratified or re-tagged. Use when asked to "run the challenger" or "challenge the graph", before any hand-off of proposed or amended items, after amending ratified items, or when a composed source moved and you need to know which local items are now suspect, which links into it are unstamped, and which of its items nothing local implements. `tl check` proves structure; this pass asks whether the graph is also true.
user-invocable: true
---

# Challenge a throughline graph

`tl check` proves that every item reaches a root through a well-formed link. It
cannot tell whether a child claims more than its parent grants, whether two
siblings name the same thing differently, whether prose cites an item the links
never record, whether a branch is verified by anything a machine could run, or
whether a new item quietly contradicts a ratified one. Those are the defects a
human ratifier is asked to catch, and ratifiers miss them.

This skill is the hand-run form of the challenge pass that the throughline
family's `throughline-challenger` tool is designed to automate. The twelve
challenges below are its, each cited by its UID in that graph
([rhodium-org/throughline-challenger](https://github.com/rhodium-org/throughline-challenger),
which this skill's own graph composes at the tag its `throughline.toml` names); the script here does the
deterministic ones, and the rest are questions you put to the graph by reading
items held together.

It has two parts. **Part A** challenges a graph you have just changed, before
hand-off. **Part B** re-checks an implementation graph against the specification
it composes, after that specification moved.

## First: is there a graph?

```sh
find . -name throughline.toml -not -path '*/.venv/*' -not -path '*/.git/*'
```

If that finds nothing, there is nothing to challenge. Say so, point at
`tl init --no-demo` (or `tl-compose init`) to create one, and stop. Do not put
the challenges to a proposal, a schema, a document or the conversation, and do
not present a review of such prose under the challenge numbers or in the report
shape below: every challenge is defined over items, links and stamps, and none
of those exist until a graph does. If a design opinion would help, give it as
one, labelled as one, outside this skill's report.

## Next: tools and the script

```sh
tl-compose --version || pip install throughline-compose   # brings tl with it
S="${CLAUDE_PLUGIN_ROOT}/scripts/challenge.py"
python3 "$S" --help
```

The script reads the JSON that `tl-compose dump` emits (or bare `tl dump` when
the graph has no `[[sources]]`) and needs nothing beyond the standard library.
`-C <graph root>` runs the tool for you; `--dump FILE` reads a saved dump. Every
command exits 0: the output is a review list, never a gate. If the plugin root
variable is unset, the script sits at `scripts/challenge.py` beside this file's
plugin.

## The twelve challenges

| # | Challenger | Challenge | Who does it |
|---|---|---|---|
| 1 | REQ-0001 | **Link strength.** Does the parent entail the child at the stated modal strength, in both directions, and does a `satisfies` link to a standard claim no more than the clause grants? | you, from `siblings` |
| 2 | REQ-0002 | **Prose mention without an edge.** Text or rationale names an item by UID and the links block has no edge to it. A UID inside a file path is listed apart as a path mention, not counted. | `mentions` |
| 3 | REQ-0003 | **Same things, different names.** Siblings under one parent enumerate a set and quantify over a narrower or differently named class of it. | you, from `siblings` |
| 4 | REQ-0004 | **Verification per branch.** How each branch is verified; a branch with no automated check, or whose automated checks all sit on one kind of item. | `verification` |
| 5 | REQ-0005 | **Untestable as written.** A predicate no observation of the running system could settle. | `untestable` (word list) + you |
| 6 | REQ-0006 | **Rationale narrower than the family.** Would an implementation satisfying this item and its stated reason break a sibling? | you, from `siblings` |
| 7 | REQ-0007 | **No failure case.** The item says what is wanted and never what a violation looks like. Weak signal; review order, not a gate. | `failure-case` |
| 8 | REQ-0008 | **Points at its own replacement.** A live item carrying a link whose meaning is that the target replaces it. | `replacement` by name; you classify the vocabulary by meaning |
| 9 | REQ-0009 | **Universal force, one mechanism.** "always/every/never" on a parent that exactly one non-test child realises. | `universal` |
| 10 | REQ-0010 | **Unstamped link into a source.** A link into a composed specification with no stamp cannot tell when its target moves. | `unstamped` |
| 11 | REQ-0011 | **Spec item nothing implements.** A borrowed item of an implementable type with no incoming local link. | `uncovered` |
| 12 | REQ-0012 | **Stamped target moved.** The target as stamped beside the target as it stands; does the item still hold? | you, from `check` and the source cache |

Challenges 1 to 9 are Part A; 10 to 12 are Part B.

## Part A: challenge a graph before hand-off

### 1. Scope the pass

The pass is over the items you touched **and their families**. Get the touched
UIDs from git, then the families from the script:

```sh
git diff --name-only HEAD~1 -- idd | sed -E 's#.*/([A-Z]+-[0-9]+)\.yml#\1#' | sort -u
python3 "$S" -C idd siblings SR-0041      # every parent, and the other children under each
```

The siblings output is the material for challenges 1, 3 and 6. Hold it together:
the defect is invisible in either item alone.

### 2. Run the deterministic checks

```sh
python3 "$S" -C idd all                                    # local items only
python3 "$S" -C idd verification --branch-types user_requirement --ignore-types journey,page
```

`all` runs mentions, universal, verification, failure-case, untestable,
replacement and unstamped over local items. Run `verification` again with the
type that heads a branch in this graph (a user requirement, a business need)
and `--ignore-types` for kinds the graph verifies by other means, such as
journeys walked by one end-to-end test. Read the `untested:` list on each
branch: an item there has no `verifies` link at all.

Borrowed items are skipped by `all`. Run `mentions` without `--local-only` once
if you want a source's own dangling mentions; they belong to the source's owner,
not to you.

### 3. Put the semantic questions

For each touched item, with its `siblings` output open:

- **Strength (1).** Read the parent's text. Does it grant what the child claims,
  at the child's modal strength? Then the reverse: does the parent claim a blanket
  property that this child realises only for one case? For every `satisfies`
  link into a standard, read the clause; the link is a claim you read it and the
  item meets it. A knowing deviation is `relates` with the reason in the
  rationale, never `satisfies`.
- **Names (3).** Do two siblings quantify over the same things under different
  names, or does one enumerate what another narrows? Check against the graph's
  own type names: if search and filter are separate types, "a filter" is not
  "search, filter and sort".
- **Rationale (6).** Take the item's rationale as the whole reason for building
  it. Would the cheapest implementation satisfying item-plus-rationale break a
  sibling? This is where a new item most often contradicts a ratified one.
- **Collision sweep.** Grep the siblings' texts for absolute clauses: `never`,
  `only`, `no other`, `nothing else`, `cannot`. Ask of each whether the new
  item's mechanism breaks it. A new item that lets an actor do something a
  ratified sibling says that actor never does is the commonest finding.

### 4. Fix through the CLI, never by hand

- An AI-origin item still `proposed` is yours to fix: `tl amend`, `tl link`,
  `tl unlink`. Rewrite the claim in the fewest words that bind — never append
  a qualifying clause. If the decision changed, record the decision and the
  alternative rejected in the rationale; never the history of the pass.
- A ratified item you must amend stays ratified and gains a `ratified-stale`
  finding until the human re-ratifies it. That is correct: the human accepts the
  new wording or reverts it. Never `git checkout` an item to escape it, and
  never touch `ratified_by` or `ratified_fingerprint`.
- Every prose mention the script reports gets a link or a reword. A `relates`
  edge is the honest minimum.
- If a fix needs a source's clause to change, the fix belongs in the source
  first; the consumer repins afterwards.
- Never allocate a UID, edit a `.register.yml`, or hand-edit a link.

### 5. Re-gate and hand off

```sh
python3 "$S" -C idd all                      # the findings you fixed are gone
tl-compose -C idd check --strict             # only unratified / ratified-stale remain
tl-compose -C idd docs && tl-compose -C idd docs --check
```

In a composed repo use `tl-compose` for `docs` too: bare `tl docs` cannot
resolve borrowed clauses and silently strips their labels from the generated
documents, which shows up as a spurious diff. Commit explicit paths, cite the
UIDs, and hand off with the count: N new items, M stale ones, and the exact
`tl -C <graph root> ratify` command for the graph in question.

### Report shape

For each finding: the challenge number, the item, the sibling or clause it
collides with, and what you changed or why you left it. Findings you could not
settle are questions for the ratifier, stated as questions.

Name each challenge by its number and by what it asks. Never by "Part A" or
"Part B": those labels exist only in this file, and the reader has not read it.
A challenge that does not apply to the graph is said not to apply and why, for
example that challenges 10 to 12 concern a composed specification and this graph
composes none.

## Part B: an implementation against a moved specification

This applies when a graph composes another graph as its specification, for
example an implementation graph whose `[[sources]]` block names the spec under a
namespace such as `spec`, and the spec has since been re-ratified or re-tagged.
It performs challenger REQ-0010 (unstamped links), REQ-0011 (spec items nothing
implements) and REQ-0012 (the question when a stamped target moved).

### 1. Stamp every link into the spec

A stamp records the target's fingerprint at the moment you confirmed the link.
Without it a moved spec is invisible to `check`.

```sh
tl-compose -C idd link REQ-0007 spec:SR-0032 --type implements --stamp
python3 "$S" -C idd unstamped --namespace spec      # links that cannot detect drift
```

To refresh a stale stamp, **unlink then relink**. Running `link --stamp` again
on an existing pair adds a second link and leaves the stale one in place:

```sh
tl-compose -C idd unlink REQ-0007 spec:SR-0032 --type implements
tl-compose -C idd link   REQ-0007 spec:SR-0032 --type implements --stamp
```

### 2. Repin and read the suspects

Point the source's `ref` at the new tag (never at a branch you intend to stay
on), then:

```sh
tl-compose -C idd check
```

Every `suspect-link` finding is one local item whose spec target changed since
you confirmed it. For each: read the target as it now stands
(`tl-compose -C idd context spec:SR-0032`, or diff the two editions in
`~/.cache/throughline-compose/sources/`), then decide:

- **Still satisfied.** Refresh the stamp (unlink, relink `--stamp`) and note in
  the rationale what moved and why it does not bind this item.
- **No longer satisfied.** Move the item to the graph's suspect status with
  `tl status <UID> suspect`, amend it, change the code and its tests, run the
  tests its `verifies` links name, move it back, refresh the stamp.

### 3. Find what the new spec adds

```sh
python3 "$S" -C idd uncovered --namespace spec --types system_requirement,nfr --links implements,satisfies
```

Each item listed is a spec item nothing local implements. It needs a local
implementer, or a recorded decision that it is outside this implementation, as
a non-goal that `relates` to it. Silence is neither.

### 4. What the consumer check shows that it cannot fix

A consumer's `check` also prints the spec's own `ratified-stale` and
`unratified` findings on borrowed items (`spec:SR-0004 ratified-stale …`). Those
mean the spec has unaccepted changes: the remedy is in the spec repo, by its
ratifier. Report them and do not pin a branch to make them go away.

## Traps

- **The script judges names, not meanings, for challenge 8.** It prints the link
  vocabulary; you classify by what each type means in this graph.
- **`all` is local-only.** Borrowed items are their owner's to challenge.
- **Journeys and pages read as untested** on every branch when the graph
  verifies them with one end-to-end test that `verifies` something else.
  Either link that test to them or pass `--ignore-types journey,page` and say so.
- **A leaf with universal language is not flagged**: its test guards it. The
  finding is a parent whose blanket claim exactly one child realises.
- **`tl check` sees status moves against the committed baseline.** Ratifying and
  re-statusing are two commits; do not combine them.
