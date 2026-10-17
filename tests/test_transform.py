"""Tests for transform.py link rewriting and page rendering."""

from lxml import html

from book_scraper.transform import Transformer


def make_tx(book_id="BID123", base="https://learning.oreilly.com/x/"):
    return Transformer(book_id, base)


class TestLinkReplace:
    def test_chapter_link_flattened_to_xhtml(self):
        tx = make_tx()
        assert tx._link_replace("ch14.html") == "ch14.xhtml"
        assert tx._link_replace("ch14.html#sec") == "ch14.xhtml#sec"

    def test_chapter_link_under_images_dir(self):
        # Regression: 'images/ch14.html' is a chapter xref, not an image.
        tx = make_tx()
        assert tx._link_replace("images/ch14.html#ch14_foo") == "ch14.xhtml#ch14_foo"

    def test_fragment_only_link_with_dir_prefix(self):
        tx = make_tx()
        assert tx._link_replace("images/#ch16_foo") == "#ch16_foo"

    def test_bare_directory_link(self):
        tx = make_tx()
        assert tx._link_replace("images/") == "#"

    def test_pure_fragment(self):
        tx = make_tx()
        assert tx._link_replace("#id123") == "#id123"

    def test_image_links_go_to_images_dir(self):
        tx = make_tx()
        assert tx._link_replace("images/foo.png") == "Images/foo.png"
        assert tx._link_replace("a/b/cover.png#x") == "Images/cover.png#x"
        assert tx._link_replace("graphics/icon.svg") == "Images/icon.svg"

    def test_absolute_url_preserved(self):
        tx = make_tx()
        assert tx._link_replace("https://example.com/x.png") == (
            "https://example.com/x.png"
        )

    def test_absolute_url_containing_book_id_recursed(self):
        tx = make_tx(book_id="BID123")
        assert (
            tx._link_replace("https://learning.oreilly.com/BID123/images/f.png")
            == "Images/f.png"
        )

    def test_mailto_and_empty(self):
        tx = make_tx()
        assert tx._link_replace("mailto:a@b.c") == "mailto:a@b.c"
        assert tx._link_replace("") == ""

    def test_data_uri_preserved(self):
        tx = make_tx()
        uri = "data:image/png;base64,iVBORw0KGgo="
        assert tx._link_replace(uri) == uri


class TestParse:
    def test_epub_namespace_declared(self):
        tx = make_tx()
        root = html.fromstring(
            '<html><body><div id="sbo-rt-content">'
            '<p epub:type="note">hi</p></div></body></html>'
        )
        page_css, xhtml = tx.parse(root)
        page = tx.render_page(page_css, xhtml, title="T")
        assert 'xmlns:epub="http://www.idpf.org/2007/ops"' in page
        parsed = html.etree.fromstring(page.encode())
        assert parsed is not None

    def test_reader_chrome_stripped(self):
        tx = make_tx()
        root = html.fromstring(
            '<html><body><div id="sbo-rt-content">'
            "<p>keep</p><script>x()</script><button>b</button>"
            '<iframe src="x"></iframe></div></body></html>'
        )
        _, xhtml = tx.parse(root)
        assert "keep" in xhtml
        assert "<script" not in xhtml and "<button" not in xhtml
        assert "<iframe" not in xhtml

    def test_missing_content_raises(self):
        tx = make_tx()
        root = html.fromstring("<html><head></head></html>")
        try:
            tx.parse(root)
        except ValueError as e:
            assert "missing" in str(e)
        else:
            raise AssertionError("expected ValueError")

    def test_stylesheet_registration_dedupes(self):
        tx = make_tx()
        root = html.fromstring(
            '<html><head><link rel="stylesheet" href="/epub.css"/></head>'
            '<body><div id="sbo-rt-content"><p>x</p></div></body></html>'
        )
        page_css, _ = tx.parse(root)
        assert "Styles/Style00.css" in page_css
        _, _ = tx.parse(root)  # same stylesheet again
        assert len(tx.css) == 1

    def test_brace_heavy_code_survives(self):
        tx = make_tx()
        root = html.fromstring(
            '<html><body><div id="sbo-rt-content">'
            '<pre>{"a": {1, 2}}</pre></div></body></html>'
        )
        page_css, xhtml = tx.parse(root)
        page = tx.render_page(page_css, xhtml)
        assert '{"a": {1, 2}}' in page
