# throughline-skills

Claude Code skills for working in [throughline](https://github.com/rhodium-org/throughline)
IDD requirements repositories.

Install once, and it applies in **your own repositories** — nothing needs to be
committed into them, and nothing needs installing on your laptop.

## What's in it

| Skill | What it's for |
|---|---|
| `throughline-multigraph` | Repositories holding **more than one** throughline graph, composed with `tl-compose`: how to pick the right binary per graph, wire sibling graphs by `path`, gate them all, and ratify items whose grounding chain crosses graphs. |

The skill activates on its own when Claude notices you are in such a repo, or you
can invoke it directly as `/throughline-multigraph:throughline-multigraph`.

## Install

Two routes — both work in the terminal and at [claude.ai/code](https://claude.ai/code).

**From GitHub:**

```
/plugin marketplace add rhodium-org/throughline-skills
/plugin install throughline-multigraph@throughline-skills
```

**From the hosted catalogue** (same thing, no GitHub account needed to browse):

```
/plugin marketplace add https://throughline-skill.iddn.uk/marketplace.json
/plugin install throughline-multigraph@throughline-skills
```

In the browser you can also do it without typing commands: **Manage plugins →
Marketplaces → Add marketplace**, paste either source above, then install.

## Working on a locked-down laptop

This is designed for it. Everything runs in the Claude sandbox, not on your
machine:

- The skill installs the CLI it needs itself (`pip install throughline-compose`,
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
