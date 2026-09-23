# throughline-skills

Claude Code skills for working in [throughline](https://github.com/rhodium-org/throughline)
IDD requirements repositories.

Install once, and it applies in **your own repositories**. Your graph is
committed there, as it must be — throughline is git-native and the items are the
product. It is the *skill* that stays out: no copy of it is vendored into your
repo, and nothing is installed on your laptop.

## What's in it

| Skill | What it's for |
|---|---|
| `/tl:shape` | **Initialising a graph** for a new piece of work by a structured discovery conversation — sources, then domain, then what the work needs from its graph, and only then the registers — instead of the fixed register guess `tl init` makes. The reasoning lands in `idd/shape/`; the graph for the work itself lands in `idd/<name>/`, named during discovery. Everything it writes is AI-origin and `proposed`; a human ratifies. |
| `/tl:multigraph` | Repositories holding **more than one** throughline graph, composed together: how to wire sibling graphs by `path`, what a source's own sources bring with them, gate every graph, and ratify items whose grounding chain crosses graphs. |
| `/tl:challenge` | A **challenge pass** before hand-off: the twelve questions `tl check` cannot ask (link strength, prose mentions without an edge, siblings naming one thing two ways, verification per branch, untestable predicates, a rationale narrower than its family, no failure case, an item pointing at its own replacement, universal force with one mechanism, and for a composed specification: unstamped links, spec items nothing implements, a stamped target that moved), with a script for the deterministic ones. Also re-checks an **implementation graph against a specification it composes** once that specification moved: stamped links, `suspect-link` triage, and spec items nothing implements. |
| `/tl:assess` | An **objective assessment** of a piece of work when it reaches done: items and acceptance, sources and citations, commits and editions, items amended after ratification, generated documents, tests, session time, tokens and tool calls from the transcripts, then a narrative beside the numbers and a copy in a collection of cases. |

Each skill activates on its own when Claude notices the situation it covers, or
you can invoke one directly as `/tl:shape`, `/tl:multigraph`, `/tl:challenge` or `/tl:assess`.

## Install

Two routes — both work in the terminal and at [claude.ai/code](https://claude.ai/code).

**From GitHub:**

```
/plugin marketplace add rhodium-org/throughline-skills
/plugin install tl@throughline-skills
```

**From the hosted catalogue** (same thing, no GitHub account needed to browse):

```
/plugin marketplace add https://skills.iddn.uk/marketplace.json
/plugin install tl@throughline-skills
```

In the browser you can also do it without typing commands: **Manage plugins →
Marketplaces → Add marketplace**, paste either source above, then install.

## Working on a locked-down laptop

This is designed for it. Everything runs in the Claude sandbox, not on your
machine:

- Each skill installs the CLI it needs itself
  (`pip install 'throughline>=3.11.0'`; from 3.11.0 `tl` composes a graph's
  sources itself). Nothing is installed on your laptop.
- Requires Python ≥ 3.11 in the session, which cloud sessions have, and
  throughline ≥ 3.11.0; the scripts refuse an older `tl`.
- Graphs wired to each other by `path` need no network at all. Graphs that adopt
  an external standard by `url` need the sandbox to reach that host — use
  `https://` URLs, never an SSH host alias, which will not resolve there.

## Updating

Bump-driven, not automatic. To pick up a new version:

```
/plugin marketplace update throughline-skills
```

## Licence

Apache-2.0. © Dr Henry J Grech-Cini.
