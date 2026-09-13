# Assessment: tl-challenge-skill

The tl:challenge skill: the hand-run challenge pass over a graph before hand-off and against a moved specification, composing the throughline-challenger graph at a pinned tag, built 9 to 13 September 2026.

Recorded 2026-09-13T18:49:12+00:00 from `/home/henry/Projects/01-applications/throughline-skills/skills/challenge/idd`.

## Measured

| Measure | Value |
|---|---|
| Items in the graph (local, live) | 11 of 13 |
| Accepted (ratified, implemented or verified) | 11 (1.0) |
| Origin | ai 13 |
| Ratified by | Henry Grech-Cini 11 |
| Sources composed | challenger (25 items) |
| Links into sources | 12 (12 stamped, 0 not) |
| Tests by method | automated 2, document 3, manual 1 |
| Git scope | skills/challenge, scripts/challenge.py |
| Commits | 10 over 1.89 days, 0 tags |
| Commits naming an item | 10 (1.0) |
| Items amended after ratification | 2 of 11 |
| Lines added / removed | 1094 / 23 |
| Generated documents | 0 files, 0 words, current |
| Test files | 0 |
| Sessions | 1 |
| Wall clock / active | 47.1 h / 3.2 h |
| Human turns / AI turns | 30 / 438 |
| Tool calls / API calls | 161 / 438 |
| Tokens out | 619,243 (thinking 285,474) |
| Tokens in (fresh / cache written / cache read) | 11,436 / 3,196,772 / 119,829,241 |
| Done | yes |
| Measured at commit | ebd0c54f4e41 |
| Source pins | challenger v0.4.0 |
| Tools | tl: tl 3.0.0; tl-compose: tl-compose 0.16.4 (throughline 3.0.0); tl-ratify: tl-ratify 0.7.0 (throughline-compose 0.16.4, throughline 3.0.0) |
| Skill | tl:assess 1.3.0 at ebd0c54f4e41, Python 3.12.3 |

## What was built

The `tl:challenge` skill in the throughline-skills plugin: a skill text that puts the twelve challenges of the throughline-challenger to a graph, nine before a hand-off and three against a specification that has moved, with a report shape and a fix rule; a standard-library script that runs the deterministic ones from a dump (mentions, universal, verification, failure-case, untestable, replacement, unstamped, uncovered, and the siblings listing the reader works from); and a graph of eleven live items (one intent, five requirements, five tests) that composes the challenger's own graph at a pinned tag with a stamped `implements` link per challenge, so a move in the tool's specification shows up here as a suspect link. Two more items were tombstoned when the moved-specification challenges were taken out of the skill and put into the tool where they belong. The skill has no fixture tests of its own; two of its test items are automated by running the script in a clean interpreter, three are document checks and one is manual. The plugin went from `throughline-challenge` 0.1.0 on 9 September to `tl` 1.0.0 with the short name on 11 September, then 1.1.1, and is 1.3.0 today. The measured session is the one from 17:21 UTC on 11 September to 16:28 UTC on 13 September in which the skill was restructured, renamed, installed, run on real graphs and fixed; it also built the skills.iddn.uk host, added edges to the crookham graph and fixed a stamp defect in throughline itself, so its numbers overstate this work, and its wall clock spans two nights. Three sessions are excluded: the crookham session of 9 September that first added the plugin (two commits), the multigraph session of 13 September that reworded REQ-0003 twice (four of the ten commits in scope), and the shape session of 13 September that found the verification view's fault; none was dominated by this work.

## Defects found after the first "done"

The first done was commit 86b4a1f on 9 September at 20:06 BST: the plugin added to the marketplace and mirrored to the hosted catalogue, never installed.

