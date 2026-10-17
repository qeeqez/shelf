"""Assemble downloaded chapters/assets into a valid EPUB 3 file."""

import os
import re
import zipfile
from datetime import UTC, datetime
from xml.sax.saxutils import escape

CONTAINER_XML = (
    '<?xml version="1.0"?>'
    '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
    "<rootfiles>"
    '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml" />'
    "</rootfiles>"
    "</container>"
)

# {0}=id {1}=title {2}=authors {3}=description {4}=subjects {5}=publisher
# {6}=rights {7}=date {8}=cover-meta-id {9}=manifest {10}=spine {11}=cover-href
# {12}=dcterms:modified
CONTENT_OPF = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid"'
    ' prefix="ibooks: http://vocabulary.itunes.apple.com/rdf/ibooks/'
    'vocabulary-extensions-1.0/" version="3.0">\n'
    '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"'
    ' xmlns:opf="http://www.idpf.org/2007/opf">\n'
    '<dc:identifier id="bookid">{0}</dc:identifier>\n'
    "<dc:title>{1}</dc:title>\n{2}\n"
    "<dc:language>{15}</dc:language>\n"
    "{13}"
    '<meta property="dcterms:modified">{12}</meta>\n'
    '<meta property="schema:accessMode">textual,visual</meta>\n'
    '<meta property="schema:accessibilityFeature">alternativeText,'
    "structuralNavigation,tableOfContents,index{14}</meta>\n"
    '<meta property="schema:accessibilityHazard">none</meta>\n'
    '<meta property="ibooks:specified-fonts">true</meta>\n'
    '<meta name="cover" content="{8}"/>\n'
    "</metadata>\n<manifest>\n"
    '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml"'
    ' properties="nav"/>\n'
    '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>\n'
    '{9}\n</manifest>\n<spine toc="ncx">\n{10}</spine>\n'
    '<guide><reference href="{11}" title="Cover" type="cover"/></guide>\n'
    "</package>"
)

# {0}=id {1}=depth {2}=title {3}=author {4}=navmap
TOC_NCX = (
    '<?xml version="1.0" encoding="utf-8" standalone="no" ?>\n'
    '<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN"'
    ' "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">\n'
    '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n'
    "<head>\n"
    '<meta content="{0}" name="dtb:uid"/>\n'
    '<meta content="{1}" name="dtb:depth"/>\n'
    '<meta content="0" name="dtb:totalPageCount"/>\n'
    '<meta content="0" name="dtb:maxPageNumber"/>\n'
    "</head>\n"
    "<docTitle><text>{2}</text></docTitle>\n"
    "<docAuthor><text>{3}</text></docAuthor>\n"
    "<navMap>{4}</navMap>\n"
    "</ncx>"
)

# {0}=title {1}=toc-ol {2}=landmarks-ol
NAV_XHTML = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    "<!DOCTYPE html>\n"
    '<html xmlns="http://www.w3.org/1999/xhtml"'
    ' xmlns:epub="http://www.idpf.org/2007/ops">\n'
    '<head><meta charset="utf-8"/><title>{0}</title></head>\n'
    "<body>\n"
    '<nav epub:type="toc" id="toc">\n<h1>{0}</h1>\n{1}</nav>\n'
    '<nav epub:type="landmarks" hidden="hidden">\n'
    "<h1>Landmarks</h1>\n<ol>\n{2}</ol>\n</nav>\n"
    "</body>\n</html>"
)

IMAGE_MEDIA_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "svg": "image/svg+xml",
    "webp": "image/webp",
}

FONT_MEDIA_TYPES = {
    "ttf": "font/ttf",
    "otf": "font/otf",
    "woff": "font/woff",
    "woff2": "font/woff2",
    "ttc": "font/ttf",
    "otc": "font/otf",
    "sfnt": "application/font-sfnt",
}

