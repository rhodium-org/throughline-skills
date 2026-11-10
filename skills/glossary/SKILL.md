---
name: glossary
description: Write, keep and publish a glossary of a throughline IDD graph, so a person who did not build it can ask "what is X?" and "how does it know?" and get an answer that leads back to the graph. The glossary is a graph of its own that follows throughline-glossary-standard: the concepts that recur, each with a one-line definition, why it exists, what decides how it behaves, one concrete example, other names and what it is not to be confused with, every entry stamped to the items it was written from, and rendered to docs/glossary.md the same way every time. Each concept is held once; a glossary for one audience is the subset of terms for it, reworded by a gloss where needed; and terms map onto a shared glossary, so names that differ for one concept, retired names still in use and one name with two meanings are found and put right over time. Use when asked to "generate a glossary", "explain the concepts", "what is X in this graph", "how does it know", "where does that knowledge live", "update the glossary", "a glossary for <audience>", "why do these graphs call it different things", or when a large graph's vocabulary needs explaining to someone new; and on a later run, to say what a change to the graph has touched before changing anything.
user-invocable: true
---

# A glossary of a throughline graph

A graph a person and an AI build together grows its vocabulary as the work goes,
and nobody holds all of it. Explaining it to someone new then turns into "what is
an X?" and "how does it know?". The answer exists in the graph, spread across
rationales, rules and settings. This skill gathers it into one entry per concept,
and each entry leads back to the items it came from.

The glossary is **a graph of its own**, following
[throughline-glossary-standard](https://github.com/rhodium-org/throughline-glossary-standard),
which composes the graph it explains. That gives three things:
- `tl check` holds every entry to the standard: a definition, a why, a how it
  works, an example, and at least one stamped link into the explained graph.
- A person signs each entry, as they sign any item.
- A stamp records each source as it was read, so a later change to the source
  marks the entry for review.

Each concept is held **once**, in neutral words. Who reads it is a separate
matter:
- **Audiences are items of their own** (AUD).
- **An audience's glossary is the subset of terms marked `for` it.** Nothing is
  copied.
- **A gloss rewords one term for one audience**, where the term's own words do
  not serve that reader.

A glossary also **maps its terms onto a shared glossary** (the organisation's
common vocabulary), using the SKOS matches `same_as`, `close_to`,
`broader_match` and `narrower_match`. `review` then reports where the names
disagree. Each finding is put to a person and put right in the graph that owns the
name, so the vocabulary of many graphs converges over time.

Rendering is deterministic: the same graph gives the same `docs/glossary.md`.
Only choosing the concepts and writing the entries needs judgement, and a person
signs that part.

## First: the graph, the tools and the script

```sh
find . -name throughline.toml -not -path '*/.venv/*' -not -path '*/.git/*'
tl --version || pip install 'throughline>=5.2.0'
S="${CLAUDE_PLUGIN_ROOT}/scripts/glossary.py"
python3 "$S" --help
```

The script runs `tl` from throughline 5.2.0 or later. That's the first release
whose `tl check` accepts a link declared to run outside the graph (a term's link
into the graph it explains) and that writes list attributes. On an older `tl`,
the script exits 2 and names the upgrade. If the plugin root variable is unset,
the script is at `scripts/glossary.py` beside this file's plugin.

Run `tl -C <explained graph> context` and read the brief before reading the
graph. A glossary that misreads the graph's own vocabulary (its link types, its
statuses) explains the wrong thing.

If the glossary graph already exists (a folder whose `throughline.toml` names the
glossary standard as its schema), go to **A later run**.

<!-- tl: implements tl-glossary/REQ-0003@e53584a07fb8 -->
## Lay the glossary graph down

```sh
python3 "$S" init -C <repo> --explains <explained graph root> [--at glossary] [--as app]
```

- The glossary goes in a folder of its own **beside** the graph it explains,
  never inside it or inside any other graph's root. The script refuses a place
  inside a graph.
- Where the repository holds several graphs, ask the person which the glossary
  explains. For a second explained graph, add another `[[sources]]` entry by
  `path` with its own namespace.
