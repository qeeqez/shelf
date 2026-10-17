"""Tests for web.py rewriting, sidebar, pager, search index."""

from lxml import html

from shelf.web import (
    SITE_CSS,
    SITE_JS,
    _chapter_data,
    _first_stem_match,
    _pager,
    _rewrite_links,
    _section_entries,
    _sidebar_ul,
    build_web,
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

    def test_chapters_prefix_applied(self):
        """Root pages (index/toc) link into chapters/; chapter pages don't."""
        out = _sidebar_ul(TOC, None, "chapters/")
        assert 'href="chapters/preface01.html"' in out
        assert 'href="chapters/preface01.html#preface_sub"' in out

    def test_container_heading_renders_span(self):
        """An href-less TOC entry used to produce href=".html" — a dead link."""
        items = [
            {
                "id": "part1",
                "label": "Part I",
                "href": "",
                "fragment": "",
                "depth": 1,
                "children": [
                    {
                        "id": "c1",
                        "label": "Ch 1",
                        "href": "ch01.html",
                        "fragment": "",
                        "depth": 2,
                        "children": [],
                    }
                ],
            }
        ]
        out = _sidebar_ul(items, None)
        assert '<span class="branch">Part I</span>' in out
        assert 'href=".html"' not in out

    def test_href_attribute_escapes_quotes(self):
        """escape() leaves '"' alone by default — inside a double-quoted
        attribute it must become &quot; or it breaks out of the tag."""
        items = [
            {
                "id": "x",
                "label": "L",
                "href": "ch01.html",
                "fragment": 'sec"quote',
                "depth": 1,
                "children": [],
            }
        ]
        out = _sidebar_ul(items, None)
        assert 'href="ch01.html#sec&quot;quote"' in out


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

    def test_href_escapes_quotes(self):
        ch = [{"filename": 'a"b.html', "title": "A"}, PAGER_CH[1]]
        assert 'href="a&quot;b.html"' in _pager(ch, 1)


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
        _, _, body, _ = _chapter_data(str(tmp_path / "ch01.xhtml"))
        entries = _section_entries(body, "Chapter 1", "ch01.html")
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
        _, _, _, is_index = _chapter_data(str(tmp_path / "ix01.xhtml"))
        assert is_index

    def test_index_epubtype_multi_value(self, tmp_path):
        """epub:type is a space-separated list — 'index backmatter' is
        still an index page and must stay out of the search index."""
        (tmp_path / "ix01.xhtml").write_text(
            '<?xml version="1.0"?><html><body>'
            '<div epub:type="index backmatter" id="ix"><h1>Index</h1></div>'
            "</body></html>"
        )
        _, _, _, is_index = _chapter_data(str(tmp_path / "ix01.xhtml"))
        assert is_index

    def test_markup_noise_not_indexed(self, tmp_path):
        """style/script/math text is markup, not prose — keep it out."""
        (tmp_path / "ch01.xhtml").write_text(
            '<?xml version="1.0"?><html><body><div class="chapter" id="c">'
            "<h1>T</h1><p>real prose</p>"
            "<style>.x{color:red}</style><script>var z=1;</script>"
            '<math xmlns="http://www.w3.org/1998/Math/MathML"><mi>zzq</mi></math>'
            "</div></body></html>"
        )
        _, _, body, _ = _chapter_data(str(tmp_path / "ch01.xhtml"))
        entries = _section_entries(body, "C", "ch01.html")
        text = " ".join(e["s"] for e in entries)
        assert "real prose" in text
        assert "color:red" not in text
        assert "var z=1" not in text
        assert "zzq" not in text

    def test_comments_not_indexed(self, tmp_path):
        """Comment text isn't prose — but the tail after it is."""
        (tmp_path / "ch01.xhtml").write_text(
            '<?xml version="1.0"?><html><body><div class="chapter" id="c">'
            "<h1>T</h1><!-- secret draft note -->"
            "<p>real prose</p></div></body></html>"
        )
        _, _, body, _ = _chapter_data(str(tmp_path / "ch01.xhtml"))
        text = " ".join(e["s"] for e in _section_entries(body, "C", "ch01.html"))
        assert "real prose" in text
        assert "secret draft note" not in text

    def test_body_id_not_used_as_fragment(self, tmp_path):
        """<body>/<html> ids never reach the generated page — a heading
        with no nearer id must deep-link to the page, not a phantom id."""
        (tmp_path / "ch01.xhtml").write_text(
            '<?xml version="1.0"?><html><body id="bodyid">'
            "<div><h2>Section</h2><p>text</p></div></body></html>"
        )
        _, _, body, _ = _chapter_data(str(tmp_path / "ch01.xhtml"))
        entries = _section_entries(body, "C", "ch01.html")
        assert entries[0]["u"] == "ch01.html"


class TestChapterBody:
    def test_inline_styles_carried(self, tmp_path):
        (tmp_path / "cover.xhtml").write_text(
            '<?xml version="1.0"?><html><head><style>body{display:table}'
            '</style></head><body><div id="Cover">x</div></body></html>'
        )
        styles, body, _, _ = _chapter_data(str(tmp_path / "cover.xhtml"))
        assert "display:table" in styles
        assert 'id="Cover"' in body

    def test_asset_paths_bumped_for_chapters_dir(self, tmp_path):
        """Chapter pages sit in chapters/ — Images/, Fonts/, Styles/ refs
        must be rewritten to ../ so they resolve at the web root."""
        (tmp_path / "ch01.xhtml").write_text(
            '<?xml version="1.0"?><html><body><div class="chapter" id="c">'
            '<img src="Images/i.png"/><a href="Fonts/f.otf">f</a>'
            '<a href="ch02.xhtml">next</a></div></body></html>'
        )
        _, body, _, _ = _chapter_data(str(tmp_path / "ch01.xhtml"))
        assert 'src="../Images/i.png"' in body
        assert 'href="../Fonts/f.otf"' in body
        assert 'href="ch02.html"' in body  # same-dir link stays flat

    def test_body_style_not_duplicated(self, tmp_path):
        """A <style> inside <body> ships in body_html already — hoisting it
        into extra_head as well would emit every rule twice."""
        (tmp_path / "ch01.xhtml").write_text(
            '<?xml version="1.0"?><html><body><div id="c">'
            "<style>p{color:blue}</style><p>x</p></div></body></html>"
        )
        styles, body, _, _ = _chapter_data(str(tmp_path / "ch01.xhtml"))
        assert "color:blue" in body
        assert "color:blue" not in styles


def make_book(tmp_path, names=("a", "b", "c")):
    oebps = tmp_path / "OEBPS"
    oebps.mkdir()
    for n in names:
        (oebps / f"{n}.xhtml").write_text(
            f'<?xml version="1.0"?><html><body>'
            f'<div class="chapter" id="{n}"><h1>{n}</h1>'
            f"<p>{n} text</p></div></body></html>"
        )
    return str(oebps)


class TestBuildWeb:
    def test_missing_chapter_gets_no_links(self, tmp_path):
        """A chapter whose .xhtml is absent is skipped — the pager, head
        rel links and 'Start reading' must not point at a 404 page."""
        oebps = make_book(tmp_path, names=("a", "c"))  # b never written
        chapters = [{"filename": f"{n}.html", "title": n} for n in "abc"]
        web = tmp_path / "web"
        build_web(oebps, chapters, [], {"title": "T"}, str(web))
        c_page = (web / "chapters" / "c.html").read_text(encoding="utf-8")
        assert 'href="a.html"' in c_page  # prev skips the missing b
        assert "b.html" not in c_page
        a_page = (web / "chapters" / "a.html").read_text(encoding="utf-8")
        assert 'href="c.html"' in a_page  # next skips it too
        assert "b.html" not in a_page
        index = (web / "index.html").read_text(encoding="utf-8")
        assert 'href="chapters/a.html"' in index

    def test_description_markup_stripped_for_meta(self, tmp_path):
        """info['description'] ships HTML markup — meta tags need text."""
        oebps = make_book(tmp_path, names=("a",))
        chapters = [{"filename": "a.html", "title": "a"}]
        info = {
            "title": "T",
            "description": '<p>hello <b>"world"</b></p>',
        }
        web = tmp_path / "web"
        build_web(oebps, chapters, [], info, str(web))
        index = (web / "index.html").read_text(encoding="utf-8")
        assert 'content="hello &quot;world&quot;"' in index


class TestSiteAssets:
    """The reading-experience features live in the embedded CSS/JS —
    guard the hooks they depend on."""

    def test_reading_position_persisted(self):
        """Scroll memory is keyed per book dir (file:// shares one origin
        across books) and an explicit #hash always wins over it."""
        assert '"shelf-pos:" + siteRoot' in SITE_JS
        assert "location.hash" in SITE_JS
        assert '"/chapters/"' in SITE_JS  # only chapters mark the resume point

    def test_resume_link_on_index(self, tmp_path):
        """index.html carries a .start hook so site.js can turn
        'Start reading' into 'Continue reading' at the last-read chapter."""
        oebps = make_book(tmp_path, names=("a",))
        chapters = [{"filename": "a.html", "title": "a"}]
        web = tmp_path / "web"
        build_web(oebps, chapters, [], {"title": "T"}, str(web))
        index = (web / "index.html").read_text(encoding="utf-8")
        assert '<a class="start" href="chapters/a.html">' in index
        assert '"shelf-last:" + siteRoot' in SITE_JS

    def test_reading_progress_bar(self):
        assert 'className = "progress"' in SITE_JS
        assert ".progress{" in SITE_CSS

    def test_footnote_preview_and_target_flash(self):
        """Hover/focus preview needs the noteref selector, tooltip wiring
        and id-stripping; plain jumps get a :target flash so the landing
        spot is findable in a wall of footnotes."""
        assert 'a[data-type="noteref"]' in SITE_JS
        assert '"role", "tooltip"' in SITE_JS
        assert "aria-describedby" in SITE_JS
        assert "querySelector(\"a[href*='#']\")" in SITE_JS  # back-link strip
        assert '[data-type="footnote"]:target' in SITE_CSS
        assert 'a[data-type="noteref"]:target' in SITE_CSS
        assert ".note-tip{" in SITE_CSS

    def test_copy_button_on_code(self):
        """Buttons sit in .pre-wrap — inside the pre itself, overflow-x
        scrolling would push them off-screen."""
        assert '".content pre"' in SITE_JS
        assert 'w.className = "pre-wrap"' in SITE_JS
        assert ".pre-wrap{" in SITE_CSS
        assert ".copy-btn{" in SITE_CSS

    def test_keyboard_shortcuts_and_help(self):
        assert 'e.key === "j"' in SITE_JS
        assert 'e.key === "k"' in SITE_JS
        assert 'e.key === "t"' in SITE_JS
        assert 'e.key === "w"' in SITE_JS
        assert 'e.key === "?"' in SITE_JS
        assert 'help.id = "keys-help"' in SITE_JS
        assert ".keys{" in SITE_CSS

    def test_image_inversion_toggle(self):
        """Dark mode inverts the whole content; the opt-out re-inverts
        media back. Needs the CSS double-inversion rule, the persisted
        pref and the early-script hook."""
        assert 'data-imginv="off"' in SITE_CSS
        assert ".content img," in SITE_CSS
        assert '"shelf-imginv"' in SITE_JS
        assert '"imginv-btn"' in SITE_JS
        assert 'e.key === "i"' in SITE_JS

    def test_print_hides_added_chrome(self):
        """New floating UI must not leak into the print layout."""
        print_css = SITE_CSS.split("@media print")[1]
        for sel in (".copy-btn", ".note-tip", ".keys"):
            assert sel in print_css
