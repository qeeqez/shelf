"""Generate a static web-reader version of the book (sre.google-style)."""

import os
import shutil
from xml.sax.saxutils import escape

from lxml import html

SITE_CSS = """\
:root{--fg:#202124;--muted:#5f6368;--line:#dadce0;--accent:#1a73e8;--code:#f6f8fa}
*{box-sizing:border-box}
html{scroll-padding-top:72px}
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,
Helvetica,Arial,sans-serif;color:var(--fg);background:#fff;font-size:17px;
line-height:1.65}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
header.top{position:fixed;top:0;left:0;right:0;height:56px;display:flex;
align-items:center;padding:0 12px;background:#fff;
border-bottom:1px solid var(--line);z-index:20}
header.top button{background:none;border:0;font-size:20px;cursor:pointer;
color:var(--muted);padding:6px 12px;border-radius:6px}
header.top button:hover{background:#f1f3f4}
header.top .booktitle{font-size:15px;font-weight:600;white-space:nowrap;
overflow:hidden;text-overflow:ellipsis}
header.top .booktitle a{color:var(--fg)}
header.top .spacer{flex:1}
header.top a.toc-link{color:var(--muted);font-size:14px;padding:6px 12px;
border-radius:6px}
header.top a.toc-link:hover{background:#f1f3f4;text-decoration:none}
nav.sidebar{position:fixed;top:56px;left:0;bottom:0;width:300px;overflow-y:auto;
border-right:1px solid var(--line);background:#fff;padding:12px 0 40px;
transition:transform .2s ease;z-index:15}
body.sidebar-hidden nav.sidebar{transform:translateX(-104%)}
nav.sidebar ul{list-style:none;margin:0;padding:0}
nav.sidebar li a{display:block;padding:6px 24px;color:var(--fg);font-size:14px;
line-height:1.4}
nav.sidebar li a:hover{background:#f1f3f4;text-decoration:none}
nav.sidebar li a.active{color:var(--accent);background:#e8f0fe;font-weight:600}
nav.sidebar ul ul a{padding-left:42px}
nav.sidebar ul ul ul a{padding-left:60px}
nav.sidebar ul ul ul ul a{padding-left:78px}
main{padding:76px 24px 64px;margin-left:300px;transition:margin .2s ease}
body.sidebar-hidden main{margin-left:0}
.content{max-width:740px;margin:0 auto}
.content img{max-width:100%;height:auto}
.content h1{font-size:30px;line-height:1.25;margin:8px 0 24px}
.content h2{font-size:24px;margin:36px 0 12px}
.content h3{font-size:19px;margin:28px 0 10px}
.content h4,.content h5,.content h6{font-size:16px;margin:24px 0 8px}
.content p,.content ul,.content ol{margin:0 0 16px}
.content pre{background:var(--code);border:1px solid var(--line);
border-radius:8px;padding:14px 16px;overflow-x:auto;font-size:14px;
line-height:1.5;white-space:pre}
.content code{font-family:"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
font-size:.9em}
.content p code,.content li code,.content td code{background:var(--code);
padding:1px 5px;border-radius:4px}
.content pre code{background:none;padding:0}
.content table{border-collapse:collapse;width:100%;font-size:15px;margin:20px 0}
.content th,.content td{border:1px solid var(--line);padding:8px 12px;
text-align:left;vertical-align:top}
.content th{background:#f8f9fa}
.content blockquote{border-left:3px solid var(--line);margin:20px 0;
padding:2px 20px;color:var(--muted)}
.content figure{margin:28px 0;text-align:center}
.content figcaption{font-size:14px;color:var(--muted);margin-top:8px}
.content math[display="block"]{overflow-x:auto;max-width:100%}
.content dl{margin:0 0 16px}
.content dd{margin:0 0 6px 2em}
.content sup,.content sub{font-size:.75em;line-height:0}
.content .sidebar,aside[data-type="sidebar"]{border:1px solid var(--line);
border-radius:8px;background:#f8f9fa;padding:16px 20px;margin:24px 0}
.content h6{font-size:.9em;font-weight:400;font-style:italic;text-align:center;
color:var(--muted)}
.pager{display:flex;justify-content:space-between;gap:16px;max-width:740px;
margin:48px auto 0;border-top:1px solid var(--line);padding-top:20px;
font-size:15px}
.pager .next{margin-left:auto;text-align:right}
.index-hero{text-align:center;margin:24px 0 40px}
.index-hero img{max-width:320px;width:100%;border:1px solid var(--line);
border-radius:4px;box-shadow:0 2px 12px rgba(0,0,0,.12)}
.index-hero h1{font-size:34px;margin:24px 0 6px}
.index-hero .authors{color:var(--muted);font-size:16px}
@media (max-width:960px){
nav.sidebar{box-shadow:2px 0 14px rgba(0,0,0,.18)}
main{margin-left:0}
}
"""

