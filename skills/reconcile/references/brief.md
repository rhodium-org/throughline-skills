# Project brief: `/tl:reconcile`

Written on 2026-10-11 from a design conversation with Henry Grech-Cini. It is
the source the skill's shaping cites; the skill's own graph, once ratified,
supersedes it on anything they disagree about.

## Mission

A fifth skill in the tl plugin that checks whether a codebase is aligned with
the throughline graph it claims to implement, and a notation that lets an agent
working under throughline cite the items its code serves, so the code carries
its own traceability and that traceability can be documented from the graph.

## Settled decisions

1. **It is a check, not a verb that aligns.** When code and graph disagree,
   either may be wrong: the code drifted from a ratified item, the item is
   out of date, or neither is clearly wrong (code nothing justifies, an item
   nothing builds). The skill reports each disagreement and asks which side
   moves. It fixes only the mechanical: a missing or malformed citation, a
   citation to a renamed UID, a stale stamp the agent has confirmed still
   holds. A ratified item is never amended to match the code without the
   human deciding so.
2. **The name is `reconcile`.** As in accounting: two records of one thing,
   compared, each difference settled on whichever side is wrong. `align` was
   rejected because it reads as the imperative to make code match. `audit` was
   rejected as read-only, `conformance` as a noun among verbs. `trace` is taken
   by `tl trace`.
3. **One skill, two halves.** The citation notation agents write while coding,
   and the reconciliation that reads it. The citations are the input to the
   check.
4. **The notation** is a comment carrying the marker `tl:`, a link type from the
   graph's own vocabulary, and a UID, optionally qualified by graph and
   stamped with the item's fingerprint:

   ```
   # tl: implements tl-challenge/REQ-0007
   # tl: verifies   tl-challenge/TEST-0007@3f9a1c
   ```

   One marker in every language's comment syntax, so one scanner serves all
   languages without a per-language parser.
5. **Deterministic checks in a standard-library script, judgement in SKILL.md**,
   as `/tl:challenge` splits them. The script reads the code and `tl dump`:
   dangling citations, live implementable items nothing cites, status the
   code contradicts (implemented with no code; code citing an unaccepted
   item), automated tests not wired to their TEST items, stale stamps, and an
   item-to-location table for generated documents. The agent reads each cited
   location against its item, and asks of uncited code whether the graph
   justifies it.
6. **Graphify is optional, never required.** A structural code graph is not
   evidence of an intended link to a requirement, and the plugin's skills
   install nothing but throughline. Where a repository already holds a code
   graph, the skill may use it to find likely implementers of an uncited
   item; otherwise grep and reading. (Graphify itself was not read for this
   brief.)
7. **It changes nothing in `tl`.** If the check proves its worth, a code scan
   in throughline itself is the upstream home, and this skill is its hand-run
   form, as `/tl:challenge` is for `throughline-challenger`.

## Open questions

- ~~Is the graph qualifier on a citation required always, or only in a
  repository holding more than one graph?~~ Answered the same day: only in a
  repository holding more than one graph. (This repository holds five, and
  `REQ-0001` exists in each.)
- Are fingerprint stamps on citations in the first version, or later?

## Evidence already in this repository

The informal form of the notation is in use: the scripts' docstrings open with
the UID they implement (`"""REQ-0002: ..."""`), the tests carry `# TEST-0001`,
and commit subjects end with `(tl-challenge REQ-0007, TEST-0007)`.
