---
name: multigraph
description: Manage a repository that holds MORE THAN ONE throughline IDD graph — several `throughline.toml` files composed together (e.g. an anchor graph describing the shared subject, plus one graph per role, discipline, brand or rendering). Use when a repo has multiple `throughline.toml` files, when adding a new graph to such a repo, when wiring one in-repo graph to borrow from another via a `path` source, when a check passes in one graph but the seam to a sibling is broken, or when ratifying items whose grounding chain crosses graphs. For a single-graph repo, follow the graph's own `tl context` brief instead.
user-invocable: true
---

# Multiple IDD graphs in one repository

A repo may hold several independent throughline graphs that cite each other — an
*anchor* graph describing the shared subject, plus a graph per role, discipline,
brand or rendering. Each graph is a separate project with its own
`throughline.toml`, its own UID space and its own accountability. Composition
lets one borrow from another; it never merges them.

A typical shape, used throughout this skill:

```
your-repo/
  subject/idd/            # the anchor — the shared subject, borrowed by the rest
  teams/developer/idd/    # one graph per role/discipline/rendering
  teams/tester/idd/
```

## First: make sure the tool exists

A fresh cloud session (claude.ai) starts without the CLI. One install brings it:

```sh
tl --version || pip install 'throughline>=3.11.0'
tl --version      # e.g. tl 3.12.0
```

Needs Python ≥ 3.11 and throughline ≥ 3.11.0, the release from which `tl`
composes a graph's sources itself. If the repo pins a higher floor, honour it.
If `tl --version` reports an older release, upgrade it with
`pip install --upgrade 'throughline>=3.11.0'`: an older `tl` reads a sourced graph
without its sources and reports every `namespace:UID` link as
`namespace-unresolved`, whether the sibling item is intact or gone. If the
install fails, stop; never carry on with an older `tl`.

## Orient first

```sh
find . -name throughline.toml -not -path '*/.venv/*' -not -path '*/.git/*'
```

Then run `tl -C <graph> context` in the graph you are about to touch. The
brief is generated from that graph's live config and is authoritative over this
file. **Each graph has its own model** — types, statuses and link vocabulary
differ between siblings, so a brief read in one graph does not describe another.

## One command drives every graph

Every graph, sourced or not, is driven with `tl`; nothing is chosen per graph.
In a graph whose `throughline.toml` declares `[[sources]]`, `check`, `query`/`ls`,
`dump`, `docs`, `trace`, `subgraph`, `new`, `link`, `unlink`, `ratify`, `migrate`
and `context` answer over the union of the graph and its sources; every other
command reads the graph alone.

A check composes, so it sees the seam: while the sibling items a graph cites are
intact it passes, and once one is tombstoned it fails with `deleted-link-target`
naming the `namespace:UID` link. A graph that borrows only from an in-repo
sibling is a sourced graph like any other.

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
**A source's own sources come with it, to any depth.** If a sibling you adopt
itself cites another namespace, that namespace is composed too, under the label
the sibling gave it, and your items may cite it by that label without declaring
it; the check summary names the path that carried it in (`wcag … via subject`).
Declaring the same source yourself as well binds it once. Your one lever over a
transitive label is `alias`, on the declared source that carries it:

```toml
[[sources]]
namespace = "subject"
path = "../../../subject/idd"
alias = { wcag = "wcag-2" }        # subject's `wcag` binds here as `wcag-2`
```

The `reexport` key is withdrawn, and `tl` refuses it in your own
`throughline.toml`.

Adopting a source costs the `[[sources]]` block and **nothing else** — never copy
a sibling's types, statuses or link vocabulary into your `throughline.toml`.
Copied declarations are inert and wrong the moment the source moves.

## Ratifying across graphs — what `tl ratify` does and does not do

`tl ratify` **cannot ratify an item in another graph.** A namespace-qualified
UID is refused before anything is written:

```
$ tl -C teams/developer/idd ratify subject:UR-0003 --by "Ada Lovelace"
tl: subject:UR-0003 does not exist          # exit 2
```

A source is read-only. Composition gives a wider *view*, never a wider
*authority* — a borrowed item is never edited, restatused or ratified by a
consumer, because its own graph owns its accountability record. Naming
`namespace:UID` as the item a writing command acts on is a mistake, not a
shortcut; it appears in a write only as a link target, as when `--ground` cites it.

**What `tl ratify` does over a sourced graph** is judge grounding over the
union. A human may only ratify a grounded item, and a local item whose grounding
chain reaches a root only through a sibling graph is grounded in the union, not
in the local graph alone. `tl ratify` resolves the sources, judges the item
against the union, and writes the record to the consumer's own register.

So to ratify across a multi-graph repo, **go to the graph that owns each item**:

```sh
tl -C teams/developer/idd ratify SREQ-0009 --by "Ada Lovelace"
tl -C subject/idd         ratify UR-0003  --by "Ada Lovelace"
```

One commit may carry ratifications in several graphs — that is normal, and is
what a cross-graph review looks like. It is still one `ratify` call per graph.

Ratification is a human act. If you do not know who is ratifying, **ask and use
exactly what they give you** — never invent, guess or reuse a name. A fabricated
`ratified_by` is a false accountability record, the one thing this toolchain
exists to prevent. `tl-ratify` (the curses cockpit) also grounds over the union
if the human prefers to work interactively.

## Gate every graph

There is no whole-repo command. Loop over every graph, and do not let one
failure mask another:

```sh
rc=0
for cfg in $(find . -name throughline.toml -not -path '*/.venv/*'); do
  graph="$(dirname "$cfg")"
  echo "::group::tl -C $graph check"
  tl -C "$graph" check || rc=1
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
- **The source cache starts empty.** The first `check` fetches every remote
  source, so it is slow but current.

To spare every user the install step, a repo can bootstrap the CLI itself with a
`SessionStart` hook in `.claude/settings.json` running
`pip install 'throughline>=3.11.0'`. Keep this skill's own check anyway; a hook
may be absent.

## Traps

- **The source cache refetches only what moved.** A remote source is fetched
  once into a per-user cache (`~/.cache/throughline/sources/`, or `$TL_CACHE`)
  and reached again only when its tag or branch has moved; a commit-id ref costs
  no network call, and `TL_OFFLINE=1` composes from the cache alone. `path`
  sources are read live.
- **A listing is not a check.** `query`, `ls` and `dump` in a consumer list the
  borrowed items beside the local ones; `--local` narrows them to the graph's
  own. Only `check` gates the seam.
- **Structure changes go through the CLI** — `tl new`/`link`/`amend`/`ratify`.
  Never hand-edit a `<UID>.yml` or a `.register.yml`. `[[sources]]` is the one
  thing you hand-edit, because it is config, not graph.

## Adding a graph to the repo

1. `tl -C <scope>/idd init`, then declare the `[[sources]]` it borrows
   from — normally the in-repo anchor by `path`, plus any external standard by
   pinned `url`+`ref`.
2. Author the graph's own roots and items; ground each at birth with `--ground`,
   citing `namespace:UID` where the chain leaves the graph.
3. Add it to the repo's check loop and to any `AGENTS.md` table of graphs.
4. Items you author enter `proposed`; hand off to a named human to ratify.
5. Cite the UID(s) in the commit message, qualified by the graph that owns them.