SITE_JS = """\
(function () {
  var key = "bs-sidebar";
  var stored = null;
  try { stored = localStorage.getItem(key); } catch (e) {}
  if (stored === "hidden" || (stored === null && window.innerWidth < 960)) {
    document.body.classList.add("sidebar-hidden");
  }
  var btn = document.getElementById("menu-btn");
  if (btn) {
    btn.setAttribute("aria-expanded",
      document.body.classList.contains("sidebar-hidden") ? "false" : "true");
    btn.addEventListener("click", function () {
    var hidden = document.body.classList.toggle("sidebar-hidden");
    btn.setAttribute("aria-expanded", hidden ? "false" : "true");
    try { localStorage.setItem(key, hidden ? "hidden" : "open"); } catch (e) {}
    });
  }
  document.addEventListener("keydown", function (e) {
    if (/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
    var sel = e.key === "ArrowLeft" ? ".pager a.prev"
            : e.key === "ArrowRight" ? ".pager a.next" : null;
    if (!sel) return;
    var a = document.querySelector(sel);
    if (a) location.href = a.href;
  });
  var act = document.querySelector("nav.sidebar a.active");
  if (act && act.scrollIntoView) act.scrollIntoView({ block: "nearest" });
})();
"""

PAGE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{page_title}</title>
{book_links}<link rel="stylesheet" href="assets/site.css"/>{extra_head}
</head>
<body>
<header class="top">
<button id="menu-btn" aria-label="Toggle table of contents"
 aria-controls="sidebar" aria-expanded="true">&#9776;</button>