# epub:type values → landmarks nav entries (reader "Go to" menus)
LANDMARK_TYPES = {
    "titlepage": "title-page",
    "copyright-page": "copyright-page",
    "dedication": "dedication",
    "epigraph": "epigraph",
    "foreword": "foreword",
    "preface": "preface",
    "introduction": "introduction",
    "prologue": "prologue",
    "glossary": "glossary",
    "index": "index",
    "colophon": "colophon",
    "appendix": "appendix",
    "bibliography": "bibliography",
    "acknowledgments": "acknowledgments",
}


def _item_id(filename):
    return escape("".join(filename.split(".")[:-1]))


def _image_media_type(filename):
    ext = filename.rsplit(".", 1)[-1].lower()
    return IMAGE_MEDIA_TYPES.get(ext, "image/" + ext)


def _epub_href(filename):
    return filename.replace(".html", ".xhtml").split("/")[-1]


class EpubBuilder:
    def __init__(self, book_info, book_id, work_dir):
        self.book_info = book_info
        self.book_id = book_id
        self.work_dir = work_dir
        self.oebps = os.path.join(work_dir, "OEBPS")
        self.images_path = os.path.join(self.oebps, "Images")
        self.css_path = os.path.join(self.oebps, "Styles")
        self.fonts_path = os.path.join(self.oebps, "Fonts")
        for d in (
            self.oebps,
            self.images_path,
            self.css_path,
            self.fonts_path,
            os.path.join(work_dir, "META-INF"),
        ):
            os.makedirs(d, exist_ok=True)

    # -- asset writers -----------------------------------------------------------

    def chapter_path(self, filename):
        return os.path.join(self.oebps, filename)

    def has_chapter(self, filename):
        return os.path.isfile(self.chapter_path(filename))

    def write_chapter(self, filename, rendered_html):
        with open(self.chapter_path(filename), "wb") as f:
            f.write(rendered_html.encode("utf-8", "xmlcharrefreplace"))

    def write_css(self, index, content):
        self.write_named_css(f"Style{index:0>2}.css", content)

    def write_named_css(self, name, content):
        with open(os.path.join(self.css_path, name), "wb") as f:
            f.write(content if isinstance(content, bytes) else content.encode())

    def write_font(self, name, content):
        with open(os.path.join(self.fonts_path, name), "wb") as f:
            f.write(content)

    def write_image(self, name, content):
        with open(os.path.join(self.images_path, name), "wb") as f:
            f.write(content)

    # -- metadata writers --------------------------------------------------------

    def _content_opf(self, chapters, cover_src, first_chapter):
        manifest = []
        has_mathml = False
        for c in chapters:
            props = []
            path = self.chapter_path(_epub_href(c["filename"]))
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    data = f.read()
                if "<math" in data:
                    props.append("mathml")
                    has_mathml = True
                if "<svg" in data:
                    props.append("svg")
                if re.search(
                    r'(?:src|data|poster|xlink:href)\s*=\s*"https?://'
                    r"|url\(\s*[\"']?https?://",
                    data,
                ):
                    props.append("remote-resources")
            except OSError:
                pass
            props_attr = ' properties="' + " ".join(props) + '"' if props else ""
            manifest.append(
                '<item id="{}" href="{}" media-type="application/xhtml+xml"{}/>'.format(
                    _item_id(c["filename"]), _epub_href(c["filename"]), props_attr
                )
            )
        spine = [f'<itemref idref="{_item_id(c["filename"])}"/>' for c in chapters]

        cover_name = os.path.basename(cover_src) if cover_src else ""
        for name in sorted(set(os.listdir(self.images_path))):
            props = ' properties="cover-image"' if name == cover_name else ""
            manifest.append(
                '<item id="img_{}" href="Images/{}" media-type="{}"{}/>'.format(
                    escape("".join(name.split(".")[:-1])),
                    name,
                    _image_media_type(name),
                    props,
                )
            )
        for name in sorted(set(os.listdir(self.fonts_path))):
            ext = name.rsplit(".", 1)[-1].lower()
            media_type = FONT_MEDIA_TYPES.get(ext, f"font/{ext}")
            manifest.append(
                '<item id="font_{}" href="Fonts/{}" media-type="{}"/>'.format(
                    escape("".join(name.split(".")[:-1])), name, media_type
                )
            )
        for i, name in enumerate(sorted(os.listdir(self.css_path))):
            manifest.append(
                f'<item id="style_{i:0>2}" href="Styles/{name}" media-type="text/css"/>'
            )

        author_elems = []
        for i, a in enumerate(self.book_info.get("authors", [])):
            cid = f"creator{i + 1:02d}"
            author_elems.append(f'<dc:creator id="{cid}">{escape(a)}</dc:creator>')
            author_elems.append(
                f'<meta refines="#{cid}" property="role"'
                ' scheme="marc:relators">aut</meta>'
            )
            parts = a.split()
            if len(parts) > 1:
                file_as = f"{parts[-1]}, {' '.join(parts[:-1])}"
                author_elems.append(
                    f'<meta refines="#{cid}" property="file-as">'
                    f"{escape(file_as)}</meta>"
                )
        authors = "\n".join(author_elems)
        subjects = "\n".join(
            f"<dc:subject>{escape(s)}</dc:subject>"
            for s in self.book_info.get("subjects", [])
        )
        cover_id = (
            "img_" + escape("".join(os.path.basename(cover_src).split(".")[:-1]))
            if cover_src
            else ""
        )
        optional_dc = []
        if self.book_info.get("issued"):
            optional_dc.append(f"<dc:date>{escape(self.book_info['issued'])}</dc:date>")
        if self.book_info.get("description"):
            optional_dc.append(
                f"<dc:description>{escape(self.book_info['description'])}</dc:description>"
            )
        optional_dc.append(subjects)
        if self.book_info.get("publishers"):
            optional_dc.append(
                "<dc:publisher>{}</dc:publisher>".format(
                    escape(", ".join(self.book_info["publishers"]))
                )
            )
        if self.book_info.get("rights"):
            optional_dc.append(
                f"<dc:rights>{escape(self.book_info['rights'])}</dc:rights>"
            )
        modified = self.book_info.get("modified") or datetime.now(UTC).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

        return CONTENT_OPF.format(
            escape(self.book_info.get("isbn") or self.book_id),
            escape(self.book_info["title"]),
            authors,
            escape(self.book_info.get("description", "")),
            subjects,
            escape(", ".join(self.book_info.get("publishers", []))),
            escape(self.book_info.get("rights", "")),
            self.book_info.get("issued", ""),
            cover_id,
            "\n".join(manifest),
            "\n".join(spine),
            _epub_href(first_chapter),
            modified,
            "\n".join(optional_dc) + "\n",
            ",MathML" if has_mathml else "",
            escape(self.book_info.get("language") or "en-US"),
        )

    def _parse_toc_ncx(self, items, counter=0, max_depth=0, playorders=None):
        if playorders is None:
            playorders = {}
        result = ""
        for item in items:
            counter += 1
            max_depth = max(max_depth, int(item["depth"]))
            src = _epub_href(item["href"])
            if item["fragment"]:
                src += "#" + item["fragment"]
            playorder = playorders.setdefault(src, counter)
            result += (
                '<navPoint id="navpoint-{}" playOrder="{}">'
                "<navLabel><text>{}</text></navLabel>"
                '<content src="{}"/>'.format(
                    counter,
                    playorder,
                    escape(item["label"]),
                    escape(src),
                )
            )
            if item["children"]:
                sub, counter, max_depth = self._parse_toc_ncx(
                    item["children"], counter, max_depth, playorders
                )
                result += sub
            result += "</navPoint>\n"
        return result, counter, max_depth

    def _toc_ncx(self, toc_items):
        navmap, _, max_depth = self._parse_toc_ncx(toc_items)
        return TOC_NCX.format(
            escape(self.book_info.get("isbn") or self.book_id),
            max_depth,
            escape(self.book_info["title"]),
            escape(", ".join(self.book_info.get("authors", []))),
            navmap,
        )

    def _toc_ol(self, items):
        lis = []
        for item in items:
            href = _epub_href(item["href"])
            if item["fragment"]:
                href += "#" + item["fragment"]
            children = self._toc_ol(item["children"]) if item["children"] else ""
            lis.append(
                f'<li><a href="{escape(href)}">'
                f"{escape(item['label'])}</a>{children}</li>"
            )
        return "<ol>\n" + "\n".join(lis) + "\n</ol>"

    def _chapter_epub_type(self, filename):
        try:
            with open(
                self.chapter_path(_epub_href(filename)),
                encoding="utf-8",
                errors="replace",
            ) as f:
                m = re.search(r'epub:type="([a-z-]+)"', f.read(65536))
                return m.group(1) if m else ""
        except OSError:
            return ""

    def _nav_xhtml(self, toc_items, chapters):
        landmarks = []
        if chapters:
            landmarks.append(
                f'<li><a epub:type="cover" '
                f'href="{_epub_href(chapters[0]["filename"])}">Cover</a></li>'
            )
            seen_types = set()
            for ch in chapters:
                etype = LANDMARK_TYPES.get(self._chapter_epub_type(ch["filename"]))
                if etype and etype not in seen_types:
                    seen_types.add(etype)
                    landmarks.append(
                        f'<li><a epub:type="{etype}" '
                        f'href="{_epub_href(ch["filename"])}">'
                        f"{escape(ch['title'])}</a></li>"
                    )
            if len(chapters) > 1:
                landmarks.append(
                    f'<li><a epub:type="bodymatter" '
                    f'href="{_epub_href(chapters[1]["filename"])}">'
                    "Start of Content</a></li>"
                )
        return NAV_XHTML.format(
            escape(self.book_info["title"]),
            self._toc_ol(toc_items),
            "\n".join(landmarks),
        )

    # -- final assembly -------------------------------------------------------------

    def finalize(self, chapters, toc_items, cover_src, epub_path):
        with open(os.path.join(self.work_dir, "mimetype"), "w") as f:
            f.write("application/epub+zip")
        with open(os.path.join(self.work_dir, "META-INF", "container.xml"), "wb") as f:
            f.write(CONTAINER_XML.encode("utf-8", "xmlcharrefreplace"))
        with open(os.path.join(self.oebps, "content.opf"), "wb") as f:
            f.write(
                self._content_opf(chapters, cover_src, chapters[0]["filename"]).encode(
                    "utf-8", "xmlcharrefreplace"
                )
            )
        with open(os.path.join(self.oebps, "toc.ncx"), "wb") as f:
            f.write(self._toc_ncx(toc_items).encode("utf-8", "xmlcharrefreplace"))
        with open(os.path.join(self.oebps, "nav.xhtml"), "wb") as f:
            f.write(
                self._nav_xhtml(toc_items, chapters).encode(
                    "utf-8", "xmlcharrefreplace"
                )
            )

        if os.path.isfile(epub_path):
            os.remove(epub_path)
        with zipfile.ZipFile(epub_path, "w") as z:
            z.writestr(
                zipfile.ZipInfo("mimetype"),
                "application/epub+zip",
                compress_type=zipfile.ZIP_STORED,
            )
            for root, _, files in os.walk(self.work_dir):
                for name in sorted(files):
                    full = os.path.join(root, name)
                    arc = os.path.relpath(full, self.work_dir)
                    if arc == "mimetype":
                        continue
                    z.write(full, arc, compress_type=zipfile.ZIP_DEFLATED)
        return epub_path
