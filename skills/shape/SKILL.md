---
name: shape
description: Initialise a throughline IDD graph for a new piece of work by a structured discovery conversation instead of the fixed register set `tl init` lays down. Use whenever someone wants to "initialise a throughline", "set up IDD", "start a new graph", "shape the registers", "work out which registers we need", or "run tl init" for work that has no graph yet — and when a repo already has `idd/shape/` and the work has moved, to re-confirm the reasoning. Reads the sources, states the domain, writes down what the work needs from its graph, and only then proposes registers, each with a rationale and each rejection recorded; the reasoning lives in `idd/shape/` and the work's own graph in `idd/<name>/`, named during discovery. Everything it writes is AI-origin and `proposed`; a human ratifies. `tl init` is untouched and remains the command-line route.
user-invocable: true
---

# Shape a throughline graph

Initialising a graph is a judgement, so it belongs to intelligence, not to a
scaffold. `tl init` lays down one fixed register set — vision, requirements,
non-functional, non-goals, tests — because that was the first idea, and a
scaffold cannot know whether this piece of work needs a risk register, a
constraints register, or something the tool has never seen. A conversation
can. This skill is that conversation, and it records its own reasoning in a
graph that sits beside the one it produces, so the register set is as
ratifiable as anything in it.

Two graphs, one repository, under `idd/`:

```
idd/shape/   the reasoning — fixed name, always this, owned by this skill
idd/<name>/    the work itself — named during discovery; this skill only proposes into it
```

Rules that hold throughout:

- **Never call `tl init` with its defaults**, and never depend on what it
  produces. The script lays the layout down from `--bare` and `tl register new`.
- **Everything you write is `origin: ai`, status `proposed`.** You never
  ratify. The script's `new` command binds both; use it for every item.
- **Registers come last.** If you reach for them before the needs are
  confirmed you will reproduce the same defaults `tl init` gives, which is the
  failure this skill exists to remove.
- **A rejection is an item, not silence.** A register you considered and did
  not create is a `non_goal` in `idd/shape/`, with its rationale, next to the ones
  you did create. There is no decisions register; the graph is the decision log.
- **Never hand-edit a `<UID>.yml` or `.register.yml`.** Every structural change
  goes through `tl`; the script wraps the calls that matter.
- **Stop at registers.** Gate both graphs, hand back for ratification, and
  *offer* to go on to the first layer of items, starting with the intent the
  second graph is grounded in. Do not go on unasked.

## First: tools and the script

```sh
tl --version || pip install 'throughline>=3.11.0'
S="${CLAUDE_PLUGIN_ROOT}/scripts/shape.py"
python3 "$S" --help
```

Needs Python ≥ 3.11 and throughline ≥ 3.11.0, the release from which `tl`
composes a graph's sources itself; the script exits 2 on an older `tl`. If the
plugin root variable is unset, the script sits at
`scripts/shape.py` beside this file's plugin. `references/layout.md` records
what was verified about the tool on the date it names; `tl --help` beats both.

The script does only the mechanics — layout, well-formed items, the second
graph from the decisions, the check gate. The judgement below is yours.

## Has this repo been shaped before?

```sh
python3 "$S" -C <repo> status
```

If `idd/shape/` exists, **do not start again.** Read the prior reasoning
back — `tl -C idd/shape context`, then each register's items — and
put it to the person stage by stage: *"Last time this was read as a
data-migration project with these three needs; is that still true?"* Amend
what changed with `tl amend` (a normative change marks dependants
suspect, which is correct), add what is new, and mark what no longer holds
`rejected` with `tl status`. A prior name decision stands unless they
say otherwise; the second graph is never renamed by this skill. Then continue
from whichever stage below the change reaches.

If the repo's `idd/` is itself a graph root (a `throughline.toml` directly in
it), this layout cannot be used there; say so and stop. The script refuses too.

If there is no `idd/shape/`:

```sh
python3 "$S" -C <repo> init
```

## The discovery, in order

