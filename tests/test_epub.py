"""Tests for epub.py NCX/OPF generation."""

import os
import re
import zipfile
from urllib.parse import unquote

from lxml import etree

from shelf.epub import EpubBuilder, _epub_href, _item_id

INFO = {
    "title": "Test Book",
    "authors": ["Ada Lovelace", "Alan Turing"],
    "isbn": "1234567890",
    "publishers": ["Pub Co"],
    "description": "A book.",
    "rights": "",
    "issued": "2025-01-01",
    "subjects": [],
}


def make_builder(tmp_path, info=None):
    return EpubBuilder(info or INFO, "BID1", str(tmp_path))


def toc_items():
    return [
        {
            "id": "ch01",
            "label": "Chapter 1",
            "href": "ch01.html",
            "fragment": "",
            "depth": 1,
            "children": [
                {
                    "id": "s1",
                    "label": "Section One",
                    "href": "ch01.html",
                    "fragment": "ch01_section_one",
                    "depth": 2,
                    "children": [],
                },
                {
                    "id": "s2:dup",
                    "label": "Section Two",
                    "href": "ch01.html",
                    "fragment": "ch01_section_one",  # same target
                    "depth": 2,
                    "children": [],
                },
            ],
        }
    ]


class TestTocNcx:
    def test_navpoint_ids_are_ncname_safe(self):
        b = make_builder("/tmp/x")
        navmap, _, _ = b._parse_toc_ncx(toc_items())
        for m in re.finditer(r'navPoint id="([^"]+)"', navmap):
            assert ":" not in m.group(1)
            assert re.fullmatch(r"[A-Za-z_][\w.-]*", m.group(1))

    def test_fragments_in_content_src(self):
        b = make_builder("/tmp/x")
        navmap, _, _ = b._parse_toc_ncx(toc_items())
        assert 'src="ch01.xhtml#ch01_section_one"' in navmap

    def test_same_target_shares_playorder(self):
        b = make_builder("/tmp/x")
        ncx = b._toc_ncx(toc_items(), [])
        root = etree.fromstring(ncx.encode())
        ns = "http://www.daisy.org/z3986/2005/ncx/"
        by_src = {}
        for np in root.iter(f"{{{ns}}}navPoint"):
            src = np.find(f"{{{ns}}}content").get("src")
            by_src.setdefault(src, set()).add(np.get("playOrder"))
        assert all(len(v) == 1 for v in by_src.values())

    def test_uid_matches_identifier(self):
        b = make_builder("/tmp/x")
        ncx = b._toc_ncx(toc_items(), [])
        # dtb:uid must equal dc:identifier exactly — both go through
        # _identifier() so the urn:isbn scheme can't drift apart.
        assert 'content="urn:isbn:1234567890" name="dtb:uid"' in ncx
        assert "ID:ISBN:" not in ncx

    def test_page_list_targets(self):
        """virtual_pages from the API produce a pageList with cumulative
        page numbers at each chapter start."""
        b = make_builder("/tmp/x")
        chapters = [
            {"filename": "ch01.html", "virtual_pages": 10},
            {"filename": "ch02.html", "virtual_pages": 5},
            {"filename": "ch03.html", "virtual_pages": 20},
        ]
        ncx = b._toc_ncx(toc_items(), chapters)
        assert '<pageList id="pageList" class="pagelist">' in ncx
        assert 'id="pageTarget-1" type="normal" value="1"' in ncx
        assert 'id="pageTarget-11" type="normal" value="11"' in ncx
        assert 'id="pageTarget-16" type="normal" value="16"' in ncx
        assert 'content src="ch02.xhtml"' in ncx
        assert 'content="35" name="dtb:totalPageCount"' in ncx
        # pageTargets keep their own unique numbering, disjoint from the
        # navPoint orders (which may share orders for duplicate targets).
        ns = "http://www.daisy.org/z3986/2005/ncx/"
        root = etree.fromstring(ncx.encode())
        np_orders = {int(np.get("playOrder")) for np in root.iter(f"{{{ns}}}navPoint")}
        pt_orders = [
            int(pt.get("playOrder")) for pt in root.iter(f"{{{ns}}}pageTarget")
        ]
        assert len(pt_orders) == len(set(pt_orders))
        assert not np_orders & set(pt_orders)

    def test_page_list_absent_without_counts(self):
        """Chapters lacking virtual_pages (old caches) emit no pageList."""
        b = make_builder("/tmp/x")
        chapters = [{"filename": "ch01.html"}, {"filename": "ch02.html"}]
        ncx = b._toc_ncx(toc_items(), chapters)
        assert "<pageList" not in ncx
        nav = b._nav_xhtml(toc_items(), chapters)
        assert "page-list" not in nav

    def test_page_list_nav_hidden(self):
        b = make_builder("/tmp/x")
        chapters = [
            {"filename": "ch01.html", "virtual_pages": 10},
            {"filename": "ch02.html", "virtual_pages": 5},
        ]
        nav = b._nav_xhtml(toc_items(), chapters)
        assert '<nav epub:type="page-list" hidden="hidden">' in nav
        assert '<a href="ch02.xhtml">11</a>' in nav

    def test_page_navigation_a11y_feature(self):
        b = make_builder("/tmp/x")
        chapters = [{"filename": "ch01.html", "virtual_pages": 3}]
        opf = b._content_opf(chapters, None, "ch01.html")
        assert "pageNavigation" in opf
        opf = b._content_opf([{"filename": "ch01.html"}], None, "ch01.html")
        assert "pageNavigation" not in opf

    def test_container_heading_uses_first_child_href(self):
        """TOC container headings have no href — the navPoint must point at
        the first descendant target, not an empty src."""
        items = [
            {
                "id": "part1",
                "label": "Part I",
                "href": "",
                "fragment": "",
                "depth": 1,
                "children": [
                    {
                        "id": "ch01",
                        "label": "Chapter 1",
                        "href": "ch01.html",
                        "fragment": "",
                        "depth": 2,
                        "children": [],
                    }
                ],
            }
        ]
        b = make_builder("/tmp/x")
        navmap, _, _ = b._parse_toc_ncx(items)
        assert 'src="ch01.xhtml"' in navmap
        assert 'src=""' not in navmap

    def test_unresolvable_items_emit_no_empty_src(self):
        """A TOC leaf with no href anywhere in its subtree must not emit a
        navPoint with an empty content src — its label is dropped but any
        resolvable siblings/children still appear."""
        items = [
            {
                "id": "dead",
                "label": "External",
                "href": "",
                "fragment": "",
                "depth": 1,
                "children": [
                    {
                        "id": "dead2",
                        "label": "Also Dead",
                        "href": "",
                        "fragment": "",
                        "depth": 2,
                        "children": [],
                    }
                ],
            },
            {
                "id": "wrapper",
                "label": "Links",
                "href": "",
                "fragment": "",
                "depth": 1,
                "children": [
                    {
                        "id": "ch01",
                        "label": "Chapter 1",
                        "href": "ch01.html",
                        "fragment": "",
                        "depth": 2,
                        "children": [],
                    }
                ],
            },
        ]
        b = make_builder("/tmp/x")
        navmap, _, _ = b._parse_toc_ncx(items)
        assert 'src=""' not in navmap
        # Fully unresolvable subtrees vanish; the container resolves to its
        # first child via _first_href and still wraps it.
        assert "External" not in navmap
        assert "Also Dead" not in navmap
        assert '<text>Links</text></navLabel><content src="ch01.xhtml"/>' in navmap

    def test_playorders_contiguous_and_ids_unique(self):
        """epubcheck rejects playOrder gaps and duplicate navPoint ids —
        numbering must survive nesting, dedup and skipped items."""
        items = toc_items() + [
            {
                "id": "dead",
                "label": "Dead",
                "href": "",
                "fragment": "",
                "depth": 1,
                "children": [],
            },
            {
                "id": "ch02",
                "label": "Chapter 2",
                "href": "ch02.html",
                "fragment": "",
                "depth": 1,
                "children": [],
            },
        ]
        b = make_builder("/tmp/x")
        navmap, _, _ = b._parse_toc_ncx(items)
        ids = re.findall(r'navPoint id="navpoint-(\d+)"', navmap)
        assert len(ids) == len(set(ids))
        # Same-target navPoints may share a playOrder; the distinct values
        # must still be contiguous — epubcheck flags gaps.
        orders = {int(m.group(1)) for m in re.finditer(r'playOrder="(\d+)"', navmap)}
        assert orders == set(range(1, len(orders) + 1))

    def test_dtb_depth_is_structural(self):
        """dtb:depth counts navMap nesting, not the listing's depth field —
        an item claiming depth 5 nested two levels deep still reports 2."""
        items = [
            {
                "id": "a",
                "label": "A",
                "href": "a.html",
                "fragment": "",
                "depth": 1,
                "children": [
                    {
                        "id": "b",
                        "label": "B",
                        "href": "b.html",
                        "fragment": "",
                        "depth": 5,
                        "children": [],
                    }
                ],
            }
        ]
        b = make_builder("/tmp/x")
        ncx = b._toc_ncx(items, [])
        assert 'content="2" name="dtb:depth"' in ncx