<span class="booktitle"><a href="index.html">{book_title}</a></span>
<span class="spacer"></span>
<a class="toc-link" href="toc.html">Contents</a>
</header>
<nav class="sidebar" id="sidebar">{sidebar}</nav>
<main>
<div class="content">
{body}
</div>
{pager}
</main>
<script src="assets/site.js"></script>
</body>
</html>
"""


def _stem(filename):
    return os.path.splitext(os.path.basename(filename))[0]


def _page_name(filename):
    return _stem(filename) + ".html"


def _rewrite_links(body):
    for a in body.iter("a"):
        href = a.attrib.get("href", "")
        if not href or href.startswith("#") or ":" in href:
            continue
        base = href.split("#", 1)[0]
        if base.endswith((".html", ".xhtml")):
            frag = "#" + href.split("#", 1)[1] if "#" in href else ""
            a.attrib["href"] = _page_name(base) + frag


def _chapter_body(path):
    doc = html.parse(path).getroot()
    body = doc.find("body")
    if body is None:
        return "", ""
    _rewrite_links(body)
    styles = "".join(html.tostring(s, encoding="unicode") for s in doc.iter("style"))
    body_html = (body.text or "") + "".join(
        html.tostring(el, encoding="unicode") for el in body
    )
    return styles, body_html


def _first_stem_match(items, stem):
    if stem is None:
        return None
    for item in items:
        if _stem(item["href"]) == stem:
            return item
        hit = _first_stem_match(item["children"], stem)
        if hit is not None:
            return hit
    return None


def _sidebar_ul(items, active_item):
    lis = []
    for item in items:
        href = _page_name(item["href"])
        if item["fragment"]:
            href += "#" + item["fragment"]
        cls = ' class="active" aria-current="page"' if item is active_item else ""
        children = (
            _sidebar_ul(item["children"], active_item) if item["children"] else ""
        )
        lis.append(
            f'<li><a href="{escape(href)}"{cls}>{escape(item["label"])}</a>'
            f"{children}</li>"
        )
    return "<ul>" + "".join(lis) + "</ul>"


def _pager(chapters, i):
    prev_link = ""
    if i > 0:
        p = chapters[i - 1]
        prev_link = (
            f'<a class="prev" href="{_page_name(p["filename"])}">'
            f"&larr; {escape(p['title'])}</a>"
        )
    next_link = ""
    if i + 1 < len(chapters):
        n = chapters[i + 1]
        next_link = (
            f'<a class="next" href="{_page_name(n["filename"])}">'
            f"{escape(n['title'])} &rarr;</a>"
        )
    if not (prev_link or next_link):
        return ""
    return f'<div class="pager">{prev_link}{next_link}</div>'


def build_web(oebps_dir, chapters, toc_items, info, web_dir, cover_src=None):
    """Emit a static site: index, toc.html, one page per chapter, assets."""
    assets = os.path.join(web_dir, "assets")
    os.makedirs(assets, exist_ok=True)
    for sub in ("Images", "Fonts", "Styles"):
        src = os.path.join(oebps_dir, sub)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(web_dir, sub), dirs_exist_ok=True)

    with open(os.path.join(assets, "site.css"), "w") as f:
        f.write(SITE_CSS)
    with open(os.path.join(assets, "site.js"), "w") as f:
        f.write(SITE_JS)

    styles_dir = os.path.join(web_dir, "Styles")
    book_links = ""
    if os.path.isdir(styles_dir):
        book_links = "".join(
            f'<link rel="stylesheet" href="Styles/{n}"/>\n'
            for n in sorted(os.listdir(styles_dir))
            if n.endswith(".css")
        )

    title = info.get("title", "Book")

    def render(
        page_title, sidebar_current, body, pager="", into="index.html", extra_head=""
    ):
        page = PAGE.replace("{page_title}", escape(page_title))
        page = page.replace("{book_title}", escape(title))
        page = page.replace("{book_links}", book_links)
        page = page.replace(
            "{sidebar}",
            _sidebar_ul(toc_items, _first_stem_match(toc_items, sidebar_current)),
        )
        page = page.replace("{pager}", pager)
        page = page.replace("{body}", body)
        page = page.replace("{extra_head}", extra_head)
        with open(os.path.join(web_dir, into), "w") as f:
            f.write(page)

    # Chapter pages
    flat = [c for c in chapters]
    for i, ch in enumerate(flat):
        path = os.path.join(oebps_dir, ch["filename"].replace(".html", ".xhtml"))
        if not os.path.isfile(path):
            continue
        styles, body = _chapter_body(path)
        render(
            f"{ch['title']} — {title}",
            _stem(ch["filename"]),
            body,
            pager=_pager(flat, i),
            into=_page_name(ch["filename"]),
            extra_head=styles,
        )

    # Full TOC page
    render(
        f"Table of Contents — {title}",
        None,
        f"<h1>Table of Contents</h1>{_sidebar_ul(toc_items, None)}",
        into="toc.html",
    )

    # Landing page
    hero = ""
    if cover_src:
        hero = f'<img src="{escape(cover_src)}" alt="Cover"/>'
    authors = ", ".join(info.get("authors", []))
    hero += f"<h1>{escape(title)}</h1>"
    if authors:
        hero += f'<p class="authors">{escape(authors)}</p>'
    first = _page_name(flat[0]["filename"]) if flat else "toc.html"
    hero += f'<p><a href="{first}">Start reading &rarr;</a></p>'
    render(title, None, f'<div class="index-hero">{hero}</div>', into="index.html")

    return web_dir
