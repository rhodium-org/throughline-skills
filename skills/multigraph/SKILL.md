---
name: multigraph
description: Manage a repository that holds MORE THAN ONE throughline IDD graph — several `throughline.toml` files composed together with `tl-compose` (e.g. an anchor graph describing the shared subject, plus one graph per role, discipline, brand or rendering). Use when a repo has multiple `throughline.toml` files, when adding a new graph to such a repo, when wiring one in-repo graph to borrow from another via a `path` source, when a check passes in one graph but the seam to a sibling is broken, or when ratifying items whose grounding chain crosses graphs. For a single-graph repo, follow the graph's own `tl-compose context` brief instead.
user-invocable: true
---

# Multiple IDD graphs in one repository

A repo may hold several independent throughline graphs that cite each other — an
*anchor* graph describing the shared subject, plus a graph per role, discipline,
brand or rendering. Each graph is a separate project with its own
`throughline.toml`, its own UID space and its own accountability. `tl-compose`
lets one borrow from another; it never merges them.

A typical shape, used throughout this skill:

```
your-repo/
  subject/idd/            # the anchor — the shared subject, borrowed by the rest
  teams/developer/idd/    # one graph per role/discipline/rendering
  teams/tester/idd/
```

## First: make sure the tools exist

A fresh cloud session (claude.ai) starts with neither CLI installed. One install
brings both — `throughline-compose` depends on `throughline`:

```sh
tl-compose --version || pip install throughline-compose
tl-compose --version      # e.g. tl-compose 0.12.0 (throughline 1.13.2)
```

Needs Python ≥ 3.11. If the repo pins a floor, honour it. Never carry on with a
bare `tl` because `tl-compose` failed to install — see the binary rule below.

## Orient first

```sh
find . -name throughline.toml -not -path '*/.venv/*' -not -path '*/.git/*'
```

Then run `tl-compose -C <graph> context` in the graph you are about to touch. The
brief is generated from that graph's live config and is authoritative over this
file. **Each graph has its own model** — types, statuses and link vocabulary
differ between siblings, so a brief read in one graph does not describe another.

## The binary rule — the easiest thing to get wrong

Any graph whose `throughline.toml` declares `[[sources]]` **must** be driven with
`tl-compose`. A graph with none takes bare `tl`. Decide per graph, never per
directory pattern:

```sh
grep -q '^\[\[sources\]\]' <graph>/throughline.toml && echo tl-compose || echo tl
```

Bare `tl` on a sourced graph does not know what `subject:UR-0001` means. It
reports on the local items alone — so it can **look green while the seam to the
sibling graph is broken**. "This graph adopts no external standard" and "this
graph needs no composition" are not the same statement: a graph that borrows only
from an in-repo sibling still has a source, and still needs `tl-compose`.

## Layout and wiring

Convention: each graph lives in a folder named `idd/`, under a directory naming
its scope — `subject/idd/`, `teams/<role>/idd/`, `brands/<brand>/<asset>/idd/`.

A `path` source is resolved **relative to the directory containing
`throughline.toml`**:

```toml
# teams/developer/idd/throughline.toml
[[sources]]
namespace = "subject"
path = "../../../subject/idd"      # -> <repo>/subject/idd

[[sources]]
namespace = "asvs"
url = "https://github.com/rhodium-org/throughline-asvs"
ref = "v5.0.0"
```

**Choose `path` vs `url`+`ref` by whose schedule the source moves on.** An in-repo
sibling moves on *this* programme's schedule and should change in the same commit
as the items that follow from the change — carry it by `path`, unpinned, so the
citation catches drift. An external standard moves on someone else's schedule —
pin it to a tag, or a clause could change meaning with no commit here to show for
it. Pinning an in-repo sibling is the classic mistake: it lets a graph go on
citing last month's description of a subject that has since changed.

Borrowed items are referenced `namespace:UID`; a bare UID is always local.
Composition is **one level deep** — if a sibling you adopt itself cites another
namespace, declare that namespace too, or have the sibling `reexport` it:

```toml
[[sources]]
namespace = "subject"
path = "../../../subject/idd"
reexport = ["plain", "wcag"]
```

Adopting a source costs the `[[sources]]` block and **nothing else** — never copy
a sibling's types, statuses or link vocabulary into your `throughline.toml`.
Copied declarations are inert and wrong the moment the source moves.

## Ratifying across graphs — what `tl-compose ratify` does and does not do

`tl-compose ratify` **cannot ratify an item in another graph.** A namespace-
qualified UID is refused before anything is written:

```
$ tl-compose -C teams/developer/idd ratify subject:UR-0003 --by "Ada Lovelace"
tl-compose: subject:UR-0003 does not exist          # exit 2
```

A source is read-only. Composition gives a wider *view*, never a wider
*authority* — a borrowed item is never edited, restatused or ratified by a
consumer, because its own graph owns its accountability record. Naming
`namespace:UID` as the item a writing command acts on is a mistake, not a
shortcut; it appears in a write only as a link target, as when `--ground` cites it.