class TestTocOl:
    def test_container_heading_renders_span_not_dead_link(self):
        items = [
            {
                "id": "part1",
                "label": "Part I",
                "href": "",
                "fragment": "",
                "depth": 1,
                "children": [],
            }
        ]
        b = make_builder("/tmp/x")
        out = b._toc_ol(items)
        assert "<span>Part I</span>" in out
        assert 'href=""' not in out


class TestContentOpf:
    def _write_chapter(self, b, name, inner=""):
        path = os.path.join(b.oebps, name)
        with open(path, "w") as f:
            f.write(
                '<?xml version="1.0"?><html'
                ' xmlns="http://www.w3.org/1999/xhtml"><body>'
                + inner
                + "</body></html>"
            )

    def test_creator_refines_epub3(self, tmp_path):
        b = make_builder(tmp_path)
        self._write_chapter(b, "ch01.xhtml")
        chapters = [{"filename": "ch01.xhtml", "title": "C1"}]
        opf = b._content_opf(chapters, "", "ch01.xhtml")
        assert "opf:file-as" not in opf
        assert "opf:role" not in opf
        assert '<dc:creator id="creator01">Ada Lovelace</dc:creator>' in opf
        assert 'refines="#creator01" property="role"' in opf
        assert 'property="file-as">Lovelace, Ada<' in opf

    def test_optional_dc_omitted_when_empty(self, tmp_path):
        info = dict(INFO, rights="", description="")
        b = make_builder(tmp_path, info)
        self._write_chapter(b, "ch01.xhtml")
        opf = b._content_opf(
            [{"filename": "ch01.xhtml", "title": "C1"}], "", "ch01.xhtml"
        )
        assert "<dc:rights>" not in opf
        assert "<dc:description>" not in opf

    def test_mathml_and_svg_properties(self, tmp_path):
        b = make_builder(tmp_path)
        self._write_chapter(
            b,
            "ch01.xhtml",
            '<math xmlns="http://www.w3.org/1998/Math/MathML"><mi>x</mi></math>',
        )
        self._write_chapter(b, "ch02.xhtml", '<svg xmlns="..."></svg>')
        chapters = [
            {"filename": "ch01.xhtml", "title": "C1"},
            {"filename": "ch02.xhtml", "title": "C2"},
        ]
        opf = b._content_opf(chapters, "", "ch01.xhtml")
        assert (
            'href="ch01.xhtml" media-type="application/xhtml+xml" properties="mathml"'
            in opf
        )
        assert 'properties="svg"' in opf

    def test_remote_resources_only_for_embeds(self, tmp_path):
        b = make_builder(tmp_path)
        self._write_chapter(b, "ch01.xhtml", '<a href="https://example.com">link</a>')
        self._write_chapter(b, "ch02.xhtml", '<img src="https://example.com/i.png"/>')
        chapters = [
            {"filename": "ch01.xhtml", "title": "C1"},
            {"filename": "ch02.xhtml", "title": "C2"},
        ]
        opf = b._content_opf(chapters, "", "ch01.xhtml")
        ch01_item = re.search(r'<item[^>]*href="ch01\.xhtml"[^>]*/>', opf).group(0)
        ch02_item = re.search(r'<item[^>]*href="ch02\.xhtml"[^>]*/>', opf).group(0)
        assert "remote-resources" not in ch01_item
        assert "remote-resources" in ch02_item

    def test_spine_toc_ncx(self, tmp_path):
        b = make_builder(tmp_path)
        self._write_chapter(b, "ch01.xhtml")
        opf = b._content_opf(
            [{"filename": "ch01.xhtml", "title": "C1"}], "", "ch01.xhtml"
        )
        assert '<spine toc="ncx">' in opf

    def test_same_stem_assets_get_distinct_ids(self, tmp_path):
        """cover.png + cover.svg must not both get id="img_cover"."""
        b = make_builder(tmp_path)
        b.write_image("cover.png", b"\x89PNG")
        b.write_image("cover.svg", b"<svg/>")
        self._write_chapter(b, "ch01.xhtml")
        opf = b._content_opf(
            [{"filename": "ch01.xhtml", "title": "C1"}], "", "ch01.xhtml"
        )
        assert 'id="img_cover-png"' in opf
        assert 'id="img_cover-svg"' in opf
        ids = re.findall(r'<item id="([^"]+)"', opf)
        assert len(ids) == len(set(ids))

    def test_manifest_skips_dotfiles_and_tmp(self, tmp_path):
        """finalize()'s zip walk excludes dotfiles and .tmp leftovers, so
        the manifest must too — otherwise items point at missing files."""
        b = make_builder(tmp_path)
        for junk in (".DS_Store", "stray.png.tmp"):
            with open(os.path.join(b.images_path, junk), "w") as f:
                f.write("x")
            with open(os.path.join(b.fonts_path, junk), "w") as f:
                f.write("x")
            with open(os.path.join(b.css_path, junk), "w") as f:
                f.write("x")
        b.write_image("cover.png", b"\x89PNG")
        self._write_chapter(b, "ch01.xhtml")
        opf = b._content_opf(
            [{"filename": "ch01.xhtml", "title": "C1"}],
            "Images/cover.png",
            "ch01.xhtml",
        )
        assert ".DS_Store" not in opf
        assert ".tmp" not in opf
        assert 'href="Images/cover.png"' in opf

    def test_asset_hrefs_are_percent_encoded(self, tmp_path):
        """A filename with spaces/& is legal in the zip — the manifest href
        must be a valid URI (percent-encoded) and the id an NCName."""
        b = make_builder(tmp_path)
        b.write_image("a b&c.png", b"\x89PNG")
        self._write_chapter(b, "ch01.xhtml")
        opf = b._content_opf(
            [{"filename": "ch01.xhtml", "title": "C1"}], "", "ch01.xhtml"
        )
        assert 'href="Images/a%20b%26c.png"' in opf
        assert 'id="img_a_b_c-png"' in opf

    def test_cover_meta_only_when_cover_exists(self, tmp_path):
        """<meta name="cover"> with an empty content ref is a dangling
        pointer — omit it when the book has no cover image."""
        b = make_builder(tmp_path)
        self._write_chapter(b, "ch01.xhtml")
        chapters = [{"filename": "ch01.xhtml", "title": "C1"}]
        opf = b._content_opf(chapters, "", "ch01.xhtml")
        assert 'name="cover"' not in opf
        b.write_image("cover.png", b"\x89PNG")
        opf = b._content_opf(chapters, "Images/cover.png", "ch01.xhtml")
        assert '<meta name="cover" content="img_cover-png"/>' in opf

    def test_nav_chapter_filename_does_not_clash(self, tmp_path):
        """A chapter literally named nav.xhtml must not reuse the nav
        manifest id — spine and manifest stay consistent either way."""
        b = make_builder(tmp_path)
        self._write_chapter(b, "nav.xhtml")
        opf = b._content_opf(
            [{"filename": "nav.xhtml", "title": "Nav Ch"}], "", "nav.xhtml"
        )
        assert 'id="nav" href="nav.xhtml" media-type="application/xhtml+xml"' in opf
        assert 'id="chapter_nav"' in opf
        assert '<itemref idref="chapter_nav"/>' in opf