- `--as` is the explained graph's namespace in the glossary. Every link writes
  it (`app:REQ-0012`), so choose a short word the reader will recognise.

Where the organisation keeps a shared glossary, the glossary maps onto it. Add it
as a source, pinned, after the explained graph:

```toml
[[sources]]
namespace = "estate"
url = "https://github.com/rhodium-org/estate-glossary"
ref = "main"
```

Then make the one glossary item (what it covers), and one audience item (AUD) for
each kind of reader. Its `knows` says what that reader already knows and asks,
for example "a technical director who did not build the system and asks where
the knowledge lives". Ask the person who the readers are if it isn't obvious.

<!-- tl: implements tl-glossary/REQ-0001@e45474e9876f -->
## The first run: choose the concepts

```sh
python3 "$S" candidates -C <glossary>
```

The script lists the phrases that recur across the explained graph's titles,
texts and rationales (most-used first, with the items that use each), and the
items most linked to and from. That gives you somewhere to start reading. It
doesn't choose the concepts, and the list isn't the glossary.

Then read the graph: the central items, the rationales, the rules and settings,
and the items the candidates point to. A concept earns an entry when:

- **it recurs**: the graph uses it across several items, under one name or
  several;
- **it carries behaviour**: something in the graph decides how it behaves, and a
  newcomer would ask how the system knows;
- **a reader would stumble on it**: its everyday meaning is not the graph's
  meaning, or two names sound alike.

Don't give every item an entry. A requirement is not a concept: it is a
statement *about* concepts. A large graph gives perhaps 15 to 40 terms. Start
with the ones the audiences will ask about first.

<!-- tl: implements tl-glossary/REQ-0002@5b810bd6772c -->
## Write each entry

Each term is one item, written through `tl apply`. The fields are:

| field | what it holds | test it against |
|---|---|---|
| title | the concept's preferred name: the shared glossary's where it has the concept, else the name the graph most uses | |
| text | **one line**, in plain neutral words: what the thing *is* | Could the reader repeat it to someone else? Does it restate any single item's text? If so, rewrite it. |
| `why` | why it exists, drawn from the rationale of the items it is defined from, and how it sits beside the concepts next to it | Does it give a reason, not a description? |
| `how_it_works` | what decides how it behaves: the rules, settings, files and links, **each named as the graph names it** | Does it answer "how does it know?" with something the reader could go and look at? |
| `example` | one concrete case from the graph, in words the reader follows | Is it a case, not a restated definition? |
| `aliases` | other names in accepted use for it (a list) | |
| `deprecated_names` | names to retire (a list); every use in an explained graph is reported | Did the person agree the name is to go? |
| `local` | true when the concept is deliberately this graph's own, so no shared term should hold it (only on the person's word) | |
| `defined_from` → | the explained items that state or use the concept (at least one) | |
| `driven_by` → | the explained items that decide its behaviour: the ones `how_it_works` names | |
| `shown_by` → | the one explained item the example is taken from | |
| `distinct_from` → | the terms it may be confused with | |
| `relates` → | the terms its why or how it works names | |
| `broader` → | the term it is a kind or part of | |
| `for` → | each audience whose glossary should hold it | Would that reader ask about it? |
| `same_as`, `close_to`, `broader_match`, `narrower_match` → | the shared glossary's term it matches (stamped) | Is it the same concept, not just the same word? |

Every link into the explained graph is **stamped**: the stamp records the
target's fingerprint as you read it. Write terms with a change set, then link the
terms to each other in a second one (`tl apply` resolves link targets against the
graph as it stood before the set):

```json
{"change_set_format": 2, "operations": [
 {"op": "new", "register": "TERM", "label": "brand", "title": "Brand",
  "text": "The look an organisation gives every deck made for it.",
  "attrs": {"why": "…", "how_it_works": "…", "example": "…", "aliases": ["look"]},
  "links": [{"target": "GLS-0001", "type": "derives_from"}]},
 {"op": "link", "uid": "$brand", "target": "app:REQ-0012", "type": "defined_from", "stamp": true},
 {"op": "link", "uid": "$brand", "target": "app:CMP-0003", "type": "driven_by", "stamp": true},
 {"op": "link", "uid": "$brand", "target": "app:ED-0004", "type": "shown_by", "stamp": true}
]}
```