Each stage produces items in `idd/shape/`. Confirm each stage with the
person before moving to the next; the confirmation is what makes the later
items grounded in more than your own reading.

### 1. Sources

Ask what to read: briefs, decks, existing docs, code, a ticket. Read each one.
Each becomes a `source` item so provenance survives — title it by what it is,
put a one-line account of what it says in the text, and record where it is.
The script stamps the day it was read (`read`): a source is a record of what
existed that day, not a claim about now, so write it that way — "the two
skills the marketplace held", not "the marketplace's two skills":

```sh
python3 "$S" new SRC --type source --title "Programme brief, March 2026" \
  --text "Sets out the tenants, the audit date and the three services in scope." \
  --attr path=docs/brief.md
```

If there are no sources, say so plainly and move on: the domain reading then
rests on the conversation, and it says so.

### 2. Domain

From the sources and the conversation, state **what area this work is in and
what kind of thing is being built**: a service, an estate, a policy, a
curriculum, a standard, a campaign. Write it as one `domain` item and link it
to every source it rests on. Put it to the person and get a yes before going
on; amend until it is right.

```sh
D=$(python3 "$S" new DOM --type domain --title "A hosting estate run for tenants" \
  --text "..." --ground SRC-0001 --ground SRC-0002)
```

The domain is a delivery root of the shape graph: the needs derive from it,
and a domain reading nothing follows from is a finding.

**Name the second directory here**, once you know what kind of thing this is.
The name says what the graph is a graph *of* — `estate`, `service`, `policy`,
`curriculum`, `handbook` — lower-case, one word where one will do. Never
default to `product`, `subject`, `domain` or any other placeholder; if you
cannot name it, you do not yet know what is being built, and that is the
question to ask. The naming is a decision item grounded in the domain:

```sh
python3 "$S" new DEC --type decision --title "Name the graph estate" \
  --text "The work is an estate, so the graph is idd/estate/." \
  --attr kind=name --attr dir=estate --ground "$D"
```

### 3. Specific needs

What does *this* work need from its graph? Ask, and write each answer as a
`need` grounded in the domain: what has to be traceable and to what; what has
to be gated before release; what a regulator, auditor, customer or board will
ask to see; what accountability record must exist; what will change often and
needs its dependants flagged. Give each a rationale when the reason is not in
the text.

```sh
N=$(python3 "$S" new NEED --type need --title "Every control traces to a threat" \
  --text "The auditor will ask which threat each control answers." --ground "$D" \
  --rationale "ISO 27001 audit is booked for Q2.")
```

**Inherited standards** arrive here. If the team has a standing rule — "every
graph has requirements and tests", "always a risk register" — record it once
as a `constraint` in `idd/shape/` and ground the register decisions it mandates in
it rather than rediscovering them. A constraint is a delivery root: one that
no decision follows from will fail the check, which is right.

```sh
C=$(python3 "$S" new CON --type constraint --title "Team standard: REQ and TEST in every graph" \
  --text "The platform team's standing rule for every graph it owns.")
```

Confirm the needs with the person. Not until they are confirmed do you say the
word *register*.

### 4. Registers

Only now, propose the register set for the second graph. Hold the needs
together and ask, for each need, what register would carry the items that
answer it — and whether one already proposed does. Then present the whole set
for confirmation, **before anything is written to the second directory**, as a
table: register, what it holds, which need it answers, and beside it every
register you considered and are *not* proposing, with why.

Each register you propose is a `decision` grounded in the need (or standard)
that calls for it. Its attributes are what the script builds from:

| attr | meaning |
|---|---|
| `kind` | `register` |
| `prefix` | the UID prefix, upper-case, e.g. `THR` |
| `dir` | the folder under `idd/<name>/`, e.g. `threats` |
| `item_type` | the item type it holds, e.g. `threat` — a default type or a new one |
| `grounding` | `root`, `delivery-root`, or `grounded` (the default) |