**What `tl-compose ratify` actually buys you** is the reason to use it here: it
hands core's accountability gate the *union* as its grounding view. A human may
only ratify a grounded item, and bare `tl ratify` judges grounding over the local
graph alone — so it **wrongly refuses** a local item whose grounding chain reaches
a root only through a sibling graph (`subject:UR-0001` reads as unresolved and the
item looks orphaned). `tl-compose ratify` resolves the sources, judges the item
against the union, and writes the record to the consumer's own register.

So to ratify across a multi-graph repo, **go to the graph that owns each item**:

```sh
tl-compose -C teams/developer/idd ratify SREQ-0009 --by "Ada Lovelace"
tl-compose -C subject/idd         ratify UR-0003  --by "Ada Lovelace"
```

One commit may carry ratifications in several graphs — that is normal, and is
what a cross-graph review looks like. It is still one `ratify` call per graph.

Ratification is a human act. If you do not know who is ratifying, **ask and use
exactly what they give you** — never invent, guess or reuse a name. A fabricated
`ratified_by` is a false accountability record, the one thing this toolchain
exists to prevent. `tl-ratify` (the curses cockpit) is compose-aware and grounds
over the union if the human prefers to work interactively.

## Gate every graph

There is no whole-repo command. Loop, choosing the binary per graph, and do not
let one failure mask another:

```sh
rc=0
for cfg in $(find . -name throughline.toml -not -path '*/.venv/*'); do
  graph="$(dirname "$cfg")"
  grep -q '^\[\[sources\]\]' "$cfg" && bin=tl-compose || bin=tl
  echo "::group::$bin -C $graph check"
  "$bin" -C "$graph" check || rc=1
  echo "::endgroup::"
done
exit $rc
```

Which graphs take `--strict` is a per-repo decision: the graph that gates the
build usually does, while graphs deliberately left awaiting human ratification do
not. Check the repo's CI workflow rather than assuming.

## Working remotely (claude.ai cloud sessions)

The session runs in a fresh sandbox holding a clone of one repo. That changes
three things:

- **In-repo `path` sources always work; remote sources may not.** A `path` source
  is inside the clone — no network, no auth, no cache. This is a further reason
  to wire sibling graphs by `path` rather than by pinned URL.
- **An SSH-alias source will fail.** A `[[sources]]` `url` like
  `git@my-alias:org/repo.git` relies on a host alias in a personal
  `~/.ssh/config`, which does not exist in the sandbox. Remote sources must use
  `https://` URLs, and a private one is only reachable if the session is
  authenticated for it. If a check fails to resolve a source, confirm this before
  hunting for a graph defect — it is an environment failure, not a finding.
- **The source cache starts empty.** The first `check` re-fetches every remote
  source, so it is slow but always current — the moved-tag staleness trap below
  cannot fire in a fresh session, only on a warm machine running compose below
  0.16.1.

To spare every user the install step, a repo can bootstrap the CLI itself with a
`SessionStart` hook in `.claude/settings.json` running `pip install
throughline-compose`. Keep this skill's own check anyway; a hook may be absent.

## Traps

- **A moved git tag is only picked up from compose 0.16.1.** From that release a
  cached source whose `ref` is a tag or branch is checked against its origin before
  reuse and refetched if it moved; a commit-id ref costs no network call. **Below
  0.16.1 a moved tag is never refetched and you get a silent stale-content pass** —
  bump the `ref` or `rm -rf ~/.cache/throughline-compose/sources/…@<ref>`. Check
  with `tl-compose --version` before trusting either behaviour. `path` sources are
  read live and are not affected.
- **`query`/`ls` only became union-aware in compose 0.12.0.** On 0.11.0 and
  earlier they answer over local items only, while `check` composes — so a listing
  can disagree with a check in the same graph. Confirm with `tl-compose --version`
  before trusting a listing. A fresh `pip install` gets 0.12.0+; a developer
  machine may be older, or installed *editable*, in which case the version string
  describes the last release rather than the code being run.
- **Grounding percentages in the check headline** counted the whole union under
  the consumer's schema before 0.11.0, which made the figure misleading on
  borrowed items. Exit codes were always correct.
- **Structure changes go through the CLI** — `tl-compose new`/`link`/`amend`/
  `ratify`. Never hand-edit a `<UID>.yml` or a `.register.yml`. `[[sources]]` is
  the one thing you hand-edit, because it is config, not graph.

## Adding a graph to the repo

1. `tl-compose -C <scope>/idd init`, then declare the `[[sources]]` it borrows
   from — normally the in-repo anchor by `path`, plus any external standard by
   pinned `url`+`ref`.
2. Author the graph's own roots and items; ground each at birth with `--ground`,
   citing `namespace:UID` where the chain leaves the graph.
3. Add it to the repo's check loop and to any `AGENTS.md` table of graphs.
4. Items you author enter `proposed`; hand off to a named human to ratify.
5. Cite the UID(s) in the commit message, qualified by the graph that owns them.
