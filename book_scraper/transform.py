"""Convert O'Reilly reader pages into standalone EPUB XHTML documents."""

import pathlib
from urllib.parse import urljoin, urlparse

from lxml import etree, html

BASE_01_HTML = (
    "<!DOCTYPE html>\n"
    '<html lang="en" xml:lang="en" xmlns="http://www.w3.org/1999/xhtml"'
    ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
    ' xsi:schemaLocation="http://www.w3.org/2002/06/xhtml2/'
    ' http://www.w3.org/MarkUp/SCHEMA/xhtml2.xsd"'
    ' xmlns:epub="http://www.idpf.org/2007/ops">\n'
    "<head>\n{0}\n"
    '<style type="text/css">'
    "body{{margin:1em;background-color:transparent!important;}}"
    "#sbo-rt-content *{{text-indent:0pt!important;}}"
    "#sbo-rt-content .bq{{margin-right:1em!important;}}"
)

KINDLE_HTML = (
    "#sbo-rt-content *{{word-wrap:break-word!important;word-break:break-word!important;}}"
    "#sbo-rt-content table,#sbo-rt-content pre{{overflow-x:unset!important;"
    "overflow:unset!important;overflow-y:unset!important;white-space:pre-wrap!important;}}"
)

BASE_02_HTML = "</style></head>\n<body>{1}</body>\n</html>"

COVER_STYLE = (
    "<style>body{display:table;position:absolute;margin:0!important;"
    "height:100%;width:100%;}"
    "#Cover{display:table-cell;vertical-align:middle;text-align:center;}"
    "img{height:90vh;margin-left:auto;margin-right:auto;}</style>"
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
    def __init__(self, book_id, base_url, kindle=False):
        self.book_id = book_id
        self.base_url = base_url
        self.css = []  # ordered registry of stylesheet URLs
        self.base_html = BASE_01_HTML + (KINDLE_HTML if kindle else "") + BASE_02_HTML
        self.cover = None

        lowercase_ns = etree.FunctionNamespace(None)
        lowercase_ns["lower-case"] = lambda _, n: n[0].lower() if n and len(n) else ""

    # -- link rewriting ------------------------------------------------------

    def _link_replace(self, link):
        if not link or link.startswith("mailto"):
            return link
        if not _is_absolute(link):
            if any(
                x in link for x in ["cover", "images", "graphics"]
            ) or _is_image_link(link):
                return "Images/" + link.split("/")[-1]
            return link.replace(".html", ".xhtml")
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
            f'<link href="Styles/Style{self.css.index(css_url):0>2}.css" rel="stylesheet" '
            'type="text/css" />\n'
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

        content_root.rewrite_links(self._link_replace)

        if first_page:
            cover_img = self._find_cover_image(content_root)
            if cover_img is not None:
                self.cover = cover_img.attrib["src"]
                page_css = COVER_STYLE
                cover_html = html.fromstring('<div id="Cover"></div>')
                cover_div = cover_html.xpath("//div")[0]
                new_img = cover_div.makeelement("img")
                new_img.attrib.update({"src": self.cover})
                cover_div.append(new_img)
                content_root = cover_html

        xhtml = html.tostring(content_root, method="xml", encoding="unicode")
        return page_css, xhtml

    def render_page(self, page_css, xhtml):
        return self.base_html.format(page_css, xhtml)
