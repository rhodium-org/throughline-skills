---
name: multigraph
description: Work in a repository that holds MORE THAN ONE throughline IDD graph — several `throughline.toml` files, wired to each other by `path` sources (an anchor graph and one graph per role or rendering, or a graph and the `<name>-shape` graph tl:shape lays beside it). Use when a repo has multiple `throughline.toml` files, when adding a graph to such a repo, when wiring one in-repo graph to borrow from another, when gating every graph, when ratifying items whose grounding chain crosses graphs, or when a merge stops on a UID collision (CONFLICT (add/add) on an item file). How composition itself works is in `tl context`; this skill covers what no single graph's brief can see. For a single-graph repo, follow the graph's own `tl context` brief instead.
user-invocable: true
---

# Several IDD graphs in one repository

A repository may hold several throughline graphs that borrow from each other:
an anchor graph describing a shared subject and a graph per role, discipline
or rendering, or simply a graph and the `<name>-shape` graph `/tl:shape` lays
beside it. Each is its own project, with its own model, UID space and
accountability. Composition lets one borrow from another; it never merges them.

**How composition works is not in this file.** Run `tl -C <graph> context` in a
graph that declares `[[sources]]` and read its composition section: declaring a
source, transitive sources and `alias`, what each command reads over the union,
the source cache, and what is edited by hand. That brief is generated from the
installed `tl` and moves with it. This skill covers only what one graph's brief
cannot see: the repository's other graphs.
<!-- tl: implements tl-multigraph/REQ-0012@d089f63d78e9 -->

## First: make sure the tool exists

<!-- tl: implements tl-multigraph/REQ-0001@01ca07a7081b -->
```sh
tl --version || pip install 'throughline>=5.2.0'
```

Needs Python ≥ 3.11 and throughline ≥ 5.2.0, the oldest release the plugin is
tested against; honour any higher floor the repository pins. Upgrade an older
`tl` with `pip install --upgrade 'throughline>=5.2.0'`: it may read these
graphs differently, or not at all. If the install fails, stop.

## Orient: find every graph, then read the one you touch

<!-- tl: implements tl-multigraph/REQ-0002@1d07d5f112ea -->
```sh
find . -name throughline.toml -not -path '*/.venv/*' -not -path '*/.git/*'
tl -C <graph> context
```

Read the brief of the graph you are about to change; it is authoritative over
this file. **Each graph has its own model**: types, statuses and link
vocabulary differ between siblings, so a brief read in one graph never
describes another.

## Wire siblings by path, standards by a pinned url

<!-- tl: implements tl-multigraph/REQ-0004@69a77b571d1b -->
Choose by **whose schedule the source moves on**:

```toml
# teams/developer/idd/throughline.toml
[[sources]]
namespace = "subject"
path = "../../../subject/idd"      # relative to this file's directory; no ref

[[sources]]
namespace = "asvs"
url = "https://github.com/rhodium-org/throughline-asvs"
ref = "v5.0.0"
```

- **An in-repo sibling moves on this programme's schedule** and changes in the
  same commit as the items that follow from it. Carry it by `path`, unpinned,
  so the check catches drift. This is the permanent wiring for a sibling, not
  only a development convenience, whatever a brief's wording suggests.
- **An external standard moves on someone else's schedule.** Pin it to a tag,
  or a clause could change meaning with no commit here to show for it.
- **Pinning an in-repo sibling is the classic mistake:** it lets a graph go on
  citing last month's description of a subject that has since changed.

<!-- tl: implements tl-multigraph/REQ-0014@18da4f8ad786 -->
**A graph that follows a standard takes its schema from it.** A source marked
`schema = true` gives the graph its item types, attributes, links, statuses and
rules; the graph's own `throughline.toml` declares only what it adds:

```toml
# glossary/throughline.toml
[[sources]]
namespace = "glossary"
url = "https://github.com/rhodium-org/throughline-glossary-standard"
ref = "v1.0.0"
schema = true

[[sources]]
namespace = "app"
path = "../idd"                    # the graph this one explains
```

- **Pin the schema source to a tag**, as any external standard: a moved
  standard would otherwise change what `tl check` demands with no commit here.