class TestItemId:
    def test_ids_are_ncnames(self):
        """Manifest ids are xsd:ID — no leading digit, no spaces, no &."""
        for name, iid in (
            ("ch01.html", "ch01"),
            ("a.b.html", "a.b"),
            ("3d-models.html", "_3d-models"),
            ("my ch.html", "my_ch"),
            (".html", "item"),
        ):
            result = _item_id(name)
            assert result == iid
            assert re.fullmatch(r"[A-Za-z_][\w.-]*", result), (name, result)

    def test_dot_stems_do_not_collapse(self):
        """Old join-stripped stems let a.b.html and ab.html share an id."""
        assert _item_id("a.b.html") != _item_id("ab.html")


class TestNavXhtml:
    def test_bodymatter_points_at_first_chapter_without_cover(self):
        """With no cover page, Start of Content is the first chapter —
        not the second."""
        b = make_builder("/tmp/x")
        chapters = [
            {"filename": "ch01.html", "title": "One"},
            {"filename": "ch02.html", "title": "Two"},
        ]
        nav = b._nav_xhtml([], chapters)
        assert '<a epub:type="bodymatter" href="ch01.xhtml">' in nav

    def test_bodymatter_skips_cover(self):
        b = make_builder("/tmp/x")
        chapters = [
            {"filename": "cover.html", "title": "Cover"},
            {"filename": "ch01.html", "title": "One"},
        ]
        nav = b._nav_xhtml([], chapters)
        assert '<a epub:type="bodymatter" href="ch01.xhtml">' in nav