```sh
tl -C <glossary> apply terms.json
tl -C <glossary> apply term-links.json   # distinct_from, relates
tl -C <glossary> check
```

Everything you write is `origin: ai` and `proposed`. Never edit an item file.

**A gloss**, where a term's words don't serve one audience, is a GLOSS item:
- its text is the definition in that reader's words;
- it may reword `why`, `how_it_works` and `example`, and anything it leaves out
  is the term's own;
- it links `glosses` → the term, **stamped**, and `for` → the audience;
- there is one gloss per term per audience.

Write a gloss only where the reader would otherwise be lost. A subset of terms is
the first tool; a gloss is the second.

**The test of an entry is whether it explains.** Read it back as each audience.
If it paraphrases the requirement it came from, it adds nothing. Say what the
reader needs that no single item says: how things connect, where the knowledge
lives, what decides the behaviour.

<!-- tl: implements tl-glossary/REQ-0007@7739125cae80 -->
## Names: one concept, one entry

While reading, note where:

- **one concept goes under several names.** Propose one term, titled with the
  name the graph most uses and with the others as aliases, and ask the person
  which name should lead. Their answer, or their signature on the term, settles it.
- **one name covers two concepts.** Make two terms, each titled to tell them
  apart (`Brand (a deck's look)`, `Brand (a tenant's setting)`), linked
  `distinct_from`.

`review` also lists every name that the title or alias of more than one term
uses. Report all of these to the person as findings about the explained graph,
not only about the glossary: a name used two ways is a defect in that graph's
vocabulary.

<!-- tl: implements tl-glossary/REQ-0011@41e6e99ea9c4, tl-glossary/REQ-0012@ae21a456dea0, tl-glossary/REQ-0013@e0f2619b5609 -->
## Map onto the shared glossary, and act on what disagrees

For each term, find the shared glossary's term for the same concept, and link to
it, stamped:
- `same_as` if it is the same concept;
- `close_to` if it can stand in for it in most uses;
- `broader_match` if the shared term is broader;
- `narrower_match` if the shared term is narrower.

Match by meaning, not by spelling: two terms called "Brand" may not be one concept.
A concept the shared glossary lacks is either a new shared term (propose it there)
or deliberately local: mark it `local` only on the person's word.

`review` then reports four kinds of finding:
- **name differs:** the same concept under two preferred names;
- **no match:** a term matched to nothing there and not marked local;
- **two meanings:** one name for two concepts that aren't matched;
- **retired name:** a deprecated name still used in an explained item.

Put each finding to the person with what would put it right, and **where**:
- **a retired name still in use:** a rename in the explained graph that owns the
  item, through `tl amend` there;
- **a name that differs:** either this glossary adopts the shared name, with the
  old one as an alias or deprecated, or the shared glossary is asked to change, in
  its own repository;
- **no match:** a new term proposed in the shared glossary, or `local` here;
- **two meanings:** a rename in one graph or the other, or a match if they turn
  out to be one concept.

Change nothing until the person has answered, and then only through `tl`, in the
graph that owns the name. Never rename on your own. Each answered finding is one
step towards one vocabulary; the next run's `review` is shorter.

<!-- tl: implements tl-glossary/REQ-0008@b8b6b33a2dba, tl-glossary/REQ-0010@081b487da583 -->
## Publish

```sh
python3 "$S" render -C <glossary>                       # every term: docs/glossary.md
python3 "$S" render -C <glossary> --audience AUD-0002   # its terms, in its glosses: docs/glossary-<audience>.md
python3 "$S" render -C <glossary> --check               # exits 1 when the document is stale
```

The document holds:
- a table of the terms, then one section per term in name order;
- each term's definition, other names, why, how it works (with the items that
  decide it), example and sources, and whether it is signed;
- the terms each entry is a kind of, not to be confused with, relates to, and
  matches in other glossaries;
- an **Under review** notice on any entry whose source, or whose gloss's term,
  has moved since its stamp.