- **Two graphs in one repository may follow different standards**, or one a
  standard and the other none. Read each graph's own `tl context`: the brief of
  a graph that follows a standard is generated from that standard.
- **A graph is never laid inside another graph's root**, whatever it follows: a
  graph walks its whole subtree.

Layout convention: each graph lives in a folder named `idd/` under a directory
naming its scope — `subject/idd/`, `teams/<role>/idd/` — and a shaped graph's
reasoning sits beside it as `idd/<name>-shape/`.

## Ratify in the graph that owns the item

<!-- tl: implements tl-multigraph/REQ-0006@5a6a39e8eb89 -->
A borrowed item is never ratified from a consumer; `tl` refuses a
namespace-qualified UID (`tl: subject:UR-0003 does not exist`, exit 2). To
ratify across graphs, **go to the graph that owns each item**, one `ratify`
call per graph, in one commit if you like:

```sh
tl -C teams/developer/idd ratify SREQ-0009 --by "Ada Lovelace"
tl -C subject/idd         ratify UR-0003  --by "Ada Lovelace"
```

A local item grounded only through a sibling is judged over the union, so it
is ratified in its own graph like any other. Ratification is a human act. If
you do not know who is ratifying, **ask and use exactly what they give you** —
never invent, guess or reuse a name.

## Gate every graph

<!-- tl: implements tl-multigraph/REQ-0007@90852af829d2 -->
There is no whole-repository command. Loop over every graph, and do not let one
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

Which graphs take `--strict` is the repository's decision; read its CI
workflow rather than assuming. A graph waiting on a human's ratification
cannot pass strict.

## A merge stopped on a UID collision

Every graph allocates UIDs on its own, so two branches can collide in several
graphs at once, and the merge stops with `CONFLICT (add/add)` on each item file.
**Never settle one by picking a side**: that silently drops an item. `tl
resolve` fixes a collision inside the stopped merge, but only in the graph `-C`
names, so run it in every graph, in any order, and do not let one refusal mask
another:

<!-- tl: implements tl-multigraph/REQ-0013@6e4a9410c2d5 -->
```sh
rc=0
for cfg in $(find . -name throughline.toml -not -path '*/.venv/*'); do
  tl -C "$(dirname "$cfg")" resolve || rc=1
done
exit $rc
```

A graph with nothing to resolve says so. Where one refuses, read why: it
changes nothing and names what to do.

**A sibling's link to a moved item follows it.** A graph that sources the
resolved one names the item `namespace:UID`, and a link the moved side added
there would otherwise still name the old UID, which after the move means the
item that kept it. `resolve` rewrites those links in every graph of the
repository that sources the resolved one by `path`, whichever graph you resolve
first, and reports each as `relink <UID> in <graph>`. Read those lines: they are
the only record of which sibling items changed.

Run the `tl check` each `resolve` suggested in every graph, then commit the
merge.

## In a cloud sandbox

<!-- tl: implements tl-multigraph/REQ-0008@aab4dcb417e0 -->
A fresh sandbox holds a clone of one repository and nothing personal:

- **An SSH-alias url fails** (`git@my-alias:org/repo.git` needs a personal
  `~/.ssh/config`). Remote sources must use `https://`, and a private one
  resolves only if the session is authenticated for it.
- **The source cache starts empty**, so the first check is slow.
- **In-repo `path` sources always resolve**, a further reason to wire siblings
  by `path`.

A source that fails to resolve is an environment failure until shown
otherwise: confirm that before hunting a graph defect.

## Adding a graph to the repository

<!-- tl: implements tl-multigraph/REQ-0011@3064e76b871f -->
1. `tl -C <scope>/idd init` (or `/tl:shape`, which also records why), then
   declare its `[[sources]]`: the in-repo anchor by `path`, any external
   standard by pinned `url` and `ref`.
2. Author its roots and items, each grounded at birth with `--ground`, citing
   `namespace:UID` where the chain leaves the graph.
3. Add it to the repository's check loop and to any table of graphs.
4. Items you author enter `proposed`; hand them to a named human to ratify.
5. Cite the UIDs in the commit subject, qualified by the graph that owns them.
