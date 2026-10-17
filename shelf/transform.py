"""Convert O'Reilly reader pages into standalone EPUB XHTML documents."""

import pathlib
from urllib.parse import urljoin, urlparse
from xml.sax.saxutils import escape

from lxml import etree, html

PAGE_HEAD = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    "<!DOCTYPE html>\n"
    '<html lang="{lang}" xml:lang="{lang}" xmlns="http://www.w3.org/1999/xhtml"'
    ' xmlns:epub="http://www.idpf.org/2007/ops">\n'
    "<head>\n"
)

PAGE_MID = "\n</head>\n<body>"
PAGE_TAIL = "</body>\n</html>"

BASE_CSS = (
    "body{margin:1em;background-color:transparent!important;}"
    "#sbo-rt-content *{text-indent:0pt!important;}"
    "#sbo-rt-content .bq{margin-right:1em!important;}"
    "img,svg,video{max-width:100%;height:auto;}"
    "pre,code,kbd,samp{white-space:pre-wrap;word-wrap:break-word;"
    "word-break:break-word;}"
    "table{max-width:100%;}"
    "td,th{vertical-align:top;}"
    "figure,table{page-break-inside:avoid;}"
    "figure{margin:1em auto;text-align:center;}"
    "figcaption{margin:0.5em;font-size:0.9em;}"
    "h1,h2,h3,h4,h5,h6{page-break-after:avoid;}"
)

KINDLE_CSS = (
    "#sbo-rt-content *{word-wrap:break-word!important;word-break:break-word!important;}"
    "#sbo-rt-content table,#sbo-rt-content pre{overflow-x:unset!important;"
    "overflow:unset!important;overflow-y:unset!important;white-space:pre-wrap!important;}"
)

COVER_CSS = (
    "body{display:table;position:absolute;margin:0!important;"
    "height:100%;width:100%;}"
    "#Cover{display:table-cell;vertical-align:middle;text-align:center;}"
    "img{height:90vh;margin-left:auto;margin-right:auto;}"
)

# Interactive/reader-only elements that have no place in an EPUB document
STRIP_XPATH = (
    ".//script|.//iframe|.//noscript|.//button|.//form|.//input"
    "|.//select|.//textarea|.//div[@class='controls']"
)


def _is_absolute(url):
    return bool(urlparse(url).netloc)


def _is_image_link(url):
    return pathlib.Path(url).suffix[1:].lower() in [
        "jpg",
        "jpeg",
        "png",
        "gif",
        "svg",
        "webp",
    ]


