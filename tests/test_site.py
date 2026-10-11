"""Checks of the landing page against the repository graph's own items.

throughline-skills TEST-0004 and TEST-0005, read against site/index.html, the
file the host serves. What the response carries (headers, the content security
policy) is the host's to check, where the page is served. Standard library only.
"""
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

PAGE = Path(__file__).resolve().parents[1] / "site" / "index.html"
OWN = "skills.iddn.uk"
FONTS = {"fonts.googleapis.com", "fonts.gstatic.com"}
LINKED = {OWN, "iddn.uk", "github.com", "claude.ai"} | FONTS
# Attributes through which a page loads something, as against links a reader follows.
LOADS = {("link", "href"), ("script", "src"), ("img", "src"), ("img", "srcset"),
         ("source", "src"), ("source", "srcset"), ("iframe", "src"), ("embed", "src"),
         ("object", "data"), ("video", "src"), ("audio", "src"), ("video", "poster")}
NAVIGATES = {"canonical", "alternate"}


class Page(HTMLParser):
    """What the page loads, what it links to, what could run, and the text of
    its install section."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags, self.loads, self.links, self.handlers, self.cookies = [], [], [], [], []
        self.style, self.install = [], []
        self._in_style = False
        self._sections = []                 # open sections: True for the install one

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.append(tag)
        if tag == "style":
            self._in_style = True
        if tag == "section":
            self._sections.append("install" in (a.get("class") or "").split())
        if tag == "meta" and (a.get("http-equiv") or "").lower() == "set-cookie":
            self.cookies.append(a)
        rel = set((a.get("rel") or "").split())
        for name, value in attrs:
            if name.startswith("on") or (value or "").strip().lower().startswith("javascript:"):
                self.handlers.append((tag, name))
            if not value:
                continue
            if (tag, name) in LOADS and not (tag == "link" and rel & NAVIGATES):
                self.loads.extend(v.split()[0] for v in value.split(",") if v.strip())
            elif name == "href":
                self.links.append(value)

    def handle_endtag(self, tag):
        if tag == "style":
            self._in_style = False
        if tag == "section" and self._sections:
            self._sections.pop()

    def handle_data(self, data):
        if self._in_style:
            self.style.append(data)
        if any(self._sections):
            self.install.append(data)


def page():
    p = Page()
    p.feed(PAGE.read_text(encoding="utf-8"))
    return p


def host(url):
    """The host an absolute URL names, or None for one relative to the page."""
    parts = urlsplit(url)
    return parts.hostname if parts.scheme in ("http", "https") or url.startswith("//") else None


# tl: verifies throughline-skills/TEST-0004
def test_no_script_no_cookie_and_nothing_loaded_from_another_origin_but_the_fonts():
    p = page()
    assert "script" not in p.tags
    assert p.handlers == []
    assert p.cookies == []
    css_urls = re.findall(r"url\(\s*['\"]?([^'\")]+)", "".join(p.style))
    loaded = {host(u) for u in p.loads + css_urls} - {None}
    assert loaded <= {OWN} | FONTS, loaded - ({OWN} | FONTS)
    linked = {host(u) for u in p.links} - {None}
    assert linked <= LINKED, linked - LINKED
    # the fonts the page loads are the estate's, from both font origins
    assert FONTS <= loaded


# tl: verifies throughline-skills/TEST-0005
def test_the_install_section_names_one_route_and_the_remove_command():
    text = re.sub(r"\s+", " ", "".join(page().install))
    assert "Pick one route" in text
    assert "/plugin marketplace remove throughline-skills" in text
    assert "network source differs" in text
