"""Generate a static web-reader version of the book (sre.google-style)."""

import json
import os
import shutil
from xml.sax.saxutils import escape

from lxml import html

SITE_CSS = """\
:root{color-scheme:light;--fg:#202124;--muted:#5f6368;--line:#dadce0;--accent:#1a73e8;
--code:#f6f8fa;--bg:#fff;--chrome:#fff;--hover:#f1f3f4;--sel:#f6f9ff;
--active:#e8f0fe;--input:#f8f9fa;--input-focus:#fff;--mark:#fff3a0;
--mark-fg:inherit;--card-bg:transparent;--card-fg:inherit;--card-pad:0;
--card-r:0;--elev:0 8px 28px rgba(0,0,0,.18);
--ring:0 0 0 2px #e8f0fe;
--hero-shadow:0 2px 12px rgba(0,0,0,.12);
--content-muted:#5f6368;--content-accent:#1a73e8}
:root[data-theme="dark"]{color-scheme:dark;--fg:#e8eaed;--muted:#9aa0a6;--line:#3c4043;
--accent:#8ab4f8;--bg:#17181a;--chrome:#1e1f21;
--hover:#303134;--sel:#26292e;--active:#374a6b;--input:#2d2f31;
--input-focus:#2d2f31;--mark:#6b5d00;--mark-fg:#fff;
--card-fg:#202124;
--elev:0 8px 28px rgba(0,0,0,.6);--ring:0 0 0 2px #374a6b;
--hero-shadow:0 2px 16px rgba(0,0,0,.5)}
@media (prefers-color-scheme:dark){
:root:not([data-theme="light"]){color-scheme:dark;--fg:#e8eaed;--muted:#9aa0a6;
--line:#3c4043;--accent:#8ab4f8;--bg:#17181a;
--chrome:#1e1f21;--hover:#303134;--sel:#26292e;--active:#374a6b;
--input:#2d2f31;--input-focus:#2d2f31;--mark:#6b5d00;--mark-fg:#fff;
--card-fg:#202124;
--elev:0 8px 28px rgba(0,0,0,.6);--ring:0 0 0 2px #374a6b;
--hero-shadow:0 2px 16px rgba(0,0,0,.5)}
}
*{box-sizing:border-box}
html{scroll-padding-top:72px;scrollbar-width:thin;
scrollbar-color:var(--muted) transparent}
::-webkit-scrollbar{width:8px;height:8px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--line);border-radius:4px}
::-webkit-scrollbar-thumb:hover{background:var(--muted)}
::-webkit-scrollbar-corner{background:transparent}
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,
Helvetica,Arial,sans-serif;color:var(--fg);background:var(--bg);font-size:17px;
line-height:1.65;text-size-adjust:100%;overflow-x:hidden}
a{color:var(--accent);text-decoration:none;transition:color .15s ease}
body,header.top,.search-results,.pager{
transition:background-color .25s ease,border-color .25s ease}
nav.sidebar li a{position:relative;
transition:background-color .15s ease,color .15s ease}
nav.sidebar li a.spy{color:var(--accent);font-weight:600}
nav.sidebar li a.spy::before{content:"";position:absolute;left:10px;
top:22%;bottom:22%;width:3px;border-radius:2px;background:var(--accent);
animation:spyin .18s ease}
@keyframes spyin{from{transform:scaleY(.3);opacity:0}
to{transform:scaleY(1);opacity:1}}
.skip{position:absolute;left:-9999px;top:0;z-index:50}
.skip:focus{left:8px;top:8px;background:var(--accent);color:#fff;
padding:8px 14px;border-radius:6px}
a:hover{text-decoration:underline}
header.top{position:fixed;top:0;left:0;right:0;height:56px;display:flex;
align-items:center;gap:6px;padding:0 max(12px,env(safe-area-inset-right)) 0
max(12px,env(safe-area-inset-left));background:var(--chrome);
border-bottom:1px solid var(--line);z-index:20}
header.top button{background:none;border:0;font-size:20px;cursor:pointer;
color:var(--muted);padding:6px 12px;border-radius:6px}
header.top button:hover{background:var(--hover)}
#theme-btn{width:36px;padding:6px 0;text-align:center}
header.top .booktitle{font-size:15px;font-weight:600;white-space:nowrap;
overflow:hidden;text-overflow:ellipsis}
header.top .booktitle a{color:var(--fg)}
header.top .spacer{flex:1}
header.top a.toc-link{color:var(--muted);font-size:14px;padding:6px 12px;
border-radius:6px}
header.top a.toc-link:hover{background:var(--hover);text-decoration:none}
.search{position:relative}
#search-box{width:220px;max-width:38vw;padding:6px 14px;
border:1px solid var(--line);border-radius:16px;font-size:16px;outline:none;
background:var(--input);color:var(--fg)}
#search-box:focus{background:var(--input-focus);border-color:var(--accent);
box-shadow:var(--ring)}
.search-results{position:absolute;top:44px;right:0;width:min(480px,92vw);
max-height:70vh;overflow-y:auto;background:var(--chrome);
border:1px solid var(--line);border-radius:8px;box-shadow:var(--elev);z-index:30;
scrollbar-width:thin;scrollbar-color:var(--muted) transparent}
.search-results a.result{display:block;padding:10px 14px;
border-bottom:1px solid var(--hover);color:var(--fg)}
.search-results a.result:last-child{border-bottom:0}
.search-results a.result:hover,.search-results a.result.sel{
background:var(--sel);text-decoration:none}
.search-results .r-title{font-weight:600;font-size:14px}
.search-results .r-snip{font-size:13px;color:var(--muted);line-height:1.45;
overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;
-webkit-box-orient:vertical}
.search-results .r-snip mark{background:var(--mark);color:var(--mark-fg);
padding:0 1px;border-radius:2px}
.search-results .no-results{padding:14px;color:var(--muted);font-size:14px}
@keyframes dropin{from{opacity:0;transform:translateY(-5px)}
to{opacity:1;transform:none}}
.search-results{animation:dropin .15s ease}
@media (max-width:640px){
#search-box{width:110px}
.search-results{position:fixed;top:56px;left:8px;right:8px;width:auto}
}
nav.sidebar{position:fixed;top:56px;left:0;bottom:0;width:300px;overflow-y:auto;
border-right:1px solid var(--line);background:var(--chrome);
padding:12px 0 calc(40px + env(safe-area-inset-bottom));
transition:transform .2s ease;z-index:15;scrollbar-width:thin;
scrollbar-color:var(--muted) transparent}
.scrim{position:fixed;inset:0;background:rgba(0,0,0,.38);opacity:0;
visibility:hidden;transition:opacity .2s ease,visibility .2s;z-index:14}
body.sidebar-hidden nav.sidebar{transform:translateX(-104%)}
nav.sidebar ul{list-style:none;margin:0;padding:0}
nav.sidebar li a{display:block;padding:6px 24px;color:var(--fg);font-size:14px;
line-height:1.4}
nav.sidebar li a:hover{background:var(--hover);text-decoration:none}
nav.sidebar li a.active{color:var(--accent);background:var(--active);
font-weight:600}
nav.sidebar ul ul a{padding-left:42px}
nav.sidebar ul ul ul a{padding-left:60px}
nav.sidebar ul ul ul ul a{padding-left:78px}
main{padding:76px 24px 64px;margin-left:300px;transition:margin .2s ease}
body.sidebar-hidden main{margin-left:0}
.content{max-width:740px;margin:0 auto;background:var(--card-bg);
color:var(--card-fg);border-radius:var(--card-r);padding:var(--card-pad);
transition:background-color .25s ease,color .25s ease,filter .3s ease}
.content a{color:var(--content-accent)}
.content .anchor{opacity:0;margin-left:.35em;font-size:.75em;
font-weight:400;color:var(--content-muted);text-decoration:none;
transition:opacity .15s ease}
.content h1:hover .anchor,.content h2:hover .anchor,
.content h3:hover .anchor,.content h4:hover .anchor,
.content .anchor:focus{opacity:1}
.content .anchor.copied{color:#188038}
@media (hover:none){.content .anchor{opacity:.5}}
.content img{max-width:100%;height:auto}
.content h1{font-size:30px;line-height:1.25;margin:8px 0 24px}
.content h2{font-size:24px;margin:36px 0 12px}
.content h3{font-size:19px;margin:28px 0 10px}
.content h4,.content h5,.content h6{font-size:16px;margin:24px 0 8px}
.content p,.content ul,.content ol{margin:0 0 16px}
.content pre{background:var(--code);border:1px solid var(--line);
border-radius:8px;padding:14px 16px;overflow-x:auto;font-size:14px;
line-height:1.5;white-space:pre;scrollbar-width:thin;
scrollbar-color:var(--muted) transparent}
.content code{font-family:"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
font-size:.9em}
.content p code,.content li code,.content td code{background:var(--code);
padding:1px 5px;border-radius:4px}
.content pre code{background:none;padding:0}
.content table{border-collapse:collapse;width:100%;font-size:15px;
margin:20px 0;display:block;overflow-x:auto;scrollbar-width:thin;
scrollbar-color:var(--muted) transparent}
.content th,.content td{border:1px solid var(--line);padding:8px 12px;
text-align:left;vertical-align:top}
.content th{background:#f8f9fa}
.content blockquote{border-left:3px solid var(--line);margin:20px 0;
padding:2px 20px;color:var(--content-muted)}
.content figure{margin:28px 0;text-align:center}
.content figcaption{font-size:14px;color:var(--content-muted);margin-top:8px}
.content math[display="block"]{overflow-x:auto;max-width:100%}
.content dl{margin:0 0 16px}
.content dd{margin:0 0 6px 2em}
.content sup,.content sub{font-size:.75em;line-height:0}
.content .sidebar,aside[data-type="sidebar"]{border:1px solid var(--line);
border-radius:8px;background:#f8f9fa;padding:16px 20px;margin:24px 0}
.content h6{font-size:.9em;font-weight:400;font-style:italic;text-align:center;
color:var(--content-muted)}
.pager{display:flex;justify-content:space-between;gap:16px;max-width:740px;
margin:48px auto 0;border-top:1px solid var(--line);padding-top:20px;
font-size:15px}
.pager .next{margin-left:auto;text-align:right}
.index-hero{text-align:center;margin:24px 0 40px}
.index-hero img{max-width:320px;width:100%;border:1px solid var(--line);
border-radius:4px;box-shadow:var(--hero-shadow)}
.index-hero h1{font-size:34px;margin:24px 0 6px}
.index-hero .authors{color:var(--content-muted);font-size:16px}
@media (max-width:960px){
nav.sidebar{box-shadow:2px 0 14px rgba(0,0,0,.18);
transform:translateX(-104%)}
body.sidebar-open nav.sidebar{transform:none}
body.sidebar-open .scrim{opacity:1;visibility:visible}
nav.sidebar li a{padding-top:9px;padding-bottom:9px}
main{margin-left:0}
}
@media (max-width:480px){
header.top .booktitle{display:none}
}
/* Content goes dark via invert+hue-rotate: lightness flips, hues survive
   (book CSS colors like #C30/#069 stay readable). Images invert too —
   diagrams become white-on-dark instead of white rectangles. */
:root[data-theme="dark"] .content{filter:invert(1) hue-rotate(180deg)}
@media (prefers-color-scheme:dark){
:root:not([data-theme="light"]) .content{filter:invert(1) hue-rotate(180deg)}
}
@media print{
header.top,nav.sidebar,.pager,.skip,.anchor{display:none}
main{padding:0;margin-left:0}
.content{max-width:none;padding:0;filter:none !important}
figure,pre,table{break-inside:avoid}
h1,h2,h3{break-after:avoid}
}
@media (prefers-reduced-motion:reduce){
*,::before,::after{animation-duration:.01ms !important;
animation-iteration-count:1 !important;transition-duration:.01ms !important}
}
"""

