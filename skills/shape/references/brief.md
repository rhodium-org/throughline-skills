# Project brief: `throughline-shaping` skill

You are starting cold. This document is your full context. Read it, then follow **Start here** at the bottom.

## Mission

Build an **Agent Skill** (working name `throughline-shaping`; rename if a better one emerges) that uses Claude to initialise a [Throughline](https://pypi.org/project/throughline/) graph for a new piece of work. It replaces the guess that `tl init` currently makes about which registers a project needs with a structured discovery conversation, and it records the reasoning behind that conversation in a second graph that lives alongside the first.

Doctrine, in one line: **initialising a graph is a judgement, so it belongs to intelligence, not to a scaffold.** `tl init` stays exactly as it is for people who know what they're doing on the command line. This skill is the other route, and it starts from nothing.

## Context

### Throughline

Git-native intent/requirements graph. One small YAML file per item; permanent UIDs; typed directed links; a grounding rule that every non-root item must reach a root (`intent`, `business_need`, `constraint`, `risk`, `assumption`, `non_goal`) through grounding links. `tl check --strict` validates the graph and gates CI. SHA-256 normative fingerprints mark dependent links suspect when content changes. AI-origin items (`origin: ai|hybrid`) enter as `proposed` and require human ratification (`tl ratify`). The method is called **IDD, Intent-Driven Development**.

Commands you will lean on: `tl init`, `tl new`, `tl link`, `tl check --strict`, `tl ls`, `tl trace`, `tl context`, `tl ratify`. Run `--help` on each. **Do not trust this brief over the installed tool.**

`throughline-compose` composes multiple source graphs into a union under importer-chosen namespaces. It is how the two graphs described below get read together when someone wants the whole picture.

Known upstream bugs, be defensive: a malformed link entry missing `target` crashes the loader with a raw `KeyError` (`model.py:66`), so validate any YAML you write before handing it to the library; and the published sdists ship tests with missing fixtures, so don't copy that packaging mistake.

The GitHub repos (`github.com/rhodium-org/...`) may be private. Work from the PyPI sdists if you need source truth: `pip download --no-binary :all: throughline throughline-compose`.

### The problem being solved

`tl init` today lays down a simple, fixed set of registers, including a requirements register. That was the first idea when the tool was built and it is generally not appropriate: a scaffold cannot know whether a given piece of work needs a risk register, a constraints register, or something the tool has never seen. A conversation can.

## Design decisions (settled, do not relitigate)

1. **`tl init` does not change.** No new flags, no bare mode. It remains the command-line path for someone who wants to build an IDD by hand. The skill does its own initialisation from scratch and does not depend on `tl init` producing any particular layout.

2. **Two graphs, one repo, under a common directory called `idd/`.** Not `graphs/`; the directory names the method, not the data structure.
   - `idd/shaping/` is fixed. It always exists and always has that name. It holds the reasoning that produced the other graph.
   - The second directory holds the graph for the thing actually being built. **The skill names it** during discovery, once it knows whether the work is a service, an estate, a policy, a curriculum, or something else. Do not hard-code `product`, `subject`, `domain`, or any other default. The chosen name is recorded in configuration so tooling has a pointer, and the naming decision is itself a ratifiable item in shaping.

3. **Ownership split.** The skill owns `idd/shaping/` outright. It only ever *proposes* into the second graph. Everything it writes anywhere carries `origin: ai` and enters as `proposed`. Henry ratifies; the skill never does.

4. **Discovery runs in a fixed order.** Sources, then domain, then specific needs, then registers. Registers come last on purpose: if the skill reaches for them early it will reproduce the same defaults `tl init` gives today, which is exactly the failure being designed out.

5. **Rejections are items, not a separate register.** "We will not have a risk register" is a `non_goal` or `constraint` in shaping, with a rationale, sitting next to the registers that were created. There is no decisions register; the graph is the decision log. Team standards arrive the same way, as a constraint saying "these registers, always", which shaping inherits rather than rediscovers.

6. **Judgement in instructions, mechanics in scripts.** Reading sources, deciding what the domain is, choosing and naming registers, writing rationale: SKILL.md. Creating directories, writing well-formed YAML, running `tl check --strict`, recording the config pointer: `scripts/`. This keeps the scripts eligible to graduate into a package later.

## The discovery flow

The skill runs a structured conversation. Each stage produces items in `idd/shaping/`.

1. **Sources.** Henry points the skill at documents to read: briefs, decks, existing docs, code. Each source becomes a first-class item so provenance survives. If there are no sources, say so and move on.
2. **Domain.** From the sources and conversation, the skill states what area this work is in and what kind of thing is being built. This is written down as an item and confirmed before proceeding. This is also where the second directory gets its name.
3. **Specific needs.** What this particular piece of work needs from its graph: what has to be traceable, what has to be gated, what regulators or stakeholders will ask about. Written as items.
4. **Registers.** Only now does the skill propose a register set for the second graph, each with a rationale grounded in the needs above, plus explicit rejections for registers considered and not created. Presented for confirmation before anything is written to the second directory.
5. **Write.** Create `idd/<name>/`, seed it with whatever the register decisions call for, record the pointer, run `tl check --strict` on both graphs, stop and present for ratification.

## What lives in `idd/shaping/`

The shaping registers are the same every time, because the conversation is the same shape every time:

- Sources the skill was pointed at
- The domain reading (what area, what kind of thing)
- The specific needs stated
- Register decisions for the second graph, each with rationale
- Rejected registers, as `non_goal` or `constraint`
- The naming decision for the second directory
- Any inherited team standards, as `constraint`

Shaping is re-runnable. On a second pass the skill reads its own prior reasoning and asks whether it still holds ("you told me this was a data-migration project, is that still true?") rather than starting from a blank sheet.

## Requirements (seed these into the skill repo's own graph as `proposed`)

- **R1** The skill initialises a Throughline layout under `idd/` without calling `tl init` and without depending on `tl init`'s current output.
- **R2** `idd/shaping/` is always created with that exact name.
- **R3** The second directory's name is chosen by the skill during discovery and recorded in configuration; no default name is hard-coded.
- **R4** Discovery proceeds sources → domain → needs → registers, and does not propose registers before needs are confirmed.
- **R5** Every item the skill writes has `origin: ai` and status `proposed`.
- **R6** Rejected registers are recorded as `non_goal` or `constraint` items with rationale, not omitted silently.
- **R7** Both graphs are green under `tl check --strict` before the skill hands back.
- **R8** Re-running the skill on a repo that already has `idd/shaping/` reads and re-confirms prior reasoning rather than overwriting it.

## Open questions (decide with Henry, do not assume)

- Does the skill stop at registers, or push on to a first layer of items in the second graph? Not settled. Default to stopping at registers and offering to continue.
- Whether the current `throughline.toml` supports two graphs in one repo, or whether compose config is the pointer. Verify against the installed tool before designing the config format.
- Skill name. `throughline-shaping` is a placeholder.

## Working practices

- Apache-2.0, `Copyright 2026 Time Back Solutions Limited`, NOTICE file matching sibling repos. Python ≥3.11. Runtime deps: `throughline` (and `throughline-compose` only if the pointer lives there). `pytest`. Ship `conftest.py` and fixtures in any sdist.
- **Dogfood.** The skill repo uses its own method: run the skill on itself to shape its own `idd/`, and capture R1–R8 as proposed items for Henry to ratify. Everything else in the Throughline family (core, compose, ratify, edit, challenge, the Claude skill) has been built this way; this is not optional.
- Follow the skill-creator conventions: `SKILL.md` with frontmatter (`name`, `description`), `scripts/`, `references/`. Keep SKILL.md under 500 lines. Make the description pushy enough to trigger on "initialise a throughline", "set up IDD", "start a new graph", "shape the registers", and similar.

## Acceptance

1. Fresh repo, no sources: skill runs discovery from conversation alone, produces `idd/shaping/` and a named second directory, both green under `tl check --strict`.
2. Fresh repo with sources: source items appear in shaping with provenance; domain reading cites them.
3. Rejection test: decline a register during discovery; a `non_goal` with rationale appears in shaping.
4. Re-run test: run the skill again on the result of (1); it re-confirms rather than overwrites.
5. Ordering test: the skill does not name registers before needs are confirmed.
6. The repo's own gates green.

## Non-goals

No changes to `tl init` or any `tl` command. No two-way sync. No opinion about which model or IDE runs the second graph's work.

## Start here

1. `pip install throughline throughline-compose`; read `tl --help`, run `tl init` on a scratch directory and study exactly what it produces so you know what you are *not* reproducing.
2. Verify how the installed tool locates a graph (config file, cwd, env) and work out how two graphs in one repo will be addressed. Write `references/layout.md` with a "verified on <date>" line.
3. Draft SKILL.md with the discovery flow above. Draft `scripts/` for layout creation, YAML writing, and the check gate.
4. Run the skill on its own repo to shape `idd/`; seed R1–R8 as proposed items grounded in an intent (suggested: *"Initialising a graph is a judgement that belongs to intelligence, not to a scaffold"*).
5. Stop and present for ratification before writing acceptance tests.
