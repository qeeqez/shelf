"""Assemble downloaded chapters/assets into a valid EPUB file."""

import os
import zipfile
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
CONTENT_OPF = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid" version="2.0" >\n'
    '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/" '
    ' xmlns:opf="http://www.idpf.org/2007/opf">\n'
    "<dc:title>{1}</dc:title>\n{2}\n<dc:description>{3}</dc:description>\n{4}"
    "<dc:publisher>{5}</dc:publisher>\n"
    "<dc:rights>{6}</dc:rights>\n"
    "<dc:language>en-US</dc:language>\n"
    "<dc:date>{7}</dc:date>\n"
    '<dc:identifier id="bookid">{0}</dc:identifier>\n'
    '<meta name="cover" content="{8}"/>\n'
    "</metadata>\n<manifest>\n"
    '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml" />\n'
    '{9}\n</manifest>\n<spine toc="ncx">\n{10}</spine>\n'
    '<guide><reference href="{11}" title="Cover" type="cover" /></guide>\n'
    "</package>"
)

# {0}=id {1}=depth {2}=title {3}=author {4}=navmap
TOC_NCX = (
    '<?xml version="1.0" encoding="utf-8" standalone="no" ?>\n'
    '<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN"'
    ' "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">\n'
    '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n'
    "<head>\n"
    '<meta content="ID:ISBN:{0}" name="dtb:uid"/>\n'
    '<meta content="{1}" name="dtb:depth"/>\n'
    '<meta content="0" name="dtb:totalPageCount"/>\n'
    '<meta content="0" name="dtb:maxPageNumber"/>\n'
    "</head>\n"
    "<docTitle><text>{2}</text></docTitle>\n"
    "<docAuthor><text>{3}</text></docAuthor>\n"
    "<navMap>{4}</navMap>\n"
    "</ncx>"
)

IMAGE_MEDIA_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "svg": "image/svg+xml",
    "webp": "image/webp",
}


def _item_id(filename):
    return escape("".join(filename.split(".")[:-1]))


def _image_media_type(filename):
    ext = filename.rsplit(".", 1)[-1].lower()
    return IMAGE_MEDIA_TYPES.get(ext, "image/" + ext)


class EpubBuilder:
    def __init__(self, book_info, book_id, work_dir):
        self.book_info = book_info
        self.book_id = book_id
        self.work_dir = work_dir
        self.oebps = os.path.join(work_dir, "OEBPS")
        self.images_path = os.path.join(self.oebps, "Images")
        self.css_path = os.path.join(self.oebps, "Styles")
        for d in (
            self.oebps,
            self.images_path,
            self.css_path,
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
        with open(os.path.join(self.css_path, f"Style{index:0>2}.css"), "wb") as f:
            f.write(content)

    def write_image(self, name, content):
        with open(os.path.join(self.images_path, name), "wb") as f:
            f.write(content)

    # -- metadata writers --------------------------------------------------------

    def _content_opf(self, chapters, cover_src, first_chapter):
        manifest = [
            '<item id="{}" href="{}" media-type="application/xhtml+xml" />'.format(
                _item_id(c["filename"]), c["filename"]
            )
            for c in chapters
        ]
        spine = [
            '<itemref idref="{}"/>'.format(_item_id(c["filename"])) for c in chapters
        ]

        for name in sorted(set(os.listdir(self.images_path))):
            manifest.append(
                '<item id="img_{}" href="Images/{}" media-type="{}" />'.format(
                    escape("".join(name.split(".")[:-1])), name, _image_media_type(name)
                )
            )
        for i, name in enumerate(sorted(os.listdir(self.css_path))):
            manifest.append(
                f'<item id="style_{i:0>2}" href="Styles/{name}" '
                'media-type="text/css" />'
            )

        authors = "\n".join(
            '<dc:creator opf:file-as="{0}" opf:role="aut">{0}</dc:creator>'.format(
                escape(a)
            )
            for a in self.book_info.get("authors", [])
        )
        subjects = "\n".join(
            f"<dc:subject>{escape(s)}</dc:subject>"
            for s in self.book_info.get("subjects", [])
        )
        cover_id = (
            "img_" + escape("".join(os.path.basename(cover_src).split(".")[:-1]))
            if cover_src
            else ""
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
            first_chapter,
        )

    def _parse_toc(self, items, counter=0, max_depth=0):
        result = ""
        for item in items:
            counter += 1
            max_depth = max(max_depth, int(item["depth"]))
            result += (
                '<navPoint id="{}" playOrder="{}">'
                "<navLabel><text>{}</text></navLabel>"
                '<content src="{}"/>'.format(
                    item["fragment"] if item["fragment"] else item["id"],
                    counter,
                    escape(item["label"]),
                    item["href"].replace(".html", ".xhtml").split("/")[-1],
                )
            )
            if item["children"]:
                sub, counter, max_depth = self._parse_toc(
                    item["children"], counter, max_depth
                )
                result += sub
            result += "</navPoint>\n"
        return result, counter, max_depth

    def _toc_ncx(self, toc_items):
        navmap, _, max_depth = self._parse_toc(toc_items)
        return TOC_NCX.format(
            escape(self.book_info.get("isbn") or self.book_id),
            max_depth,
            escape(self.book_info["title"]),
            escape(", ".join(self.book_info.get("authors", []))),
            navmap,
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