SITE_JS = """\
(function () {
  var key = "bs-sidebar";
  var stored = null;
  try { stored = localStorage.getItem(key); } catch (e) {}
  var narrow = function () { return window.innerWidth < 960; };
  var isHidden = function () {
    return narrow()
      ? !document.body.classList.contains("sidebar-open")
      : document.body.classList.contains("sidebar-hidden");
  };
  if (stored === "hidden") document.body.classList.add("sidebar-hidden");
  if (stored === "open" && narrow()) document.body.classList.add("sidebar-open");
  var btn = document.getElementById("menu-btn");
  var setSidebar = function (open) {
    if (narrow()) {
      document.body.classList.toggle("sidebar-open", open);
      document.body.classList.remove("sidebar-hidden");
    } else {
      document.body.classList.toggle("sidebar-hidden", !open);
      document.body.classList.remove("sidebar-open");
    }
    if (btn) btn.setAttribute("aria-expanded", open ? "true" : "false");
    try {
      if (!narrow()) localStorage.setItem(key, open ? "open" : "hidden");
    } catch (e) {}
  };
  if (btn) {
    btn.setAttribute("aria-expanded", isHidden() ? "false" : "true");
    btn.addEventListener("click", function () {
      setSidebar(isHidden());
    });
  }
  var scrim = document.getElementById("scrim");
  if (scrim) {
    scrim.addEventListener("click", function () {
      setSidebar(false);
    });
  }
  document.querySelectorAll("nav.sidebar a").forEach(function (a) {
    a.addEventListener("click", function () {
      if (narrow()) setSidebar(false);
    });
  });
  // -- theme (system / light / dark) --------------------------------------
  var themeKey = "bs-theme";
  var themeBtn = document.getElementById("theme-btn");
  var mq =
    window.matchMedia && window.matchMedia("(prefers-color-scheme:dark)");
  var GLYPHS = { system: "◐", light: "☀", dark: "☾" };
  function applyTheme(t) {
    document.documentElement.dataset.theme = t;
    if (themeBtn) {
      themeBtn.textContent = GLYPHS[t];
      themeBtn.title = "Theme: " + t;
      themeBtn.setAttribute("aria-label", "Theme: " + t);
    }
  }
  applyTheme(document.documentElement.dataset.theme || "system");
  if (mq && mq.addEventListener) {
    mq.addEventListener("change", function () {
      if ((document.documentElement.dataset.theme || "system") === "system")
        applyTheme("system");
    });
  }
  if (themeBtn) {
    themeBtn.addEventListener("click", function () {
      var order = { system: "light", light: "dark", dark: "system" };
      var t =
        order[document.documentElement.dataset.theme || "system"] || "system";
      applyTheme(t);
      try {
        localStorage.setItem(themeKey, t);
      } catch (e) {}
    });
  }
  document.addEventListener("keydown", function (e) {
    if (/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
    if (e.key === "Escape" && !isHidden()) {
      setSidebar(false);
      return;
    }
    var box = document.getElementById("search-box");
    if (e.key === "/" && box) {
      e.preventDefault();
      box.focus();
      return;
    }
    var sel = e.key === "ArrowLeft" ? ".pager a.prev"
            : e.key === "ArrowRight" ? ".pager a.next" : null;
    if (!sel) return;
    var a = document.querySelector(sel);
    if (a) location.href = a.href;
  });
  var act = document.querySelector("nav.sidebar a.active");
  if (act && act.scrollIntoView) act.scrollIntoView({ block: "nearest" });

  // -- client-side search --------------------------------------------------
  var box = document.getElementById("search-box");
  var res = document.getElementById("search-results");
  var idx = null, idxLoading = false, sel = -1;

  function ensureIndex() {
    if (idx || idxLoading) return;
    idxLoading = true;
    var s = document.createElement("script");
    s.src = "assets/search-index.js";
    s.onload = function () {
      idx = window.BS_SEARCH || [];
      for (var i = 0; i < idx.length; i++) {
        idx[i]._tl = idx[i].t.toLowerCase();
        idx[i]._sl = idx[i].s.toLowerCase();
      }
    };
    document.head.appendChild(s);
  }

  function hideResults() { if (res) res.hidden = true; sel = -1; }

  function highlight(snippet, terms) {
    var frag = document.createDocumentFragment(), pos = 0;
    var low = snippet.toLowerCase();
    while (pos < snippet.length) {
      var next = -1, term = "";
      for (var i = 0; i < terms.length; i++) {
        var p = low.indexOf(terms[i], pos);
        if (p >= 0 && (next < 0 || p < next)) { next = p; term = terms[i]; }
      }
      if (next < 0) {
        frag.appendChild(document.createTextNode(snippet.slice(pos)));
        break;
      }
      frag.appendChild(document.createTextNode(snippet.slice(pos, next)));
      var m = document.createElement("mark");
      m.textContent = snippet.slice(next, next + term.length);
      frag.appendChild(m);
      pos = next + term.length;
    }
    return frag;
  }

  function doSearch() {
    var q = box.value.toLowerCase().trim();
    if (!idx || q.length < 2) { hideResults(); return; }
    var terms = q.split(/\\s+/).filter(Boolean);
    var out = [];
    for (var i = 0; i < idx.length; i++) {
      var e = idx[i], first = -1, score = 0, ok = true;
      for (var w = 0; w < terms.length; w++) {
        var tp = e._tl.indexOf(terms[w]);
        var sp = e._sl.indexOf(terms[w]);
        if (tp < 0 && sp < 0) { ok = false; break; }
        if (tp >= 0) score += 30;
        if (sp >= 0) {
          score += Math.min(e._sl.split(terms[w]).length - 1, 20);
          if (first < 0 || sp < first) first = sp;
        }
      }
      if (ok) out.push({ e: e, score: score, pos: Math.max(0, first) });
    }
    out.sort(function (a, b) { return b.score - a.score; });
    res.innerHTML = ""; sel = -1;
    if (!out.length) {
      res.innerHTML = '<div class="no-results">No results</div>';
      res.hidden = false;
      return;
    }
    out.slice(0, 20).forEach(function (r) {
      var a = document.createElement("a");
      a.href = r.e.u;
      a.className = "result";
      var t = document.createElement("div");
      t.className = "r-title";
      t.textContent = r.e.t;
      var sn = document.createElement("div");
      sn.className = "r-snip";
      var from = Math.max(0, r.pos - 70), to = r.pos + 110;
      if (from > 0) sn.appendChild(document.createTextNode("…"));
      sn.appendChild(highlight(r.e.s.slice(from, to), terms));
      if (to < r.e.s.length) sn.appendChild(document.createTextNode("…"));
      a.appendChild(t);
      a.appendChild(sn);
      res.appendChild(a);
    });
    res.hidden = false;
  }

  var deb;
  if (box && res) {
    box.addEventListener("focus", ensureIndex);
    box.addEventListener("input", function () {
      ensureIndex();
      clearTimeout(deb);
      deb = setTimeout(doSearch, 120);
    });
    box.addEventListener("keydown", function (e) {
      var items = res.querySelectorAll("a.result");
      if (e.key === "Escape") { hideResults(); box.blur(); }
      else if (e.key === "ArrowDown") {
        e.preventDefault(); sel = Math.min(sel + 1, items.length - 1);
      } else if (e.key === "ArrowUp") {
        e.preventDefault(); sel = Math.max(sel - 1, 0);
      } else if (e.key === "Enter") {
        var target = items[sel < 0 ? 0 : sel];
        if (target) location.href = target.href;
      } else { return; }
      items.forEach(function (a, i) { a.classList.toggle("sel", i === sel); });
    });
    document.addEventListener("click", function (e) {
      if (!res.contains(e.target) && e.target !== box) hideResults();
    });
  }

  // -- heading anchors ------------------------------------------------------
  var copyText = function (t) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(t);
      return;
    }
    var ta = document.createElement("textarea");
    ta.value = t;
    ta.style.cssText = "position:fixed;opacity:0";
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); } catch (e) {}
    document.body.removeChild(ta);
  };
  document
    .querySelectorAll(".content h1,.content h2,.content h3,.content h4")
    .forEach(function (h) {
      var host = h.id ? h : h.closest("[id]");
      if (!host) return;
      var a = document.createElement("a");
      a.className = "anchor";
      a.href = "#" + host.id;
      a.textContent = "#";
      a.title = "Copy link to this section";
      a.setAttribute("aria-label", "Copy link to this section");
      a.addEventListener("click", function (e) {
        e.preventDefault();
        location.hash = host.id;
        copyText(location.href.split("#")[0] + "#" + host.id);
        a.classList.add("copied");
        a.textContent = "✓";
        setTimeout(function () {
          a.classList.remove("copied");
          a.textContent = "#";
        }, 1200);
      });
      h.appendChild(a);
    });

  // -- scroll spy -----------------------------------------------------------
  var page = location.pathname.split("/").pop() || "index.html";
  var spyLinks = [], spyEls = [];
  document.querySelectorAll("nav.sidebar a[href]").forEach(function (a) {
    var href = a.getAttribute("href"), i = href.indexOf("#");
    if (i < 0) return;
    var p = href.slice(0, i);
    if (p && p !== page) return;
    var el = document.getElementById(decodeURIComponent(href.slice(i + 1)));
    if (!el) return;
    spyLinks.push(a);
    spyEls.push(el);
  });
  var spyCur = null, spyTick = false;
  var spyNav = document.querySelector("nav.sidebar");
  function spyUpdate() {
    spyTick = false;
    var cur = null;
    for (var i = 0; i < spyEls.length; i++) {
      if (spyEls[i].getBoundingClientRect().top <= 88) cur = spyLinks[i];
      else break;
    }
    if (cur === spyCur) return;
    if (spyCur) spyCur.classList.remove("spy");
    spyCur = cur;
    if (spyCur) {
      spyCur.classList.add("spy");
      var r = spyCur.getBoundingClientRect();
      var b = spyNav.getBoundingClientRect();
      if (r.top < b.top + 4 || r.bottom > b.bottom - 4)
        spyCur.scrollIntoView({ block: "nearest" });
    }
  }
  if (spyEls.length) {
    window.addEventListener(
      "scroll",
      function () {
        if (!spyTick) {
          spyTick = true;
          requestAnimationFrame(spyUpdate);
        }
      },
      { passive: true }
    );
    spyUpdate();
  }
})();
"""