Publish one document per audience the person wants. The full one is the reference
the audience documents are subsets of.

Never edit the document. Change the graph and render it again. A repository can
put `render --check` in CI beside `tl check`.

Then hand over for signing, as the explained graph's own AGENTS.md says:
1. Name the repository, the branch and the glossary graph's root.
2. Give the line for the full-screen assistant, so the person reads each entry
   before signing it.

<!-- tl: implements tl-glossary/REQ-0004@b76040f97582, tl-glossary/REQ-0005@f6a0ae5afaf9, tl-glossary/REQ-0006@363f1c32a428 -->
## A later run: say what changed before changing anything

On a glossary that already holds terms, write **nothing** until the person has
seen what you propose.

```sh
python3 "$S" review -C <glossary>
```

`review` sorts the terms:

- **touched**: a stamped source has `moved` (its fingerprint is not the stamped
  one) or is `gone`, or a link into the explained graph is `unstamped`;
- **settled**: none of its links has moved.

**For each touched term:**
1. Read the source as it is now. `git log -p` on its item file shows what changed.
2. Decide whether the entry still holds.
3. Show the person:
   - the term as it stands;
   - what moved;
   - your proposal: no change, or the amendment, word for word.
4. Apply only the changes the person accepts.
5. Refresh a stamp (`tl -C <glossary> link <TERM> <target> --type <type> --stamp`,
   on the same pair) **only** after re-reading the term against the moved target.
   A restamp says "read again and still true"; never restamp to clear a report.

**For each settled term:** don't amend it. A settled term's sources haven't
changed, so a different wording from you is not news. Read its sources again
anyway, and compare what your fresh reading **claims** (what the thing is, why it
exists, what decides it) with what the term claims. Ignore differences of wording.

If the claims differ **materially** while nothing changed underneath, report it as
**a reading that moved without a change**:
- the term;
- its sources;
- the term's reading and your reading, side by side.

Then ask the person which it is:
1. **The term was wrong.** Propose the amendment and apply it on their word.
2. **The source is ambiguous.** It supports both readings. On their word,
   record that on the source item, in the explained graph:
   `tl -C <explained graph> flag <UID> --reason "…"`. Then propose wording for
   the term that holds under both readings, or wait for the source to be
   clarified.
3. **Your new reading is wrong.** Change nothing.

Two readings of the same unchanged text are evidence about that text. That is
the glossary's health check on the graph it explains.

**Each gloss whose term moved** (`gloss … moved`): read the term as it is now
and re-word the gloss, or confirm it still holds. Show the person, and restamp its
`glosses` link only after that. Keep one gloss per term per audience.

**Names:** act on the naming findings as **Map onto the shared glossary** says.
A shared term that moved touches every term matched to it.

**New concepts:** run `candidates` again. Propose new terms as you did on the
first run, and show each proposed entry before writing it.

Then render and hand over for signing as above.

## Answering "what is X?"

If someone asks what something in the graph is, or how the system knows
something:
1. Look for it in the glossary first (by title or alias), and answer from the
   entry, citing the items it is defined from and driven by.
2. If there is no entry, answer from the graph, then offer to add the term.
3. If the entry is under review, say so.

## Traps

- **Paraphrase is not explanation.** An entry that says what one item says, in
  other words, fails the reader. Its value is the connection across items.
- **Never restamp without re-reading.** It hides exactly the change the stamp
  exists to catch.
- **Never amend a settled term on a fresh reading alone.** Report it and ask.
  Otherwise the glossary drifts with the model, not with the graph.
- **The glossary never sits inside the graph it explains.** A graph walks its
  whole subtree, so a nested glossary would be checked as part of the explained
  graph.
- **Match by meaning, not by spelling.** The same word in two glossaries is a
  question, not an answer; `review`'s "two meanings" finding exists because of it.
- **An audience never gets its own copy of a term.** A copy would drift; a subset
  and a stamped gloss cannot.
- **`tl apply` takes a list only for a list attribute** (`aliases`,
  `deprecated_names`), and
  resolves link targets against the graph as it stood before the set.
