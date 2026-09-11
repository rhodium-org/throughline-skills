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
| `throughline-multigraph` | Repositories holding **more than one** throughline graph, composed with `tl-compose`: how to pick the right binary per graph, wire sibling graphs by `path`, gate them all, and ratify items whose grounding chain crosses graphs. |
| `throughline-challenge` | A **challenge pass** before hand-off: the twelve questions `tl check` cannot ask (link strength, prose mentions without an edge, siblings naming one thing two ways, verification per branch, untestable predicates, a rationale narrower than its family, no failure case, an item pointing at its own replacement, universal force with one mechanism, and for a composed specification: unstamped links, spec items nothing implements, a stamped target that moved), with a script for the deterministic ones. Also re-checks an **implementation graph against a specification it composes** once that specification moved: stamped links, `suspect-link` triage, and spec items nothing implements. |

Each skill activates on its own when Claude notices the situation it covers, or
you can invoke one directly as `/throughline-multigraph:throughline-multigraph`
or `/throughline-challenge:throughline-challenge`.

## Install

Two routes — both work in the terminal and at [claude.ai/code](https://claude.ai/code).

**From GitHub:**

```
/plugin marketplace add rhodium-org/throughline-skills
/plugin install throughline-multigraph@throughline-skills
/plugin install throughline-challenge@throughline-skills
```

**From the hosted catalogue** (same thing, no GitHub account needed to browse):

```
/plugin marketplace add https://iddn.uk/throughline-skill/marketplace.json
/plugin install throughline-multigraph@throughline-skills
/plugin install throughline-challenge@throughline-skills
```

In the browser you can also do it without typing commands: **Manage plugins →
Marketplaces → Add marketplace**, paste either source above, then install.

## Working on a locked-down laptop

This is designed for it. Everything runs in the Claude sandbox, not on your
machine:

- Each skill installs the CLI it needs itself (`pip install throughline-compose`,
  which brings `throughline` with it). Nothing is installed on your laptop.
- Requires Python ≥ 3.11 in the session, which cloud sessions have.
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
