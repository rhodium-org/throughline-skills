## Citing the graph in code

This repository holds several throughline graphs. When you write or change
code, cite the graph items it serves at the time you write it, in a comment
line directly above the function, class, test or block that realises the
item: the marker tl:, a link type from the graph's vocabulary (implements or
satisfies for code, verifies for tests), then the item references,
comma-separated. Every reference names its graph's project name, as in
`# tl: implements tl-reconcile/REQ-0042`; a borrowed item keeps its
namespace, as in `tl-challenge/challenger:REQ-0001`. Never cite in a file
header. End each commit subject with the graph and UIDs it serves, as in
(tl-reconcile REQ-0042, TEST-0042).

Every citation here carries a stamp of its item's fingerprint. After you
have read the item against the code, write the stamp with
`python3 scripts/reconcile.py -C . restamp <graph>/<UID>`, never by hand,
then run `python3 scripts/reconcile.py -C . scan` and expect no findings.

| Graph root | Project name |
|---|---|
| `idd` | `throughline-skills` |
| `skills/assess/idd` | `tl-assess` |
| `skills/challenge/idd` | `tl-challenge` |
| `skills/multigraph/idd` | `tl-multigraph` |
| `skills/reconcile/idd/skill` | `tl-reconcile` |
| `skills/reconcile/idd/skill-shape` | `tl-reconcile-shape` |
| `skills/shape/idd/skill` | `skill` |
| `skills/shape/idd/skill-shape` | `skill-shape` |
