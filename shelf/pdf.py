"""Render the assembled OEBPS content into a single PDF via WeasyPrint."""

import os
from xml.sax.saxutils import escape

from lxml import html

PDF_CSS = (
    "@page{size:A4;margin:20mm 18mm !important;"
    "@bottom-center{content:counter(page);font-size:9pt;color:#666}"
    "@top-center{content:string(chapter);font-size:8pt;color:#999}}"
    "h1,h2{string-set:chapter content()}"
    ".chapter + .chapter{break-before:page}"
    "a{color:inherit;text-decoration:none}"
    "img{max-width:100%}"
    "pre,code{font-size:0.9em}"
)


def _chapter_section(path, anchor):
    doc = html.parse(path)
    body = doc.getroot().find("body")
    if body is None:
        return ""
    for a in body.iter("a"):
        href = a.attrib.get("href", "")
        if not href or href.startswith("#") or ":" in href:
            continue
        base = href.split("#", 1)[0]
        if base.endswith((".html", ".xhtml")):
            frag = ""
            if "#" in href:
                frag = "#" + href.split("#", 1)[1]
            stem = os.path.splitext(os.path.basename(base))[0]
            a.attrib["href"] = frag or f"#{stem}"
    inner = (body.text or "") + "".join(
        html.tostring(el, encoding="unicode") for el in body
    )
    return f'<section class="chapter" id="{anchor}">{inner}</section>'


def build_pdf(oebps_dir, chapters, book_title, pdf_path):
    """chapters: list of {filename, title} dicts (filenames may still be .html)."""
    from weasyprint import HTML

    styles_dir = os.path.join(oebps_dir, "Styles")
    links = "".join(
        f'<link href="Styles/{n}" rel="stylesheet" type="text/css"/>\n'
        for n in sorted(os.listdir(styles_dir))
        if n.endswith(".css")
    )

    sections = []
    for ch in chapters:
        filename = ch["filename"].replace(".html", ".xhtml")
        path = os.path.join(oebps_dir, filename)
        if not os.path.isfile(path):
            continue
        sections.append(_chapter_section(path, os.path.splitext(filename)[0]))

    doc = (
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
        "<html><head>\n"
        f'<meta charset="utf-8"/><title>{escape(book_title)}</title>\n'
        f"{links}<style>{PDF_CSS}</style></head>\n"
        f"<body>{''.join(sections)}</body></html>"
    )
    HTML(string=doc, base_url=oebps_dir + "/").write_pdf(pdf_path)
    return pdf_path
