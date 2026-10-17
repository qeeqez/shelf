"""Render the assembled OEBPS content into a single PDF.

WeasyPrint (needs system Pango) is preferred for CSS paged-media support;
headless Chromium is the no-extra-install fallback."""

import os
import shutil
import subprocess
import sys
from xml.sax.saxutils import escape

from lxml import html


class PdfError(Exception):
    pass


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


def _chrome_binary():
    """Chrome renders print PDFs with full modern CSS/MathML support —
    a usable engine most machines already have installed."""
    candidates = []
    if sys.platform == "darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ]
    elif sys.platform == "win32":
        for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            base = os.environ.get(env)
            if base:
                candidates += [
                    os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"),
                    os.path.join(
                        base, "Microsoft", "Edge", "Application", "msedge.exe"
                    ),
                ]
    for name in (
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "microsoft-edge",
        "brave",
    ):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def _chrome_pdf(doc, oebps_dir, pdf_path):
    """Print the assembled single-document HTML via headless Chromium.
    Chrome ignores CSS paged-media margin boxes, so page numbers/running
    headers are lost — WeasyPrint output stays superior when available."""
    chrome = _chrome_binary()
    if not chrome:
        return False
    src = os.path.join(oebps_dir, "_print.html")
    with open(src, "w", encoding="utf-8") as f:
        f.write(doc)
    try:
        result = subprocess.run(
            [
                chrome,
                "--headless=new",
                "--disable-gpu",
                "--no-pdf-header-footer",
                "--virtual-time-budget=30000",
                f"--print-to-pdf={os.path.abspath(pdf_path)}",
                "file://" + os.path.abspath(src),
            ],
            check=False,
            capture_output=True,
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired):
        result = None
    finally:
        try:
            os.unlink(src)
        except OSError:
            pass
    return result is not None and result.returncode == 0 and os.path.isfile(pdf_path)


def build_pdf(oebps_dir, chapters, book_title, pdf_path):
    """chapters: list of {filename, title} dicts (filenames may still be .html)."""
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

    # WeasyPrint first (real paged-media support: page numbers, running
    # heads) — it needs the system Pango/GDK-Pixbuf libraries, which is why
    # --pdf requires that extra install. Import can succeed while the libs
    # are absent, so the render itself decides availability.
    try:
        from weasyprint import HTML

        HTML(string=doc, base_url=oebps_dir + "/").write_pdf(pdf_path)
        return pdf_path
    except (ImportError, OSError):
        pass

    if _chrome_pdf(doc, oebps_dir, pdf_path):
        return pdf_path

    raise PdfError(
        "No PDF engine available — either install a Chromium browser, or "
        "WeasyPrint + Pango (macOS: brew install pango; see README)."
    )
