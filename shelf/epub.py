"""Assemble downloaded chapters/assets into a valid EPUB 3 file."""

import os
import re
import zipfile
from datetime import UTC, datetime
from html import unescape
from urllib.parse import quote
from xml.sax.saxutils import escape

CONTAINER_XML = (
    '<?xml version="1.0"?>'
    '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
    "<rootfiles>"
    '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml" />'
    "</rootfiles>"
    "</container>"
)

# {0}=id {1}=title {2}=authors {8}=cover-meta {9}=manifest {10}=spine
# {11}=cover-href {12}=dcterms:modified {13}=optional dc + identifier metas
# {14}=a11y metas {15}=language
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
    "{14}"
    '<meta property="ibooks:specified-fonts">true</meta>\n'
    "{8}"
    "</metadata>\n<manifest>\n"
    '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml"'
    ' properties="nav"/>\n'
    '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>\n'
    '{9}\n</manifest>\n<spine toc="ncx">\n{10}</spine>\n'
    '<guide><reference href="nav.xhtml" title="Table of Contents" type="toc"/>'
    '<reference href="{11}" title="Cover" type="cover"/></guide>\n'
    "</package>"
)

# {0}=id {1}=depth {2}=title {3}=author {4}=navmap {5}=totalPages
# {6}=maxPageNumber {7}=pageList
TOC_NCX = (
    '<?xml version="1.0" encoding="utf-8" standalone="no" ?>\n'
    '<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN"'
    ' "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">\n'
    '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n'
    "<head>\n"
    '<meta content="{0}" name="dtb:uid"/>\n'
    '<meta content="{1}" name="dtb:depth"/>\n'
    '<meta content="{5}" name="dtb:totalPageCount"/>\n'
    '<meta content="{6}" name="dtb:maxPageNumber"/>\n'
    "</head>\n"
    "<docTitle><text>{2}</text></docTitle>\n"
    "<docAuthor><text>{3}</text></docAuthor>\n"
    "<navMap>{4}</navMap>\n"
    "{7}"
    "</ncx>"
)

# {0}=title {1}=toc-ol {2}=landmarks-ol {3}=lang {4}=page-list nav or ""
NAV_XHTML = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    "<!DOCTYPE html>\n"
    '<html xmlns="http://www.w3.org/1999/xhtml" lang="{3}" xml:lang="{3}"'
    ' xmlns:epub="http://www.idpf.org/2007/ops">\n'
    '<head><meta charset="utf-8"/><title>{0}</title></head>\n'
    "<body>\n"
    '<nav epub:type="toc" id="toc">\n<h1>{0}</h1>\n{1}</nav>\n'
    '<nav epub:type="landmarks" hidden="hidden">\n'
    "<h1>Landmarks</h1>\n<ol>\n{2}</ol>\n</nav>\n"
    "{4}"
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

# Formats that deflate can't shrink — stored raw so zipping stays cheap.
STORED_SUFFIXES = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".woff",
    ".woff2",
    ".mp3",
    ".mp4",
    ".zip",
)

FONT_MEDIA_TYPES = {
    "ttf": "font/ttf",
    "otf": "font/otf",
    "woff": "font/woff",
    "woff2": "font/woff2",
    "ttc": "font/ttf",
    "otc": "font/otf",
    "sfnt": "font/sfnt",
}

