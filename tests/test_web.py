"""Tests for web.py rewriting, sidebar, pager, search index."""

from lxml import html

from book_scraper.web import (
    _chapter_body,
    _first_stem_match,
    _pager,
    _rewrite_links,
    _search_index,
    _sidebar_ul,
)


def body_of(markup):
    frag = html.fromstring(
        f'<html><body><div id="sbo-rt-content">{markup}</div></body></html>'
    )
    return frag.find("body").find("div")


class TestRewriteLinks:
    def test_xhtml_to_html(self):
        b = body_of('<a href="ch02.xhtml#sec">x</a>')
        _rewrite_links(b)
        assert b.find("a").get("href") == "ch02.html#sec"

    def test_html_to_html(self):
        b = body_of('<a href="ch02.html">x</a>')
        _rewrite_links(b)
        assert b.find("a").get("href") == "ch02.html"

    def test_fragment_absolute_untouched(self):
        b = body_of(
            '<a href="#f">a</a><a href="https://x.com/y">b</a>'
            '<a href="Images/i.png">c</a>'
        )
        _rewrite_links(b)
        links = [a.get("href") for a in b.iter("a")]
        assert links == ["#f", "https://x.com/y", "Images/i.png"]


TOC = [
    {
        "id": "p",
        "label": "Preface",
        "href": "preface01.html",
        "fragment": "",
        "depth": 1,
        "children": [
            {
                "id": "s",
                "label": "Sub",
                "href": "preface01.html",
                "fragment": "preface_sub",
                "depth": 2,
                "children": [],
            }
        ],
    },
    {
        "id": "c1",
        "label": "Ch 1",
        "href": "ch01.html",
        "fragment": "",
        "depth": 1,
        "children": [],
    },
]


class TestSidebar:
    def test_single_active_item(self):
        active = _first_stem_match(TOC, "preface01")
        out = _sidebar_ul(TOC, active)
        assert out.count('class="active"') == 1
        assert 'href="preface01.html#preface"' not in out  # parent has no frag
        assert 'href="preface01.html#preface_sub"' in out

    def test_no_active_for_unknown_stem(self):
        out = _sidebar_ul(TOC, _first_stem_match(TOC, None))
        assert 'class="active"' not in out


PAGER_CH = [
    {"filename": "a.html", "title": "A"},
    {"filename": "b.html", "title": "B"},
    {"filename": "c.html", "title": "C"},
]


class TestPager:
    def test_first_page_next_only(self):
        p = _pager(PAGER_CH, 0)
        assert 'class="next"' in p and 'class="prev"' not in p

    def test_middle_both(self):
        p = _pager(PAGER_CH, 1)
        assert 'href="a.html"' in p and 'href="c.html"' in p

    def test_last_prev_only(self):
        p = _pager(PAGER_CH, 2)
        assert 'class="prev"' in p and 'class="next"' not in p


XHTML_PAGE = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><body>
<div class="chapter" id="ch01">
<h1>Chapter Title</h1>
<div class="sect1" id="ch01_sec_one"><h2>Section One</h2>
<p>error budgets and SLO burn rates</p></div>
<div class="sect1" id="ch01_sec_two"><h2>Section Two</h2>
<p>postmortem culture</p></div>
</div></body></html>"""


class TestSearchIndex:
    def test_sections_split_with_deep_links(self, tmp_path):
        (tmp_path / "ch01.xhtml").write_text(XHTML_PAGE)
        chapters = [{"filename": "ch01.html", "title": "Chapter 1"}]
        entries = _search_index(chapters, str(tmp_path))
        urls = [e["u"] for e in entries]
        assert "ch01.html#ch01_sec_one" in urls
        assert "ch01.html#ch01_sec_two" in urls
        sec = next(e for e in entries if e["u"].endswith("ch01_sec_one"))
        assert sec["t"] == "Section One"
        assert "error budgets" in sec["s"]

    def test_index_chapter_excluded(self, tmp_path):
        (tmp_path / "ix01.xhtml").write_text(
            '<?xml version="1.0"?><html><body>'
            '<div epub:type="index" id="ix"><h1>Index</h1></div>'
            "</body></html>"
        )
        entries = _search_index(
            [{"filename": "ix01.html", "title": "Index"}], str(tmp_path)
        )
        assert entries == []


class TestChapterBody:
    def test_inline_styles_carried(self, tmp_path):
        (tmp_path / "cover.xhtml").write_text(
            '<?xml version="1.0"?><html><head><style>body{display:table}'
            '</style></head><body><div id="Cover">x</div></body></html>'
        )
        styles, body = _chapter_body(str(tmp_path / "cover.xhtml"))
        assert "display:table" in styles
        assert 'id="Cover"' in body