PAGE = """\
<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8"/>
<script>(function(){var t="system";try{t=localStorage.getItem("bs-theme")||"system"}catch(e){}
document.documentElement.dataset.theme=t;})()</script>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
<meta name="theme-color" content="#ffffff" media="(prefers-color-scheme:light)"/>
<meta name="theme-color" content="#17181a" media="(prefers-color-scheme:dark)"/>
<title>{page_title}</title>
{book_links}<link rel="stylesheet" href="assets/site.css"/>{extra_head}
</head>
<body>
<a class="skip" href="#content">Skip to content</a>
<header class="top">
<button id="menu-btn" aria-label="Toggle table of contents"
 aria-controls="sidebar" aria-expanded="true">&#9776;</button>
<span class="booktitle"><a href="index.html">{book_title}</a></span>
<span class="spacer"></span>
<div class="search">
<input id="search-box" type="search" placeholder="Search book…"
 autocomplete="off" spellcheck="false" aria-label="Search this book"/>
<div id="search-results" class="search-results" hidden></div>
</div>
<button id="theme-btn" aria-label="Theme: system"
 title="Theme: system">&#9680;</button>
<a class="toc-link" href="toc.html">Contents</a>
</header>
<div class="scrim" id="scrim"></div>
<nav class="sidebar" id="sidebar">{sidebar}</nav>
<main>
<div class="content" id="content">
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
    for img in body.iter("img"):
        img.set("loading", "lazy")
        img.set("decoding", "async")
    styles = "".join(html.tostring(s, encoding="unicode") for s in doc.iter("style"))
    body_html = (body.text or "") + "".join(
        html.tostring(el, encoding="unicode") for el in body
    )
    return styles, body_html


SECTION_TAGS = frozenset(("h1", "h2", "h3", "h4"))


def _nearest_id(el):
    while el is not None:
        i = el.get("id")
        if i:
            return i
        el = el.getparent()
    return ""


def _search_index(chapters, oebps_dir):
    """One entry per heading-delimited section: {t: title, u: url, s: text}."""
    entries = []
    for ch in chapters:
        path = os.path.join(oebps_dir, ch["filename"].replace(".html", ".xhtml"))
        if not os.path.isfile(path):
            continue
        with open(path, "rb") as f:
            raw = f.read()
        if b'epub:type="index"' in raw:
            continue  # the index chapter is already an index
        body = html.parse(path).getroot().find("body")
        if body is None:
            continue
        page = _page_name(ch["filename"])
        cur = {"t": ch["title"], "u": page, "s": []}
        for el in body.iter():
            if el.tag in SECTION_TAGS:
                text = " ".join(" ".join(cur["s"]).split())
                if text:
                    entries.append({"t": cur["t"], "u": cur["u"], "s": text})
                frag = _nearest_id(el)
                title = " ".join("".join(el.itertext()).split()) or cur["t"]
                cur = {"t": title, "u": page + (f"#{frag}" if frag else ""), "s": []}
            if el.text:
                cur["s"].append(el.text)
            if el.tail:
                cur["s"].append(el.tail)
        text = " ".join(" ".join(cur["s"]).split())
        if text:
            entries.append({"t": cur["t"], "u": cur["u"], "s": text})
    return entries


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
    # web_dir is fully generated — clear it so stale pages can't linger.
    if os.path.isdir(web_dir):
        shutil.rmtree(web_dir)
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

    lang = info.get("language") or "en"

    def render(
        page_title, sidebar_current, body, pager="", into="index.html", extra_head=""
    ):
        page = PAGE.replace("{lang}", escape(lang))
        page = page.replace("{page_title}", escape(page_title))
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
        rel_links = ""
        if i > 0:
            rel_links += (
                f'<link rel="prev" href="{_page_name(flat[i - 1]["filename"])}"/>'
            )
        if i + 1 < len(flat):
            rel_links += (
                f'<link rel="next" href="{_page_name(flat[i + 1]["filename"])}"/>'
            )
        render(
            f"{ch['title']} — {title}",
            _stem(ch["filename"]),
            body,
            pager=_pager(flat, i),
            into=_page_name(ch["filename"]),
            extra_head=styles + rel_links,
        )

    # Client-side search index
    entries = _search_index(flat, oebps_dir)
    with open(os.path.join(assets, "search-index.js"), "w") as f:
        f.write("window.BS_SEARCH=")
        f.write(json.dumps(entries, ensure_ascii=False, separators=(",", ":")))
        f.write(";")

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
    og = (
        f'<meta property="og:title" content="{escape(title)}"/>'
        '<meta property="og:type" content="book"/>'
    )
    if authors:
        og += f'<meta name="author" content="{escape(authors)}"/>'
    if info.get("description"):
        desc = " ".join(info["description"].split())[:300]
        og += (
            f'<meta name="description" content="{escape(desc)}"/>'
            f'<meta property="og:description" content="{escape(desc)}"/>'
        )
    if cover_src:
        og += f'<meta property="og:image" content="{escape(cover_src)}"/>'
    render(
        title,
        None,
        f'<div class="index-hero">{hero}</div>',
        into="index.html",
        extra_head=og,
    )

    return web_dir