def test_epub_href():
    assert _epub_href("ch01.html") == "ch01.xhtml"
    assert _epub_href("dir/ch01.html") == "ch01.xhtml"
    assert _epub_href("ch01.xhtml") == "ch01.xhtml"


class TestFinalize:
    def test_zip_excludes_work_dir_junk(self, tmp_path):
        """.cache/, web/ and dotfiles in work_dir must not ship in the EPUB."""
        b = make_builder(tmp_path)
        for junk in (
            os.path.join(b.work_dir, ".cache", "ch01.html"),
            os.path.join(b.work_dir, "web", "ch01.html"),
            os.path.join(b.work_dir, ".DS_Store"),
            os.path.join(b.oebps, "Images", ".DS_Store"),
        ):
            os.makedirs(os.path.dirname(junk), exist_ok=True)
            with open(junk, "w") as f:
                f.write("x")
        b.write_chapter(
            "ch01.xhtml",
            '<?xml version="1.0"?><html'
            ' xmlns="http://www.w3.org/1999/xhtml"><body/></html>',
        )
        epub = str(tmp_path / "book.epub")
        b.finalize([{"filename": "ch01.xhtml", "title": "C1"}], toc_items(), "", epub)
        names = zipfile.ZipFile(epub).namelist()
        assert "mimetype" in names
        assert names[0] == "mimetype"
        assert all(
            n == "mimetype" or n.startswith(("META-INF/", "OEBPS/")) for n in names
        ), names

    def test_every_manifest_href_exists_in_zip(self, tmp_path):
        """Manifest/zip parity — every declared href (after URI-decoding)
        must name a file that actually shipped."""
        b = make_builder(tmp_path)
        b.write_chapter(
            "ch01.xhtml",
            '<?xml version="1.0"?><html'
            ' xmlns="http://www.w3.org/1999/xhtml"><body/></html>',
        )
        b.write_image("my pic.png", b"\x89PNG")
        with open(os.path.join(b.images_path, ".DS_Store"), "w") as f:
            f.write("x")
        epub = str(tmp_path / "book.epub")
        b.finalize(
            [{"filename": "ch01.xhtml", "title": "C1"}],
            toc_items(),
            "Images/my pic.png",
            epub,
        )
        zf = zipfile.ZipFile(epub)
        shipped = set(zf.namelist())
        opf = zf.read("OEBPS/content.opf").decode()
        hrefs = re.findall(r'<item[^>]*href="([^"]+)"', opf)
        assert hrefs
        for href in hrefs:
            assert "OEBPS/" + unquote(href) in shipped, href