| Defect | Found by | Would a gate have caught it? | Which |
|---|---|---|---|
| The skill's graph restated the tool's behaviour: eleven items of its own, refinements of two challenges hidden in REQ-0001, and the moved-specification challenges held here rather than in the challenger | Henry, reading the ratify command: "why does it add eleven items of its own" | No, an ownership judgement | The three challenges moved into the challenger (REQ-0010 to REQ-0012), the refinements folded into its REQ-0002 and REQ-0009, the skill's graph cut to what is true of the skill, 3ce9f3e; REQ-0004 and TEST-0004 tombstoned |
| A second clone of the skills repository under another directory left it unclear which graph the ratify command meant | Henry | No | The clone deleted |
| The hosted catalogue entry was a relative path a URL marketplace cannot resolve, so the first install from iddn.uk failed | The AI, installing the plugin | No, found by use | A git-subdir source, 6b43e71; then one plugin with a plain URL |
| The 0.2.1 bump wrote a literal backslash-n into three catalogue manifests; the validator failed and a pipe masked its exit, and the broken file was pushed | The AI, reading the output after the push | Yes, the plugin validator did, and its exit was piped past | Repaired, e8db833 |
| A UID that opens a sentence was classed as a path mention, because an empty preceding character is a member of every string | The AI, running the pass on its own iddn.uk items | No | 4fc6546, challenger REQ-0002 and TEST-0003 amended first |
| The invocation `throughline-challenger:throughline-challenger` was too long to type | Henry: "far too long winded to run a skill" | No | One plugin `tl` with short names, 4e750b7 |
| The skills page was linked from nowhere on iddn.uk, so the marketplace appeared not to exist | Henry: "I see nothing in the iddn.uk catalogue" | No | skills.iddn.uk as its own host, iddn.uk REQ-0044 |
| Run in a session with no graph on disk, the skill reviewed a proposal in chat under the challenge numbers | Henry, running it in another session | No, and now a rule: the skill stops | 8accc60, REQ-0006 and TEST-0006 |
| The report handed the ratifier "Part A" and "Part B", labels that exist only in the skill file | Henry, in the multigraph session: "as if the user knows what that is" | No | cf4e7ab, REQ-0003 |
| The fix step told the agent to record the pass's history in the rationale and said nothing about the text, so every amended item grew by a quarter to a third | Henry, noticing the drift; the AI measured it | No | 22b1fd9, REQ-0003 rewritten |
| A "dropped suspect-link finding" reported as a tool defect was the AI's own `tail -12` cutting the first line | The AI, reproducing it on review | No | Memory corrected |
| `tl link --stamp` on an existing pair added a second link instead of refreshing the stamp | The AI, running the moved-specification pass on the skill's own stamps | No, a tool defect | throughline#36; the skill carries unlink-then-relink until it is released |
| "machine-readable" tripped the vague-word list, and a path mention named only the local item carrying a UID | The AI, on review of the crookham run | No | 1ebe943, challenger REQ-0002 and REQ-0005 |
| The per-requirement verification view reports every leaf branch as untested, because the walk ignores tests that verify the head itself | The AI, running the pass on the shape skill's graph | No | Open, being fixed in another session |

Fourteen defects: seven found by Henry using the thing, seven by the AI reading its own output, one of which a gate had caught and a pipe had masked. Three of the seven human findings are about names and where things live, which no gate reads.

## What the graph caught before a person did

- The challenger's own prose-mention check found the rationale of its new REQ-0012 naming REQ-0008 with no edge, an hour after the AI wrote it.
- The moved-specification pass on the skill's own stamps found the stale stamps at each repin: REQ-0002 and REQ-0009 at v0.2.0, one at v0.3.0, one at v0.4.0, each time exactly the items whose wording had moved upstream.
- The strict gate held REQ-0003 as ratified-stale twice on 13 September, so each rewording of the report and fix rules went back to Henry rather than drifting.
- Run over the iddn.uk items before hand-off, the pass found REQ-0036 naming REQ-0044 with no edge and REQ-0040's rationale describing a deployment that no longer existed; the same run exposed the sentence-opening bug in the script.
- Run over the crookham implementation, it raised six questions for the ratifier, two of them universal-force findings on decisions, and the AI changed none of them.

## Human effort

Thirty turns in the measured session, of which about a third were the host and the other graphs. On the skill: the question of what shape the challenger should take; the instruction to make the tool public and compose it; the ratify-together request; the two questions that exposed the ownership fault and the decision to move the moved-specification challenges into the tool; the request to explain and then do the path-token fix; the objection to the long invocation and the choice of the name `tl`; the report that the skill had reviewed prose with no graph and the instruction to fix it; the review request on 13 September; and eight ratification sittings, of which five were for this graph or the challenger it composes. In the excluded multigraph session, two more corrections of the report and fix rules and two re-ratifications. The decisions only he made: one plugin, the name, what the skill owns and what the tool owns, that a skill stops when there is no graph, and that a fix rewrites rather than appends.

## Verdict

Cost: 3.2 active hours over 47 of wall clock in a session that also built a host and touched two other graphs, 619 thousand output tokens, 161 tool calls, 30 human turns, ten ratification sittings across two sessions, and two of eleven items amended after ratification, for a skill text, a script, a graph of eleven items with twelve stamped links into the tool's, and three plugin versions. Return: the stamps found every upstream wording that moved at three repins; the challenger checked its own author within the hour; the pass, run on four real graphs, produced findings a human judged and one bug in itself; and the report and fix rules were corrected under signature rather than around it. Against that: seven of fourteen defects were found by Henry using the thing, the skill's own text has no automated test, and the script's verification view was wrong for two days with no test to notice. Judgement: the graph earned its keep here on the seam to the tool it composes, where the stamps did what no reader would have, and spent an evening on ownership that a single graph would never have needed; whether that evening bought anything is the question the next moved specification will answer.
