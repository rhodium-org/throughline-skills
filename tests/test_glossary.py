"""Tests for the glossary skill's script.

tl-glossary TEST-0001 to TEST-0004 and TEST-0007 to TEST-0009; TEST-0005 and
TEST-0006 are inspections of SKILL.md. Most tests feed the script a saved dump, so
they need neither tl nor the network. The two that prove tl check accepts what the
skill writes need tl from throughline 5.2.0 or later and the glossary standard: a
checkout named by GLOSSARY_STANDARD, else the tagged repository.
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPTS / "glossary.py"
sys.path.insert(0, str(SCRIPTS))
import glossary  # noqa: E402

STANDARD = os.environ.get("GLOSSARY_STANDARD", glossary.STANDARD_URL)


def run(*args, cwd=None, path=None, ok=True):
    env = dict(os.environ, PATH=path) if path else None
    r = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], cwd=cwd, env=env,
                       text=True, capture_output=True)
    if ok:
        assert r.returncode == 0, r.stdout + r.stderr
    return r


def tl_at_least(version):
    if shutil.which("tl") is None:
        return False
    said = subprocess.run(["tl", "--version"], capture_output=True, text=True).stdout
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", said)
    return bool(m) and tuple(int(g) for g in m.groups()) >= version


needs_tl = pytest.mark.skipif(not tl_at_least(glossary.FLOOR),
                              reason="needs tl from throughline 5.2.0 or later")


# ── a saved dump ────────────────────────────────────────────────────────────

def explained(uid, title, text="", links=(), fp=None):
    return {"uid": f"app:{uid}", "type": "requirement", "status": "proposed",
            "title": title, "text": text, "links": [{"target": f"app:{t}", "type": "implements"}
                                                    for t in links],
            "attrs": {}, "fingerprint": fp or f"sha256:{uid}"}


def term(uid, title, text, links, **attrs):
    return {"uid": uid, "type": "term", "status": "proposed", "title": title, "text": text,
            "links": [{"target": "GLS-0001", "type": "derives_from"}] + [
                dict({"target": t, "type": k}, **({"stamp": s} if s else {}))
                for k, t, s in links],
            "attrs": attrs}


def saved(tmp_path, items, name="dump.json"):
    data = {"config": {"sources": [{"namespace": "glossary", "schema": True},
                                   {"namespace": "app", "path": "../idd"},
                                   {"namespace": "estate", "path": "../estate"}]},
            "schema_source": {"namespace": "glossary"},
            "items": [{"uid": "GLS-0001", "type": "glossary", "status": "proposed",
                       "title": "The deck maker's concepts", "text": "What the deck maker means.",
                       "attrs": {"audience": "A technical director who did not build it."},
                       "links": []}] + items}
    f = tmp_path / name
    f.write_text(json.dumps(data))
    return f


def deck_maker():
    return [
        explained("INT-0001", "Make one deck's content in any look"),
        explained("REQ-0001", "A deck's look comes from its brand alone",
                  "Every colour and font in a deck comes from its brand.", ["INT-0001"]),
        explained("REQ-0002", "A brand is a folder of tokens",
                  "Palette, fonts and logos, read by the deck builder.", ["INT-0001"]),
        explained("REQ-0003", "Slide text is written once",
                  "Slide text names no colour; the deck builders lay it out.", ["INT-0001"]),
        explained("TEST-0001", "Brands are read", "test/brand.test.mjs and `deck.render()` read "
                  "deck/brands/triad/brand.json", ["REQ-0002"]),
        explained("REQ-0004", "The first deck is made in two brands", "", ["REQ-0001"]),
        {"uid": "glossary:REG-0002", "type": "register", "status": "ratified",
         "title": "Terms live in TERM", "text": "deck builder deck builder", "links": [], "attrs": {}},
    ]


def brand(stamp1="sha256:REQ-0001", **extra):
    return term("TERM-0001", "Brand", "The look a deck is made in.", [
        ("defined_from", "app:REQ-0001", stamp1), ("defined_from", "app:REQ-0002", "sha256:REQ-0002"),
        ("driven_by", "app:REQ-0002", "sha256:REQ-0002"), ("shown_by", "app:REQ-0004", "sha256:REQ-0004"),
        ("distinct_from", "TERM-0002", None)],
        why="So a deck can be shown in another organisation's look.",
        how_it_works="The builder reads the brand's tokens each time.",
        example="The first deck in two brands.", **extra)


def content(*links):
    return term("TERM-0002", "Content", "What a deck says.", list(links) or [
        ("defined_from", "app:REQ-0003", "sha256:REQ-0003"), ("shown_by", "app:REQ-0004", "sha256:REQ-0004")],
        why="Written once.", how_it_works="Kept apart from any look.", example="The first deck.")


# ── candidates ──────────────────────────────────────────────────────────────

# tl: verifies tl-glossary/TEST-0001@fe751e546c67
def test_candidates_come_from_the_explained_graph_most_used_first(tmp_path):
    items = deck_maker() + [term("TERM-0009", "Brand", "x", [], aliases=["colour"])]
    out = run("candidates", "-C", tmp_path, "--dump", saved(tmp_path, items)).stdout
    listed = out.split("centres")[0]
    names = re.findall(r"^\s+\d+\s+(.+?)\s+\(", listed, re.M)
    assert names.index("deck") < names.index("deck builder")      # three items before two
    assert "deck builder  (app:REQ-0002, app:REQ-0003)" in out     # "builders" folded in
    assert "brand" not in names and "colour" not in names         # a term's names are left out
    assert not any(n in glossary.COMMON for n in names)
    assert "glossary:REG-0002" not in out                          # the standard is not explained
    assert not {"mjs", "test mjs", "json", "render", "triad"} & set(names)   # code and paths
    assert "deck builders" not in names                            # counted with its singular
    centres = out.split("centres")[1]
    assert centres.splitlines()[1].split()[1] == "app:INT-0001"


# ── review and shared names ─────────────────────────────────────────────────

# tl: verifies tl-glossary/TEST-0004@edaf5f71d1db
def test_review_names_the_term_whose_source_moved_and_leaves_the_rest_settled(tmp_path):
    items = deck_maker() + [
        brand(stamp1="sha256:old"),
        content(("defined_from", "app:REQ-0003", None), ("shown_by", "app:REQ-0004", "sha256:REQ-0004")),
        term("TERM-0003", "Token", "One value a brand sets.",
             [("defined_from", "app:REQ-0002", "sha256:REQ-0002"),
              ("shown_by", "app:REQ-0009", "sha256:REQ-0009")],
             why="w", how_it_works="h", example="e"),
        term("TERM-0004", "Deck", "What is presented.",
             [("defined_from", "app:REQ-0004", "sha256:REQ-0004")], why="w", how_it_works="h",
             example="e"),
    ]
    f = saved(tmp_path, items)
    before = sorted(p.name for p in tmp_path.iterdir())
    out = run("review", "-C", tmp_path, "--dump", f).stdout
    assert "4 term(s): 3 touched, 1 settled" in out
    assert re.search(r"touched  TERM-0001  Brand\n\s+moved\s+defined_from app:REQ-0001  A deck's look", out)
    assert re.search(r"touched  TERM-0002  Content\n\s+unstamped defined_from app:REQ-0003", out)
    assert re.search(r"touched  TERM-0003  Token\n\s+gone\s+shown_by app:REQ-0009", out)
    assert "settled  TERM-0004  Deck" in out
    assert sorted(p.name for p in tmp_path.iterdir()) == before


# tl: verifies tl-glossary/TEST-0007@177ae187b3ee
def test_review_reports_a_name_two_terms_share(tmp_path):
    items = deck_maker() + [brand(aliases=["Look"]),
                            term("TERM-0005", "look", "x", [], why="w", how_it_works="h", example="e")]
    out = run("review", "-C", tmp_path, "--dump", saved(tmp_path, items)).stdout
    assert "shared name  'look'  TERM-0001, TERM-0005" in out


# ── render ──────────────────────────────────────────────────────────────────

# tl: verifies tl-glossary/TEST-0008@4f30e7bd628d
def test_render_is_the_same_twice_and_its_check_catches_a_stale_one(tmp_path):
    f = saved(tmp_path, deck_maker() + [brand(aliases=["look"]), content()])
    doc = tmp_path / "docs" / "glossary.md"
    run("render", "-C", tmp_path, "--dump", f, "--out", doc)
    first = doc.read_bytes()
    run("render", "-C", tmp_path, "--dump", f, "--out", doc)
    assert doc.read_bytes() == first
    text = first.decode()
    assert text.startswith("# The deck maker's concepts\n")
    assert "| [Brand](#brand) | The look a deck is made in. |" in text
    assert text.index("## Brand") < text.index("## Content")
    assert "*Also called look.*" in text
    assert "**Why it exists.** So a deck can be shown" in text
    assert "**How it works.** The builder reads" in text
    assert "- Decided by `app:REQ-0002` A brand is a folder of tokens" in text
    assert "(`app:REQ-0004` The first deck is made in two brands)" in text
    assert "**Not to be confused with** [Content](#content)." in text
    assert "Defined from `app:REQ-0001` A deck's look comes from its brand alone;" in text
    assert "Under review" not in text
    assert run("render", "-C", tmp_path, "--dump", f, "--out", doc, "--check").returncode == 0

    moved = saved(tmp_path, deck_maker() + [brand(stamp1="sha256:old"), content()], "moved.json")
    assert run("render", "-C", tmp_path, "--dump", moved, "--out", doc, "--check",
               ok=False).returncode == 1
    assert doc.read_bytes() == first                               # --check wrote nothing
    run("render", "-C", tmp_path, "--dump", moved, "--out", doc)
    text = doc.read_text()
    assert ("> **Under review.** `app:REQ-0001` A deck's look comes from its brand alone "
            "has changed since this entry was written.") in text
    assert text.index("Under review") < text.index("## Content")
    assert run("render", "-C", tmp_path, "--dump", moved, "--out", doc, "--check").returncode == 0

    # A source two links reach is named once.
    items = deck_maker()
    items[2] = dict(items[2], fingerprint="sha256:new")             # app:REQ-0002 moved
    twice = saved(tmp_path, items + [brand(), content()], "twice.json")
    run("render", "-C", tmp_path, "--dump", twice, "--out", doc)
    notice = next(l for l in doc.read_text().splitlines() if "Under review" in l)
    assert notice.count("`app:REQ-0002`") == 1


# ── what tl check makes of it ───────────────────────────────────────────────

def explained_graph(root: Path):
    root.mkdir(parents=True)
    (root / "throughline.toml").write_text(
        '[project]\nname = "deck maker"\nformat_version = 4\n'
        '[grounding]\nroot_types = ["intent"]\ndelivery_roots = ["intent"]\n'
        'ground_link_types = ["implements"]\n[links]\ntypes = ["implements"]\n'
        '[status]\nvalues = ["proposed", "ratified", "rejected", "deleted"]\n'
        '[status.roles]\ninitial = "proposed"\nproposed = "proposed"\nratified = "ratified"\n'
        'invalidated = "rejected"\ntombstone = "deleted"\n')
    for prefix, folder, kind in (("INT", "vision", "intent"), ("REQ", "requirements", "requirement")):
        subprocess.run(["tl", "-C", str(root), "register", "new", prefix, folder, "--type", kind],
                       check=True, capture_output=True)
    changes = {"change_set_format": 2, "operations": [
        {"op": "new", "register": "INT", "label": "i", "title": "Decks in any look", "text": "t"},
        {"op": "new", "register": "REQ", "title": "A deck's look comes from its brand alone",
         "text": "t", "links": [{"target": "$i", "type": "implements"}]},
        {"op": "new", "register": "REQ", "title": "The first deck is made in two brands",
         "text": "t", "links": [{"target": "$i", "type": "implements"}]}]}
    (root.parent / "explained.json").write_text(json.dumps(changes))
    subprocess.run(["tl", "-C", str(root), "apply", str(root.parent / "explained.json")],
                   check=True, capture_output=True)


# tl: verifies tl-glossary/TEST-0003@ef557c66c2fe
@needs_tl
def test_init_lays_the_glossary_beside_the_graph_it_explains(tmp_path):
    explained_graph(tmp_path / "idd")
    refused = run("init", "-C", tmp_path, "--explains", "idd", "--at", "idd/glossary",
                  "--standard", STANDARD, ok=False)
    assert refused.returncode == 2 and "inside the graph at idd" in refused.stderr
    assert not (tmp_path / "idd" / "glossary").exists()
    run("init", "-C", tmp_path, "--explains", "idd", "--standard", STANDARD)
    toml = (tmp_path / "glossary" / "throughline.toml").read_text()
    assert re.search(r'namespace = "glossary"\n(url|path) = ', toml)
    assert "schema = true" in toml
    assert '[[sources]]\nnamespace = "app"\npath = "../idd"\n' in toml
    if "://" in STANDARD:
        assert f'ref = "{glossary.STANDARD_REF}"' in toml


# tl: verifies tl-glossary/TEST-0002@52b7b49a2015
@needs_tl
def test_a_glossary_written_as_the_skill_writes_it_passes_tl_check(tmp_path):
    explained_graph(tmp_path / "idd")
    run("init", "-C", tmp_path, "--explains", "idd", "--standard", STANDARD)
    g = tmp_path / "glossary"
    changes = {"change_set_format": 2, "operations": [
        {"op": "new", "register": "GLS", "label": "g", "title": "The deck maker's concepts",
         "text": "t"},
        {"op": "new", "register": "AUD", "label": "cto", "title": "A technical director",
         "text": "t", "attrs": {"knows": "Did not build it."},
         "links": [{"target": "$g", "type": "derives_from"}]},
        {"op": "new", "register": "TERM", "label": "brand", "title": "Brand",
         "text": "The look a deck is made in.",
         "attrs": {"why": "w", "how_it_works": "h", "example": "e", "aliases": ["look"],
                   "deprecated_names": ["skin"]},
         "links": [{"target": "$g", "type": "derives_from"}, {"target": "$cto", "type": "for"}]},
        {"op": "link", "uid": "$brand", "target": "app:REQ-0001", "type": "defined_from", "stamp": True},
        {"op": "link", "uid": "$brand", "target": "app:REQ-0002", "type": "shown_by", "stamp": True}]}
    (tmp_path / "set.json").write_text(json.dumps(changes))
    subprocess.run(["tl", "-C", str(g), "apply", str(tmp_path / "set.json")], check=True,
                   capture_output=True)
    check = subprocess.run(["tl", "-C", str(g), "check"], text=True, capture_output=True)
    assert check.returncode == 0, check.stdout + check.stderr
    item = (g / "terms" / "TERM-0001.yml").read_text()
    assert "aliases:\n  - look\n" in item and "deprecated_names:\n  - skin" in item
    assert item.count("stamp: sha256:") == 2
    out = run("review", "-C", g).stdout
    assert "1 term(s): 0 touched, 1 settled" in out


# ── the floor ───────────────────────────────────────────────────────────────

# tl: verifies tl-glossary/TEST-0009@b81e8d2ba7f5
@pytest.mark.parametrize("args", [["candidates", "-C", "{root}"], ["review", "-C", "{root}"],
                                  ["render", "-C", "{root}"],
                                  ["init", "-C", "{root}", "--explains", "idd"]])
def test_a_tl_older_than_5_2_0_is_refused(args, tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "tl").write_text("#!/bin/sh\necho 'tl 5.1.0'\n")
    (bin_dir / "tl").chmod(0o755)
    root = tmp_path / "work"
    root.mkdir()
    r = run(*(a.format(root=root) for a in args), cwd=root,
            path=f"{bin_dir}{os.pathsep}{os.environ['PATH']}", ok=False)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "tl 5.1.0 is older than 5.2.0" in r.stderr
    assert "pip install --upgrade 'throughline>=5.2.0'" in r.stderr
    assert list(root.iterdir()) == []


# ── audiences, other glossaries and retired names ───────────────────────────

def audience(uid, title, knows):
    return {"uid": uid, "type": "audience", "status": "proposed", "title": title, "text": title,
            "attrs": {"knows": knows}, "links": [{"target": "GLS-0001", "type": "derives_from"}]}


def gloss(uid, of, aud, text, stamp, **attrs):
    return {"uid": uid, "type": "gloss", "status": "proposed", "title": uid, "text": text,
            "attrs": attrs, "links": [{"target": of, "type": "glosses", "stamp": stamp},
                                      {"target": aud, "type": "for"}]}


def for_(item, *auds):
    return dict(item, links=item["links"] + [{"target": a, "type": "for"} for a in auds])


def fingerprinted(item, fp):
    return dict(item, fingerprint=fp)


# tl: verifies tl-glossary/TEST-0010@d1b88834cc55
def test_an_audiences_glossary_holds_only_its_terms_in_its_glosses(tmp_path):
    items = deck_maker() + [
        audience("AUD-0001", "A technical director", "Did not build it; asks where the knowledge lives."),
        audience("AUD-0002", "A deck author", "Writes slides; never edits a brand."),
        fingerprinted(for_(brand(), "AUD-0001", "AUD-0002"), "sha256:brand"),
        for_(content(), "AUD-0002"),
        gloss("GLOSS-0001", "TERM-0001", "AUD-0002", "The look your deck is shown in, which you never set.",
              "sha256:brand", why="So you write once."),
    ]
    f = saved(tmp_path, items)
    cto, author, full = (tmp_path / n for n in ("cto.md", "author.md", "full.md"))
    run("render", "-C", tmp_path, "--dump", f, "--audience", "AUD-0001", "--out", cto)
    run("render", "-C", tmp_path, "--dump", f, "--audience", "a deck author", "--out", author)
    run("render", "-C", tmp_path, "--dump", f, "--out", full)
    c, a, w = cto.read_text(), author.read_text(), full.read_text()
    assert c.startswith("# The deck maker's concepts: for a technical director\n")
    assert "*Written for a technical director: did not build it; asks where the knowledge lives.*" in c
    assert "## Brand" in c and "## Content" not in c
    assert "The look a deck is made in." in c and "**Why it exists.** So a deck can be shown" in c
    assert "## Brand" in a and "## Content" in a
    assert "| [Brand](#brand) | The look your deck is shown in, which you never set. |" in a
    assert "**Why it exists.** So you write once." in a
    assert "**How it works.** The builder reads the brand's tokens each time." in a   # the term's own
    assert "worded for this reader in `GLOSS-0001`, not yet signed" in a
    assert "Published for a deck author (2 terms); a technical director (1 terms)." in w
    assert "Under review" not in a

    moved = items[:-1] + [gloss("GLOSS-0001", "TERM-0001", "AUD-0002", "x", "sha256:old"),
                          gloss("GLOSS-0002", "TERM-0001", "AUD-0002", "y", "sha256:brand")]
    out = run("review", "-C", tmp_path, "--dump", saved(tmp_path, moved, "moved.json")).stdout
    assert "gloss    GLOSS-0001  moved glosses TERM-0001  Brand" in out
    assert "glosses  2 glosses word TERM-0001 for AUD-0002; keep one" in out
    refused = run("render", "-C", tmp_path, "--dump", f, "--audience", "nobody", ok=False)
    assert refused.returncode == 2 and "no audience 'nobody'" in refused.stderr


def estate(uid, title, **attrs):
    return {"uid": f"estate:{uid}", "type": "term", "status": "ratified", "title": title,
            "text": title, "attrs": attrs, "links": [], "fingerprint": f"sha256:{uid}"}


# tl: verifies tl-glossary/TEST-0011@24857dc1c5af
def test_review_reports_where_names_disagree_with_the_shared_glossary(tmp_path):
    def matched(item, kind, target):
        return dict(item, links=item["links"] + [{"target": target, "type": kind, "stamp": f"sha256:{target.split(':')[1]}"}])
    items = deck_maker() + [
        estate("TERM-0001", "Look"), estate("TERM-0002", "Content"), estate("TERM-0003", "Token"),
        matched(brand(), "same_as", "estate:TERM-0001"),                        # Brand = Look
        content(),                                                               # also "content" there
        term("TERM-0003", "Slide", "s", [("defined_from", "app:REQ-0003", "sha256:REQ-0003")],
             why="w", how_it_works="h", example="e", local=True),               # local: no finding
        matched(term("TERM-0004", "Chip", "c", [], why="w", how_it_works="h", example="e"),
                "close_to", "app:REQ-0002"),                                      # not a term
    ]
    out = run("review", "-C", tmp_path, "--dump", saved(tmp_path, items)).stdout
    assert ("name differs  TERM-0001 Brand  is the same as  estate:TERM-0001 Look: "
            "one concept, two preferred names") in out
    assert "no match      TERM-0002 Content: in no glossary of estate" in out
    assert "two meanings  'content'  is TERM-0002 Content here and estate:TERM-0002 Content there" in out
    assert "TERM-0003 Slide" not in out.split("settled")[-1].split("\n", 1)[-1]
    assert "no match      TERM-0003" not in out
    assert "not a term    TERM-0004 close_to app:REQ-0002" in out
    # The shared glossary is mapped onto, not explained: none of its names is a candidate.
    cands = run("candidates", "-C", tmp_path, "--dump", saved(tmp_path, items, "c.json")).stdout
    assert "estate:" not in cands and cands.startswith("candidates from app ")


# tl: verifies tl-glossary/TEST-0012@4675a0211000
def test_review_finds_a_retired_name_as_a_whole_word(tmp_path):
    items = deck_maker() + [
        explained("REQ-0005", "The Skin is read first", "x"),
        explained("REQ-0006", "Two skins", "a skin-deep look"),
        brand(deprecated_names=["skin"]),
    ]
    out = run("review", "-C", tmp_path, "--dump", saved(tmp_path, items)).stdout
    hits = [l for l in out.splitlines() if l.startswith("retired name")]
    assert hits == ["retired name  'skin' (TERM-0001 Brand) still in app:REQ-0005  The Skin is read first"]
