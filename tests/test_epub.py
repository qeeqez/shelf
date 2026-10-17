"""Tests for epub.py NCX/OPF generation."""

import os
import re
import zipfile

from lxml import etree

from shelf.epub import EpubBuilder, _epub_href

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
        ncx = b._toc_ncx(toc_items())
        root = etree.fromstring(ncx.encode())
        ns = "http://www.daisy.org/z3986/2005/ncx/"
        by_src = {}
        for np in root.iter(f"{{{ns}}}navPoint"):
            src = np.find(f"{{{ns}}}content").get("src")
            by_src.setdefault(src, set()).add(np.get("playOrder"))
        assert all(len(v) == 1 for v in by_src.values())

    def test_uid_matches_identifier(self):
        b = make_builder("/tmp/x")
        ncx = b._toc_ncx(toc_items())
        assert 'content="1234567890" name="dtb:uid"' in ncx
        assert "ID:ISBN:" not in ncx

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