class Transformer:
    def __init__(self, book_id, base_url, kindle=False, lang="en"):
        self.book_id = book_id
        self.base_url = base_url
        self.lang = lang or "en"
        self.css = []  # ordered registry of stylesheet URLs
        self.base_css = BASE_CSS + (KINDLE_CSS if kindle else "")
        self.cover = None

        lowercase_ns = etree.FunctionNamespace(None)
        lowercase_ns["lower-case"] = lambda _, n: n[0].lower() if n and len(n) else ""

    # -- link rewriting ------------------------------------------------------

    def _link_replace(self, link):
        if not link or link.startswith("mailto"):
            return link
        if not _is_absolute(link):
            path, _, frag = link.partition("#")
            if not path:
                return link
            tail = path.rsplit("/", 1)[-1]
            if not tail:
                return f"#{frag}" if frag else "#"
            suffix = f"#{frag}" if frag else ""
            if _is_image_link(tail):
                return "Images/" + tail + suffix
            if tail.lower().endswith((".html", ".xhtml")):
                return tail.rsplit(".", 1)[0] + ".xhtml" + suffix
            return link
        if self.book_id in link:
            return self._link_replace(link.split(self.book_id)[-1])
        return link

    # -- cover detection -------------------------------------------------------

    @staticmethod
    def _find_cover_image(html_root):
        images = html_root.xpath(
            "//img[contains(lower-case(@id), 'cover') or contains(lower-case(@class), 'cover')"
            " or contains(lower-case(@name), 'cover') or contains(lower-case(@src), 'cover')"
            " or contains(lower-case(@alt), 'cover')]"
        )
        if len(images):
            return images[0]
        for tag in ("div", "a"):
            found = html_root.xpath(
                f"//{tag}[contains(lower-case(@id), 'cover') or "
                f"contains(lower-case(@class), 'cover') or "
                f"contains(lower-case(@name), 'cover') or "
                f"contains(lower-case(@src), 'cover')]//img"
            )
            if len(found):
                return found[0]
        return None

    # -- stylesheet handling ------------------------------------------------------

    def _register_css(self, css_url):
        if css_url not in self.css:
            self.css.append(css_url)
        return (
            f'<link href="Styles/Style{self.css.index(css_url):0>2}.css" '
            'rel="stylesheet" type="text/css" />\n'
        )

    # -- main entry -----------------------------------------------------------------

    def parse(self, root, chapter_stylesheets=(), first_page=False):
        book_content = root.xpath("//div[@id='sbo-rt-content']")
        if len(book_content):
            content_root = book_content[0]
        else:
            # v2 content_url may serve the raw EPUB XHTML: fall back to <body>
            body = root.xpath("//body")
            if not len(body):
                raise ValueError(
                    "Chapter content is missing (#sbo-rt-content and <body>)"
                )
            content_root = body[0]

        page_css = ""
        for css_url in chapter_stylesheets:
            page_css += self._register_css(css_url)

        for s in root.xpath("//link[@rel='stylesheet']"):
            href = s.attrib.get("href", "")
            if not href:
                continue
            css_url = (
                urljoin("https:", href)
                if href[:2] == "//"
                else urljoin(self.base_url, href)
            )
            page_css += self._register_css(css_url)

        for css in root.xpath("//style"):
            if css.attrib.get("data-template"):
                css.text = css.attrib["data-template"]
                del css.attrib["data-template"]
            page_css += html.tostring(css, method="xml", encoding="unicode") + "\n"

        # SVG <image> -> <img>
        for img in root.xpath("//image"):
            href_keys = [k for k in img.attrib if "href" in k]
            if href_keys:
                svg_root = img.getparent().getparent()
                new_img = svg_root.makeelement("img")
                new_img.attrib.update({"src": img.attrib[href_keys[0]]})
                svg_root.remove(img.getparent())
                svg_root.append(new_img)

        # Strip reader-only interactive elements
        for el in content_root.xpath(STRIP_XPATH):
            el.getparent().remove(el)

        content_root.rewrite_links(self._link_replace)

        # Explicit empty alt marks decorative images (better than absent).
        for img in content_root.iter("img"):
            if img.get("alt") is None:
                img.set("alt", "")

        if first_page:
            cover_img = self._find_cover_image(content_root)
            if cover_img is not None:
                self.cover = cover_img.attrib["src"]
                page_css = f"<style>{COVER_CSS}</style>"
                cover_html = html.fromstring('<div id="Cover" epub:type="cover"></div>')
                cover_div = cover_html.xpath("//div")[0]
                new_img = cover_div.makeelement("img")
                new_img.attrib.update({"src": self.cover, "alt": "Cover"})
                cover_div.append(new_img)
                content_root = cover_html

        xhtml = html.tostring(content_root, method="xml", encoding="unicode")
        return page_css, xhtml

    def render_page(self, page_css, xhtml, title=""):
        head = (
            '<meta charset="utf-8"/>\n'
            f"<title>{escape(title)}</title>\n"
            f"{page_css}"
            '<link href="Styles/Shelf.css" rel="stylesheet"'
            ' type="text/css"/>'
        )
        return (
            PAGE_HEAD.format(lang=escape(self.lang))
            + head
            + PAGE_MID
            + xhtml
            + PAGE_TAIL
        )