# epub:type values → landmarks nav entries (reader "Go to" menus)
LANDMARK_TYPES = {
    "cover": "cover",
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


def _ncname(text):
    # Manifest/spine ids must match NCName: word characters, dots and
    # hyphens survive, anything else becomes "_" and a leading non-letter
    # (digit, hyphen, dot) gets a "_" prefix.
    iid = re.sub(r"[^.\w-]", "_", text) or "item"
    return iid if iid[0].isalpha() or iid[0] == "_" else "_" + iid


def _item_id(filename):
    iid = _ncname(filename.rsplit(".", 1)[0])
    # A chapter literally named nav.xhtml/ncx.xhtml would collide with the
    # fixed nav/ncx manifest item ids.
    return "chapter_" + iid if iid in ("nav", "ncx") else iid


def _asset_id(name):
    # Include the extension so same-stem files (cover.png + cover.svg,
    # font.ttf + font.otf) can't produce duplicate manifest ids.
    return _ncname(name.replace(".", "-"))


def _asset_names(path):
    # Dotfiles and interrupted-write .tmp leftovers are skipped by
    # finalize()'s zip walk, so they must not reach the manifest either.
    return sorted(
        n for n in os.listdir(path) if not n.startswith(".") and not n.endswith(".tmp")
    )


def _image_media_type(filename):
    ext = filename.rsplit(".", 1)[-1].lower()
    return IMAGE_MEDIA_TYPES.get(ext, "image/" + ext)


def _epub_href(filename):
    return filename.replace(".html", ".xhtml").split("/")[-1]


def _epub_uri(filename, fragment=""):
    # href/src values are URIs: percent-encode so filenames or fragments
    # containing spaces, "&" or quotes stay valid URIs and well-formed XML
    # attribute values.
    uri = quote(_epub_href(filename))
    if fragment:
        uri += "#" + quote(fragment)
    return uri


def _plain_text(markup):
    # The API embeds HTML markup in the description, but readers render
    # dc:description as flat text — strip tags (entity-escaped text like
    # "&lt;b&gt;" is meant literally, so unescape only after stripping),
    # collapse the whitespace paragraphs leave behind and close the gap a
    # removed inline tag leaves before punctuation.
    text = " ".join(unescape(re.sub(r"<[^>]+>", " ", markup or "")).split())
    return re.sub(r" ([,.;:!?)\]])", r"\1", text)


class EpubBuilder:
    def __init__(self, book_info, book_id, work_dir):
        self.book_info = book_info
        self.book_id = book_id
        self.work_dir = work_dir
        self.oebps = os.path.join(work_dir, "OEBPS")
        self.images_path = os.path.join(self.oebps, "Images")
        self.css_path = os.path.join(self.oebps, "Styles")
        self.fonts_path = os.path.join(self.oebps, "Fonts")
        # Populated by the downloader during transform so manifest/nav
        # generation doesn't re-read every chapter file. Missing entries fall
        # back to scanning the file on disk (resume path).
        self.chapter_props = {}
        self.chapter_types = {}
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

    @staticmethod
    def _atomic_write(path, content):
        # Write-then-rename so an interrupted run can't leave a partial file
        # that resume would mistake for complete.
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(content)
        os.replace(tmp, path)

    def write_chapter(self, filename, rendered_html):
        self._atomic_write(
            self.chapter_path(filename),
            rendered_html.encode("utf-8", "xmlcharrefreplace"),
        )

    def write_css(self, index, content):
        self.write_named_css(f"Style{index:0>2}.css", content)

    def write_named_css(self, name, content):
        self._atomic_write(
            os.path.join(self.css_path, name),
            content if isinstance(content, bytes) else content.encode(),
        )

    def write_font(self, name, content):
        self._atomic_write(os.path.join(self.fonts_path, name), content)

    def write_image(self, name, content):
        self._atomic_write(os.path.join(self.images_path, name), content)

    # -- metadata writers --------------------------------------------------------

    def _content_opf(self, chapters, cover_src, first_chapter):
        manifest = []
        has_mathml = False
        has_index = False
        for c in chapters:
            name = _epub_href(c["filename"])
            if self._chapter_epub_type(c["filename"]) == "index":
                has_index = True
            props = self.chapter_props.get(name)
            if props is None:
                props = []
                path = self.chapter_path(name)
                try:
                    with open(path, encoding="utf-8", errors="replace") as f:
                        data = f.read()
                    if "<math" in data:
                        props.append("mathml")
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
                self.chapter_props[name] = props
            if "mathml" in props:
                has_mathml = True
            props_attr = ' properties="' + " ".join(props) + '"' if props else ""
            manifest.append(
                '<item id="{}" href="{}" media-type="application/xhtml+xml"{}/>'.format(
                    _item_id(c["filename"]), _epub_uri(c["filename"]), props_attr
                )
            )
        spine = [f'<itemref idref="{_item_id(c["filename"])}"/>' for c in chapters]

        cover_name = os.path.basename(cover_src) if cover_src else ""
        for name in _asset_names(self.images_path):
            props = ' properties="cover-image"' if name == cover_name else ""
            manifest.append(
                f'<item id="img_{_asset_id(name)}" href="Images/{quote(name)}"'
                f' media-type="{_image_media_type(name)}"{props}/>'
            )
        for name in _asset_names(self.fonts_path):
            ext = name.rsplit(".", 1)[-1].lower()
            media_type = FONT_MEDIA_TYPES.get(ext, f"font/{ext}")
            manifest.append(
                f'<item id="font_{_asset_id(name)}" href="Fonts/{quote(name)}"'
                f' media-type="{media_type}"/>'
            )
        for i, name in enumerate(_asset_names(self.css_path)):
            manifest.append(
                f'<item id="style_{i:0>2}" href="Styles/{quote(name)}"'
                ' media-type="text/css"/>'
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
        cover_id = "img_" + _asset_id(os.path.basename(cover_src)) if cover_src else ""
        # EPUB2-style cover meta must point at a real manifest item — an
        # empty content attribute is a dangling reference epubcheck rejects.
        cover_meta = f'<meta name="cover" content="{cover_id}"/>\n' if cover_id else ""
        optional_dc = []
        if self.book_info.get("issued"):
            optional_dc.append(f"<dc:date>{escape(self.book_info['issued'])}</dc:date>")
        if self.book_info.get("description"):
            optional_dc.append(
                "<dc:description>{}</dc:description>".format(
                    escape(_plain_text(self.book_info["description"]))
                )
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
        ident, refine = self._identifier()
        optional_dc = [
            m for m in (refine, self._secondary_identifier(ident)) if m
        ] + optional_dc
        modified = self.book_info.get("modified") or datetime.now(UTC).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

        # EPUB Accessibility discovery metadata: one <meta> per schema.org
        # value (the spec form — some tools don't split comma-joined
        # values). 100% image alt coverage in the source chapters backs the
        # alternativeText feature and the "textual" sufficient mode.
        features = ["alternativeText", "structuralNavigation", "tableOfContents"]
        if has_mathml:
            features.append("MathML")
        if has_index:
            features.append("index")
        if self._page_list(chapters):
            features.append("pageNavigation")
        a11y = "".join(
            f'<meta property="schema:accessibilityFeature">{f}</meta>\n'
            for f in features
        )
        a11y += (
            '<meta property="schema:accessMode">textual</meta>\n'
            '<meta property="schema:accessMode">visual</meta>\n'
            '<meta property="schema:accessModeSufficient">textual</meta>\n'
            '<meta property="schema:accessibilityHazard">none</meta>\n'
            '<meta property="schema:accessibilitySummary">This publication'
            " includes alternative text for images and supports structural"
            " navigation.</meta>\n"
        )

        return CONTENT_OPF.format(
            escape(ident),
            escape(self.book_info["title"]),
            authors,
            escape(self.book_info.get("description", "")),
            subjects,
            escape(", ".join(self.book_info.get("publishers", []))),
            escape(self.book_info.get("rights", "")),
            self.book_info.get("issued", ""),
            cover_meta,
            "\n".join(manifest),
            "\n".join(spine),
            _epub_uri(first_chapter),
            modified,
            "\n".join(optional_dc) + "\n",
            a11y,
            escape(self.book_info.get("language") or "en"),
        )

    def _first_href(self, item):
        """First href in this subtree — container headings carry no href of
        their own, so NCX navPoints point at the first child that has one."""
        if item["href"]:
            return _epub_uri(item["href"], item["fragment"])
        for child in item["children"]:
            found = self._first_href(child)
            if found:
                return found
        return ""

    def _parse_toc_ncx(self, items, counter=0, max_depth=0, playorders=None, level=1):
        if playorders is None:
            playorders = {}
        result = ""
        for item in items:
            counter += 1
            # Children are numbered after this item, so capture its id and
            # playOrder number before recursing.
            own = counter
            src = self._first_href(item)
            sub = ""
            if item["children"]:
                # A skipped (unresolvable) item emits no navPoint, so its
                # children sit at this item's level in the navMap.
                child_level = level + 1 if src else level
                sub, counter, max_depth = self._parse_toc_ncx(
                    item["children"], counter, max_depth, playorders, child_level
                )
            if not src:
                # Nothing in this subtree resolves to a file — emit any
                # resolvable children but no <content src=""> navPoint shell.
                result += sub
                continue
            # dtb:depth is the navMap's structural depth, not the listing's
            # depth field — the two disagree when the API flattens a level.
            max_depth = max(max_depth, level)
            # len(playorders) counts emitted navPoints, so playOrders stay
            # gap-free even when an item is skipped or a src repeats.
            playorder = playorders.setdefault(src, len(playorders) + 1)
            result += (
                '<navPoint id="navpoint-{}" playOrder="{}">'
                "<navLabel><text>{}</text></navLabel>"
                '<content src="{}"/>'.format(
                    own,
                    playorder,
                    escape(item["label"]),
                    src,
                )
            )
            result += sub + "</navPoint>\n"
        return result, counter, max_depth

    def _identifier(self):
        """(identifier string, refinement <meta> or ""). urn:isbn + ONIX
        identifier-type so library tools recognise it; NCX dtb:uid must equal
        dc:identifier, so both writers go through here."""
        isbn = self.book_info.get("isbn")
        digits = re.sub(r"[^0-9Xx]", "", isbn) if isbn else ""
        if len(digits) in (10, 13):
            code = "15" if len(digits) == 13 else "02"
            return (
                f"urn:isbn:{isbn}",
                (
                    '<meta refines="#bookid" property="identifier-type"'
                    f' scheme="onix:codelist5">{code}</meta>'
                ),
            )
        return self.book_info.get("identifier") or f"urn:orm:book:{self.book_id}", ""

    def _secondary_identifier(self, primary):
        """book_info carries the O'Reilly catalog id (`identifier`, the
        ebook ISBN on ISBN-shaped values) alongside the print `isbn`, but
        only the isbn reaches the OPF. Emit it as a second dc:identifier so
        library tools can cross-reference both."""
        raw = (self.book_info.get("identifier") or "").strip()
        if not raw or raw == primary:
            return ""
        digits = re.sub(r"[^0-9Xx]", "", raw)
        isbn_digits = re.sub(r"[^0-9Xx]", "", self.book_info.get("isbn") or "")
        if digits and digits == isbn_digits:
            return ""
        urn = f"urn:isbn:{raw}" if len(digits) in (10, 13) else f"urn:orm:book:{raw}"
        if urn == primary:
            return ""
        return f"<dc:identifier>{escape(urn)}</dc:identifier>"

    def _page_list(self, chapters):
        """(page label, filename) at each chapter start, from the API's
        per-chapter virtual_pages. Source HTML has no intra-chapter page
        anchors, so granularity is chapter starts; empty when the API gave
        no page counts (e.g. a cache written before this field existed)."""
        entries, page = [], 1
        for ch in chapters:
            entries.append((page, ch["filename"]))
            page += int(ch.get("virtual_pages") or 0)
        return entries if page > 1 else []

    def _toc_ncx(self, toc_items, chapters):
        # playorders maps each emitted content src to its playOrder, so its
        # length is the first free order for the pageTargets that follow.
        playorders = {}
        navmap, _, max_depth = self._parse_toc_ncx(toc_items, playorders=playorders)
        pages = self._page_list(chapters)
        page_list = ""
        if pages:
            targets = [
                f'<pageTarget id="pageTarget-{n}" type="normal" value="{n}"'
                f' playOrder="{len(playorders) + i}">'
                f"<navLabel><text>{n}</text></navLabel>"
                f'<content src="{_epub_uri(fname)}"/></pageTarget>'
                for i, (n, fname) in enumerate(pages, 1)
            ]
            page_list = (
                '<pageList id="pageList" class="pagelist">'
                "<navLabel><text>Pages</text></navLabel>"
                + "".join(targets)
                + "</pageList>\n"
            )
        total = sum(int(c.get("virtual_pages") or 0) for c in chapters)
        return TOC_NCX.format(
            escape(self._identifier()[0], {'"': "&quot;"}),
            max_depth,
            escape(self.book_info["title"]),
            escape(", ".join(self.book_info.get("authors", []))),
            navmap,
            total,
            total,
            page_list,
        )

    def _toc_ol(self, items):
        lis = []
        for item in items:
            children = self._toc_ol(item["children"]) if item["children"] else ""
            if item["href"]:
                href = _epub_uri(item["href"], item["fragment"])
                label = f'<a href="{href}">{escape(item["label"])}</a>'
            else:
                # Container heading with no target of its own — a span, not a
                # dead link (nav doc spec allows span for unlinked entries).
                label = f"<span>{escape(item['label'])}</span>"
            lis.append(f"<li>{label}{children}</li>")
        return "<ol>\n" + "\n".join(lis) + "\n</ol>"

    def _chapter_epub_type(self, filename):
        name = _epub_href(filename)
        etype = self.chapter_types.get(name)
        if etype is not None:
            return etype
        etype = ""
        try:
            with open(self.chapter_path(name), encoding="utf-8", errors="replace") as f:
                m = re.search(r'epub:type="([a-z-]+)"', f.read(65536))
                if m:
                    etype = m.group(1)
        except OSError:
            pass
        self.chapter_types[name] = etype
        return etype

    def _nav_xhtml(self, toc_items, chapters):
        landmarks = []
        if chapters:
            first = chapters[0]
            etype0 = self._chapter_epub_type(first["filename"])
            looks_cover = (
                etype0 == "cover"
                or "cover" in (first["filename"] + (first.get("title") or "")).lower()
            )
            seen_types = set()
            if looks_cover:
                seen_types.add("cover")
                landmarks.append(
                    f'<li><a epub:type="cover" '
                    f'href="{_epub_uri(first["filename"])}">Cover</a></li>'
                )
            for ch in chapters:
                etype = LANDMARK_TYPES.get(self._chapter_epub_type(ch["filename"]))
                if etype and etype not in seen_types:
                    seen_types.add(etype)
                    landmarks.append(
                        f'<li><a epub:type="{etype}" '
                        f'href="{_epub_uri(ch["filename"])}">'
                        f"{escape(ch['title'])}</a></li>"
                    )
            # "Start of Content" is the chapter after the cover — or the
            # first chapter itself when the book has no cover page.
            start = 1 if looks_cover else 0
            if len(chapters) > start:
                landmarks.append(
                    f'<li><a epub:type="bodymatter" '
                    f'href="{_epub_uri(chapters[start]["filename"])}">'
                    "Start of Content</a></li>"
                )
        page_nav = ""
        if self._page_list(chapters):
            lis = "".join(
                f'<li><a href="{_epub_uri(fname)}">{n}</a></li>\n'
                for n, fname in self._page_list(chapters)
            )
            page_nav = (
                '<nav epub:type="page-list" hidden="hidden">\n'
                f"<h1>Pages</h1>\n<ol>\n{lis}</ol>\n</nav>\n"
            )
        return NAV_XHTML.format(
            escape(self.book_info["title"]),
            self._toc_ol(toc_items),
            "\n".join(landmarks),
            escape(self.book_info.get("language") or "en", {'"': "&quot;"}),
            page_nav,
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
            f.write(
                self._toc_ncx(toc_items, chapters).encode("utf-8", "xmlcharrefreplace")
            )
        with open(os.path.join(self.oebps, "nav.xhtml"), "wb") as f:
            f.write(
                self._nav_xhtml(toc_items, chapters).encode(
                    "utf-8", "xmlcharrefreplace"
                )
            )

        if os.path.isfile(epub_path):
            os.remove(epub_path)
        # Deflate level 9: an EPUB is written once and read many times, so
        # pay the extra CPU now for a smaller artifact.
        with zipfile.ZipFile(epub_path, "w", compresslevel=9) as z:
            z.writestr(
                zipfile.ZipInfo("mimetype"),
                "application/epub+zip",
                compress_type=zipfile.ZIP_STORED,
            )
            # Only META-INF + OEBPS belong in the package; work_dir also holds
            # .cache/, web/ and OS junk (.DS_Store) that must not be zipped.
            for base in (os.path.join(self.work_dir, "META-INF"), self.oebps):
                for root, dirs, files in os.walk(base):
                    dirs[:] = [d for d in dirs if not d.startswith(".")]
                    for name in sorted(files):
                        if name.startswith(".") or name.endswith(".tmp"):
                            continue
                        full = os.path.join(root, name)
                        arc = os.path.relpath(full, self.work_dir)
                        # Already-compressed payloads gain nothing from
                        # deflate but still pay its CPU cost on every build.
                        ctype = (
                            zipfile.ZIP_STORED
                            if name.lower().endswith(STORED_SUFFIXES)
                            else zipfile.ZIP_DEFLATED
                        )
                        z.write(full, arc, compress_type=ctype)
        return epub_path
