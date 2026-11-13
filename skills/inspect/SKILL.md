---
name: inspect
description: Show one item of a throughline IDD graph with everything it rests on and everything that rests on it, across every graph in the repository, as a page a person can read and tick through - a box for each item, a dialog with the item's whole wording, links, stamps and signer, and a tick box to keep count of what has been read. Use when asked to "inspect" an item, to "show the blast", "show the trace", "draw the blast radius", "what does this rest on", "what would changing this disturb", to "see it as a graph", or when a person is about to sign an item or a change and needs the surrounding items in front of them. `tl trace` and `tl blast` print lists inside one graph; this draws both, joined across graphs, with the items themselves.
user-invocable: true
---

# Inspect an item of a throughline graph

`tl trace` prints what an item rests on and `tl blast` what rests on it, each as
a list and each inside one graph. A person deciding whether to sign an item, or
what a change to it would disturb, needs more than the list: the items
themselves, the ones in other graphs of the repository, and whether the links
between graphs still hold.

This skill draws that. A script reads every graph the item's graph is joined to
and writes one page: the item in the middle, what it rests on above, what rests
on it below, a dialog on every box with the item's whole content, and a tick
box on each to keep count of what has been read.

## First: is there a graph, and which item?

```sh
find . -name throughline.toml -not -path '*/.venv/*' -not -path '*/.git/*'
```

If that finds nothing there is nothing to inspect: say so and stop. Otherwise
you need the graph root (the folder holding `throughline.toml`) and a UID in
it. If the person named a test, a component or a line of code, find the item
it stands for first (`tl -C <root> query`, or the `tl:` citation above the
code) and say which item you chose and why.

## Build the view
<!-- tl: implements tl-inspect/REQ-0001@012865cd6da8, tl-inspect/REQ-0008@dc37b2291c1d -->

```sh
tl --version || pip install 'throughline>=5.2.0'
S="${CLAUDE_PLUGIN_ROOT}/scripts/inspect_graph.py"
python3 "$S" -C <graph root> <UID>
```

That prints a summary: the item, what it rests on, what rests on it, the links
out of a graph whose stamp is stale or missing, and each graph's `tl check`
result. Read it before drawing anything; it tells you how big the view is.

The script reads `tl dump` for the item's graph and for every graph under the
repository joined to it by `path` sources, in either direction, so an item in
a specification shows the items of an implementation graph that rest on it.
It needs throughline 5.2.0 or later and nothing beyond the standard library,
and it changes no file of any graph. If the plugin root variable is unset, the
script sits at `scripts/inspect_graph.py` beside this file's plugin.

## How far it follows
<!-- tl: implements tl-inspect/REQ-0010@0b22a0ece1da -->

By default the view follows two links each way, and says how many items lie
beyond. The whole blast of a root item can be most of a repository; a hundred
boxes is a list again, not a picture.

- Keep the default when the person wants to read and tick through.
- Use `--depth 1` for the item and its immediate neighbours only.
- Use `--depth 0` when they need every item, and say how many that is first.

Always tell the person what the count beyond the depth is. Never describe a
bounded view as the whole blast.

## Show the page
<!-- tl: implements tl-inspect/REQ-0005@29bb2a9376a5, tl-inspect/REQ-0002@20a6c4cd589b -->

Write the page with the script and show that. Do not draw the graph yourself
and do not retype item text into a picture: the script fills the page from the
dumps, so every word in a dialog is the graph's.

```sh
python3 "$S" -C <graph root> <UID> --html <file>.html      # a page in one file
python3 "$S" -C <graph root> <UID> --fragment -            # its body, to show inline
python3 "$S" -C <graph root> <UID> --json -                # the view as data
```

- Where the session can show HTML inline (a widget or an artifact), pass it
  the fragment as it is.
- Otherwise write the page to a file the person can open and give them its
  path. It is one file, loads nothing from any host, and works offline.

The page shows, for each item: its graph, UID, type and status; the title,
text and rationale in full; its attributes; each link with the state of its
stamp; and who signed it. A box with a dashed edge belongs to another graph. A
dot marks an item nobody has signed.

## What the stamps tell you
<!-- tl: implements tl-inspect/REQ-0003@2a1304661a64 -->

A link that leaves its graph should carry a stamp of the item it points at.

| State | Meaning | What to do |
|---|---|---|
| current | the target has not changed since the link was stamped | nothing |
| stale | the target was reworded after the stamp was written | read the item against the new wording before anyone signs it |
| unstamped | the link leaves its graph with no stamp | a change to the target will not mark this item; stamp it with `tl link SRC DST --type T --stamp` |

Report stale and unstamped links to the person with the view. They are the
part of a blast that `tl check` in one graph cannot see.

## Ticks are not signatures
<!-- tl: implements tl-inspect/REQ-0007@3a0b88ca363c -->

A tick records that a person has read an item. It writes nothing to disk and
signs nothing. For ticked items that nobody has signed, the page prints the
command a person would run, one line for each graph:

```sh
tl -C <graph root> ratify <UID> <UID>
```

Never run `tl ratify` yourself, whatever is ticked: a person signs. When you
hand the command over, give the repository, the branch checked out at that
path, and the graph root, so the signature lands where it is meant to.

## What to say with the view

Give the person, in a few lines beside the page:

- the item, and how many items it rests on and how many rest on it;
- how many more lie beyond the depth, if any;
- which items nobody has signed, since those are the ones awaiting them;
- any stale or unstamped link, and any graph whose `tl check` reports errors;
- anything you noticed reading the items that a program cannot check, such as
  a source that does not say what the item resting on it claims. Say it as
  your reading, and name the item.

For the questions `tl check` cannot ask of a whole graph, use `/tl:challenge`;
for code against the graph, `/tl:reconcile`.