```sh
python3 "$S" new DEC --type decision --title "Threats register" \
  --text "One item per threat the audit will ask about; controls mitigate them." \
  --attr kind=register --attr prefix=THR --attr dir=threats \
  --attr item_type=threat --attr grounding=delivery-root --ground "$N"
```

`grounding` is the throughline question: can an item of this type stand on its
own, or must it reach a root? A `root` may exist ungrounded; a `delivery-root`
additionally must have something deriving from or mitigating it; everything
else must trace to a root. `intent`, `business_need`, `risk` and `constraint`
are delivery roots already; `assumption` and `non_goal` are roots. **At least
one register must hold a delivery root**, or the graph has nowhere to put the
intent its first layer will be grounded in; the script refuses to write
otherwise.

Each register you considered and rejected is a `non_goal` with its rationale,
linked (`derives_from`) to the need that made it unnecessary or the domain
reading that made it wrong:

```sh
NG=$(python3 "$S" new NG --type non_goal --title "No risk register" \
  --text "Threats and controls already carry the risk picture; a third register would split it." \
  --rationale "Considered because tl init would have offered one.")
tl -C idd/shape link "$NG" "$N" --type derives_from
```

*Considered* includes the five `tl init` would have given: say, for each of
vision, requirements, non-functional, non-goals and tests, whether it is in
and why, or out and why. Their absence from the set is a decision, not an
oversight.

### 5. Write, gate, hand off

```sh
python3 "$S" -C <repo> write
```

This creates `idd/<name>/` from `--bare`, declares each item type, root and
`origin` attribute the decisions call for (every change carries a `--because`
naming the decision), creates the registers, and records the pointer: a
`path` source in `idd/shape/throughline.toml` naming the second graph. `tl`
composes the second graph through that pointer, so `tl -C idd/shape context`
shows the whole picture from here on.

Gate both graphs:

```sh
python3 "$S" -C <repo> check
```

Hand back on **zero errors in both graphs**. The second graph holds registers
and no items yet, which throughline reports as the warning `empty-registers`,
not an error; do not author an item to silence it. Other warnings will remain:
every item in `idd/shape/` is AI-origin and unratified, and that is the point.
`--strict` is the gate *after* ratification; a graph the skill has only
proposed into cannot pass it, and you must not make it pass by ratifying.

Then stop and present, naming the absolute path and the command to run:

> Shaped. `idd/shape/` holds N items across sources, domain, needs, decisions,
> non-goals and constraints; `idd/<name>/` has these registers and no items yet.
> Both report zero errors.
> To ratify: `cd <absolute repo path> && tl -C idd/shape ratify` for
> each of <UIDs>. I can go on to the first layer of items in `idd/<name>/`,
> starting with its intent, if you want; I have stopped at registers.

Ratification is a human act. If asked to do it, decline and say why: a
fabricated `ratified_by` is the one thing this toolchain exists to prevent.

## What the shape graph looks like

The script lays this down every time, because the conversation is the same
shape every time:

| register | prefix | type | root? | holds |
|---|---|---|---|---|
| `sources/` | SRC | `source` | root | each document read, with its `path` and the day it was `read` |
| `domain/` | DOM | `domain` | delivery root | the reading of what this is |
| `needs/` | NEED | `need` | — | what the work needs from its graph |
| `decisions/` | DEC | `decision` | — | the name, and one per register created |
| `non-goals/` | NG | `non_goal` | root | registers considered and not created |
| `constraints/` | CON | `constraint` | delivery root | inherited team standards |

Links are `derives_from` throughout: domain from sources, needs from domain,
decisions from needs or constraints, the name from domain, non-goals from the
need or domain that ruled them out. A prior run's items stay where they are;
a second pass amends, adds or rejects, and the fingerprints record which
dependants that disturbed.

## What this skill does not do

It does not change `tl init` or any `tl` command. It does not ratify. It does
not rename or delete the second graph once written; adding a register to an
existing second graph is a new decision in `idd/shape/` followed by
`tl register new` there by hand, and the script says so. It has no view on
which model or editor does the second graph's work afterwards.
