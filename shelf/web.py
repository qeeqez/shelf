"""Generate a static web-reader version of the book (sre.google-style)."""

import json
import os
import shutil
from xml.sax.saxutils import escape

from lxml import html

FALLBACK_ICON = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect width="64" height="64" rx="12" fill="#1a73e8"/>
<path d="M14 15c6-2 12-2 18 2v31c-6-4-12-4-18-2zM50 15c-6-2-12-2-18 2v31c6-4 12-4 18-2z"
 fill="#fff"/>
</svg>
"""

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
nav.sidebar li a.spy{color:var(--accent)}
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
#menu-btn,#settings-btn{width:36px;height:36px;
padding:0;display:flex;align-items:center;justify-content:center;
line-height:1}
.settings{position:relative}
.settings-panel{position:absolute;right:0;top:calc(100% + 4px);z-index:30;
background:var(--chrome);border:1px solid var(--line);border-radius:10px;
box-shadow:var(--elev);padding:5px;min-width:210px;
animation:dropin .15s ease}
.settings-panel button{display:flex;align-items:center;gap:10px;
width:100%;padding:8px 10px;font-size:13.5px;border-radius:7px;
color:var(--fg);background:none;border:0;cursor:pointer;text-align:left}
.settings-panel button:hover{background:var(--hover)}
.settings-panel button[aria-pressed="true"]{color:var(--accent)}
.settings-panel .tglyph,.settings-panel svg{flex:none;display:flex}
.progress{position:absolute;left:0;bottom:-1px;height:2px;width:0;
background:var(--accent);pointer-events:none}
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
.note-tip{position:fixed;z-index:40;max-width:min(420px,92vw);
max-height:45vh;overflow-y:auto;background:var(--chrome);color:var(--fg);
border:1px solid var(--line);border-radius:8px;box-shadow:var(--elev);
padding:12px 16px;font-size:14px;line-height:1.55;
animation:dropin .15s ease;scrollbar-width:thin;
scrollbar-color:var(--muted) transparent}
.note-tip p{margin:0 0 8px}
.note-tip p:last-child{margin-bottom:0}
.keys{position:fixed;inset:0;z-index:60;display:flex;align-items:center;
justify-content:center;background:rgba(0,0,0,.42)}
.keys[hidden]{display:none}
.keys .panel{background:var(--chrome);color:var(--fg);
border:1px solid var(--line);border-radius:10px;box-shadow:var(--elev);
padding:18px 26px;max-width:92vw;font-size:14px;animation:dropin .15s ease}
.keys h2{font-size:15px;margin:0 0 10px}
.keys table{border-collapse:collapse}
.keys td{padding:3px 0;color:var(--muted)}
.keys td:first-child{padding-right:18px;color:var(--fg);font-weight:600;
white-space:nowrap}
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
nav.sidebar li span.branch{display:block;padding:6px 24px;color:var(--muted);
font-size:13px;line-height:1.4;font-weight:600}
nav.sidebar li a:hover{background:var(--hover);text-decoration:none}
nav.sidebar li a.active{color:var(--accent);background:var(--active)}
nav.sidebar ul ul a,nav.sidebar ul ul span.branch{padding-left:42px}
nav.sidebar ul ul ul a,nav.sidebar ul ul ul span.branch{padding-left:60px}
nav.sidebar ul ul ul ul a,nav.sidebar ul ul ul ul span.branch{padding-left:78px}
main{padding:76px 24px 64px;margin-left:300px;transition:margin .2s ease}
body.sidebar-hidden main{margin-left:0}
.content{max-width:740px;margin:0 auto;background:var(--card-bg);
color:var(--card-fg);border-radius:var(--card-r);padding:var(--card-pad);
transition:background-color .25s ease,color .25s ease,filter .3s ease,
max-width .25s ease}
[data-wide] .content,[data-wide] .pager{max-width:none}
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
.pre-wrap{position:relative}
.copy-btn{position:absolute;top:6px;right:6px;padding:3px 10px;
font:inherit;font-size:12px;line-height:1.4;border:1px solid var(--line);
border-radius:6px;background:var(--chrome);color:var(--muted);
cursor:pointer;opacity:0;transition:opacity .15s ease}
.pre-wrap:hover .copy-btn,.copy-btn:focus{opacity:1}
.copy-btn.copied{color:var(--accent);border-color:var(--accent);
font-weight:600}
@media (hover:none){.copy-btn{opacity:.75}}
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
/* Book CSS usually styles its own footnotes block (higher specificity
   wins) — this is the fallback for books that don't. */
.content [data-type="footnotes"]{border-top:1px solid var(--line);
margin-top:40px;font-size:.92em;color:var(--content-muted)}
@keyframes fnhl{0%{background:var(--mark)}to{background:transparent}}
/* Flash the landing spot after a noteref jump — footnotes cluster at the
   page foot and the marker back-link is a tiny sup, both easy to lose. */
.content [data-type="footnote"]:target,
.content a[data-type="noteref"]:target{animation:fnhl 2s ease-out;
border-radius:3px}
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
   diagrams become white-on-dark instead of white rectangles — unless the
   reader opts out: data-imginv="off" re-inverts media back to original. */
:root[data-theme="dark"] .content{filter:invert(1) hue-rotate(180deg)}
@media (prefers-color-scheme:dark){
:root:not([data-theme="light"]) .content{filter:invert(1) hue-rotate(180deg)}
}
:root[data-theme="dark"][data-imginv="off"] .content img,
:root[data-theme="dark"][data-imginv="off"] .content svg,
:root[data-theme="dark"][data-imginv="off"] .content video{
filter:invert(1) hue-rotate(180deg)}
@media (prefers-color-scheme:dark){
:root:not([data-theme="light"])[data-imginv="off"] .content img,
:root:not([data-theme="light"])[data-imginv="off"] .content svg,
:root:not([data-theme="light"])[data-imginv="off"] .content video{
filter:invert(1) hue-rotate(180deg)}
}
@media print{
header.top,nav.sidebar,.pager,.skip,.anchor,.copy-btn,.note-tip,
.keys{display:none}
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
  // Sidebar TOC ships as assets/toc.js (SHELF_TOC) — one shared file instead
  // of ~64KB inlined into every chapter page. Chapter pages embed only a
  // <noscript> fallback link to toc.html.
  // pathname is percent-encoded; TOC hrefs are not — decode before matching.
  var page =
    decodeURIComponent(location.pathname.split("/").pop()) || "index.html";
  var navEl = document.querySelector("nav.sidebar");
  if (navEl && window.SHELF_TOC) {
    navEl.innerHTML = window.SHELF_TOC;
    // Mark the current chapter — shared markup can't carry per-page state.
    // Only the first match (the chapter's own TOC entry): section links
    // point into the same page but aren't "the current page".
    var marked = false;
    navEl.querySelectorAll("a[href]").forEach(function (a) {
      if (marked || a.getAttribute("href").split("#")[0] !== page) return;
      marked = true;
      a.classList.add("active");
      a.setAttribute("aria-current", "page");
    });
  }

  var key = "shelf-sidebar";
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

  // -- sidebar scroll position ---------------------------------------------
  // Keep the TOC where the reader left it across page switches. Fresh tabs
  // (no saved position) reveal the active chapter instead.
  var scrollKey = "shelf-sidebar-scroll";
  var sb = document.querySelector("nav.sidebar");
  if (sb) {
    var saved = null;
    try {
      saved = sessionStorage.getItem(scrollKey);
    } catch (e) {}
    if (saved !== null) {
      sb.scrollTop = parseInt(saved, 10) || 0;
    } else {
      var activeLink = sb.querySelector("a.active");
      if (activeLink) activeLink.scrollIntoView({ block: "center" });
    }
    var sbTick = false;
    sb.addEventListener(
      "scroll",
      function () {
        if (sbTick) return;
        sbTick = true;
        requestAnimationFrame(function () {
          sbTick = false;
          try {
            sessionStorage.setItem(scrollKey, String(sb.scrollTop));
          } catch (e) {}
        });
      },
      { passive: true }
    );
  }
  // -- reading position + progress -----------------------------------------
  // Each page remembers its scroll offset — leaving a chapter and coming
  // back lands where the reader stopped, and index.html's "Start reading"
  // becomes a resume point. Keys carry the site root so two books on the
  // shared file:// origin never collide (both have a ch01.html). An
  // explicit #hash always wins: TOC/search links target sections on
  // purpose and must not be overridden by stale position.
  var siteRoot = location.pathname
    .replace(/[/]chapters[/][^/]*$/, "/")
    .replace(/[/][^/]*$/, "/");
  var posKey = "shelf-pos:" + siteRoot + page;
  var posY = null;
  try {
    posY = localStorage.getItem(posKey);
  } catch (e) {}
  if (!location.hash && posY !== null) {
    var y = parseInt(posY, 10);
    if (y > 0) {
      window.scrollTo(0, y);
      // The page can still be short here — images below the fold without
      // reserved space clamp the jump. Re-apply once layout is final.
      window.addEventListener("load", function () {
        window.scrollTo(0, y);
      });
    }
  }
  if (location.pathname.indexOf("/chapters/") >= 0) {
    try {
      localStorage.setItem("shelf-last:" + siteRoot, page);
    } catch (e) {}
  }
  var startLink = document.querySelector(".index-hero a.start");
  if (startLink) {
    var lastPage = null;
    try {
      lastPage = localStorage.getItem("shelf-last:" + siteRoot);
    } catch (e) {}
    if (lastPage) {
      startLink.setAttribute("href", "chapters/" + lastPage);
      startLink.textContent = "Continue reading →";
    }
  }
  // A 2px bar under the header edge — enough to judge "how far into this
  // chapter am I" without spending layout space on it.
  var progBar = document.createElement("div");
  progBar.className = "progress";
  progBar.setAttribute("aria-hidden", "true");
  var topBar = document.querySelector("header.top");
  if (topBar) topBar.appendChild(progBar);
  var posTick = false;
  var onPageScroll = function () {
    posTick = false;
    try {
      localStorage.setItem(posKey, String(window.scrollY));
    } catch (e) {}
    var de = document.documentElement;
    var max = de.scrollHeight - de.clientHeight;
    progBar.style.width = (max > 0 ? (window.scrollY / max) * 100 : 0) + "%";
  };
  window.addEventListener(
    "scroll",
    function () {
      if (!posTick) {
        posTick = true;
        requestAnimationFrame(onPageScroll);
      }
    },
    { passive: true }
  );
  onPageScroll();

  // -- display settings popover -------------------------------------------
  var setBtn = document.getElementById("settings-btn");
  var setPanel = document.getElementById("settings-panel");
  function setOpen(open) {
    if (!setPanel) return;
    setPanel.hidden = !open;
    setBtn.setAttribute("aria-expanded", open ? "true" : "false");
  }
  if (setBtn && setPanel) {
    setBtn.addEventListener("click", function () {
      setOpen(setPanel.hidden);
    });
    document.addEventListener("click", function (e) {
      var outside =
        !setPanel.contains(e.target) &&
        e.target !== setBtn &&
        !setBtn.contains(e.target);
      if (!setPanel.hidden && outside) setOpen(false);
    });
  }

  // -- theme (system / light / dark) --------------------------------------
  var themeKey = "shelf-theme";
  var themeBtn = document.getElementById("theme-btn");
  var mq =
    window.matchMedia && window.matchMedia("(prefers-color-scheme:dark)");
  var SVG_OPEN =
    '<svg width="18" height="18" viewBox="0 0 16 16" fill="none" ' +
    'stroke="currentColor" stroke-width="1.5" stroke-linecap="round" ' +
    'stroke-linejoin="round" aria-hidden="true">';
  var GLYPHS = {
    system:
      SVG_OPEN +
      '<circle cx="8" cy="8" r="5.5"/>' +
      '<path d="M8 2.5A5.5 5.5 0 008 13.5z" fill="currentColor" ' +
      'stroke="none"/></svg>',
    light:
      SVG_OPEN +
      '<circle cx="8" cy="8" r="3"/>' +
      '<path d="M8 1.5v1.5M8 13v1.5M1.5 8H3M13 8h1.5M3.4 3.4l1 1' +
      'M11.6 11.6l1 1M12.6 3.4l-1 1M4.4 11.6l-1 1"/></svg>',
    dark:
      SVG_OPEN +
      '<path d="M13.5 9.5A6 6 0 116.5 2.5a4.8 4.8 0 007 7z"/></svg>',
  };
  function applyTheme(t) {
    if (!GLYPHS[t]) t = "system"; // unknown stored value → fall back
    document.documentElement.dataset.theme = t;
    if (themeBtn) {
      // innerHTML on the button would wipe the .lbl span — swap the
      // glyph and label separately.
      themeBtn.querySelector(".tglyph").innerHTML = GLYPHS[t];
      themeBtn.querySelector(".lbl").textContent = "Theme: " + t;
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

  // -- full-width content toggle -------------------------------------------
  var wideBtn = document.getElementById("wide-btn");
  if (wideBtn) {
    var syncWide = function () {
      wideBtn.setAttribute(
        "aria-pressed",
        document.documentElement.dataset.wide === "1" ? "true" : "false"
      );
    };
    wideBtn.addEventListener("click", function () {
      var w = document.documentElement.dataset.wide === "1";
      if (w) delete document.documentElement.dataset.wide;
      else document.documentElement.dataset.wide = "1";
      try {
        localStorage.setItem("shelf-wide", w ? "0" : "1");
      } catch (e) {}
      syncWide();
    });
    syncWide();
  }

  // -- image inversion in dark mode ----------------------------------------
  // Whole-content inversion also flips images; some readers prefer real
  // colors for photos. data-imginv="off" re-inverts media back via CSS.
  var imgBtn = document.getElementById("imginv-btn");
  if (imgBtn) {
    var syncImgInv = function () {
      var on = document.documentElement.dataset.imginv !== "off";
      imgBtn.setAttribute("aria-pressed", on ? "true" : "false");
      imgBtn.title = on
        ? "Dark mode: images inverted (click for original colors)"
        : "Dark mode: images original (click to invert)";
    };
    imgBtn.addEventListener("click", function () {
      var off = document.documentElement.dataset.imginv === "off";
      if (off) delete document.documentElement.dataset.imginv;
      else document.documentElement.dataset.imginv = "off";
      try {
        localStorage.setItem("shelf-imginv", off ? "1" : "0");
      } catch (e) {}
      syncImgInv();
    });
    syncImgInv();
  }
  // -- footnote previews -----------------------------------------------------
  // O'Reilly chapters carry dense noteref→footnote pairs (a chapter can
  // have 100+). Hovering or focusing a ref pops the note in place — no
  // jump, no lost position. Clicking still jumps (the note flashes
  // :target on arrival); touch users keep the classic behaviour for free.
  var tip = null, tipFor = null, tipHide = 0;
  var TIP_ID = "shelf-note-tip";
  function hideTip() {
    if (!tip) return;
    if (tipFor) tipFor.removeAttribute("aria-describedby");
    tip.remove();
    tip = tipFor = null;
  }
  function queueHide() {
    clearTimeout(tipHide);
    tipHide = setTimeout(hideTip, 140);
  }
  function showTip(a) {
    if (tipFor === a) return;
    var href = a.getAttribute("href") || "";
    var i = href.indexOf("#");
    if (i < 0) return;
    var note = null;
    try {
      note = document.getElementById(decodeURIComponent(href.slice(i + 1)));
    } catch (e) {}
    if (!note) return; // note on another page — plain navigation stands
    hideTip();
    var clone = note.cloneNode(true);
    clone.removeAttribute("id");
    clone.querySelectorAll("[id]").forEach(function (n) {
      n.removeAttribute("id");
    });
    // The footnote's own back-link ("return to text") is chrome, not
    // prose — drop it so the popup starts with the note body. Citation
    // links deeper in the note stay clickable.
    var back = clone.querySelector("a[href*='#']");
    if (back) {
      var bt = null;
      try {
        bt = document.getElementById(
          decodeURIComponent(back.getAttribute("href").split("#")[1] || "")
        );
      } catch (e) {}
      if (bt && bt.getAttribute("data-type") === "noteref") {
        (back.closest("sup") || back).remove();
        // "[1] note" / "<sup>1</sup> note" → strip the orphaned bracket
        clone.innerHTML = clone.innerHTML.replace(/^[\\s\\[\\]]+/, "");
      }
    }
    var d = document.createElement("div");
    d.className = "note-tip";
    d.id = TIP_ID;
    d.setAttribute("role", "tooltip");
    d.appendChild(clone);
    document.body.appendChild(d);
    var r = a.getBoundingClientRect();
    d.style.left =
      Math.max(8, Math.min(r.left, window.innerWidth - d.offsetWidth - 8)) +
      "px";
    var top = r.bottom + 6;
    if (top + d.offsetHeight > window.innerHeight - 4)
      top = Math.max(4, r.top - d.offsetHeight - 6); // flip above the ref
    d.style.top = top + "px";
    tip = d;
    tipFor = a;
    a.setAttribute("aria-describedby", TIP_ID);
    // The note is hoverable so links inside it can be followed — a short
    // grace period bridges the gap between ref and popup.
    d.addEventListener("mouseenter", function () {
      clearTimeout(tipHide);
    });
    d.addEventListener("mouseleave", queueHide);
  }
  var refOf = function (e) {
    return (
      e.target.closest && e.target.closest('a[data-type="noteref"]')
    );
  };
  document.addEventListener("mouseover", function (e) {
    var a = refOf(e);
    if (a) {
      clearTimeout(tipHide);
      showTip(a);
    }
  });
  document.addEventListener("mouseout", function (e) {
    var a = refOf(e);
    if (!a) return;
    if (tip && e.relatedTarget && tip.contains(e.relatedTarget)) return;
    queueHide();
  });
  document.addEventListener("focusin", function (e) {
    var a = refOf(e);
    if (a) showTip(a);
  });
  document.addEventListener("focusout", function (e) {
    if (refOf(e)) queueHide();
  });
  document.addEventListener("click", function (e) {
    if (refOf(e)) hideTip(); // jump + :target flash takes over
  });
  window.addEventListener(
    "scroll",
    function () {
      if (tip) hideTip(); // fixed position would go stale
    },
    { passive: true }
  );

  // -- keyboard shortcuts ----------------------------------------------------
  var help = null;
  var SHORTCUTS = [
    ["/", "Search the book"],
    ["j / →", "Next chapter"],
    ["k / ←", "Previous chapter"],
    ["t", "Cycle theme (system → light → dark)"],
    ["w", "Toggle full-width content"],
    ["i", "Invert images in dark mode"],
    ["s", "Display settings"],
    ["Esc", "Close panels and sidebar"],
    ["?", "This help"],
  ];
  function toggleHelp(show) {
    if (!help) {
      help = document.createElement("div");
      help.className = "keys";
      help.id = "keys-help";
      help.hidden = true;
      help.setAttribute("role", "dialog");
      help.setAttribute("aria-modal", "true");
      help.setAttribute("aria-label", "Keyboard shortcuts");
      var rows = "";
      SHORTCUTS.forEach(function (r) {
        rows += "<tr><td>" + r[0] + "</td><td>" + r[1] + "</td></tr>";
      });
      help.innerHTML =
        '<div class="panel" tabindex="-1"><h2>Keyboard shortcuts</h2>' +
        "<table>" +
        rows +
        "</table></div>";
      help.addEventListener("click", function (e) {
        if (e.target === help) toggleHelp(false);
      });
      document.body.appendChild(help);
    }
    var open = show === undefined ? help.hidden : show;
    help.hidden = !open;
    if (open) help.querySelector(".panel").focus();
  }
  document.addEventListener("keydown", function (e) {
    if (/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === "Escape") {
      if (help && !help.hidden) {
        toggleHelp(false);
        return;
      }
      if (tip) {
        hideTip();
        return;
      }
      if (setPanel && !setPanel.hidden) {
        setOpen(false);
        return;
      }
      if (!isHidden()) setSidebar(false);
      return;
    }
    if (e.key === "?") {
      e.preventDefault();
      toggleHelp();
      return;
    }
    if (help && !help.hidden) return; // modal up — other shortcuts inert
    var box = document.getElementById("search-box");
    if (e.key === "/" && box) {
      e.preventDefault();
      box.focus();
      return;
    }
    if (e.key === "t" && themeBtn) {
      themeBtn.click();
      return;
    }
    if (e.key === "w" && wideBtn) {
      wideBtn.click();
      return;
    }
    if (e.key === "i" && imgBtn) {
      imgBtn.click();
      return;
    }
    if (e.key === "s" && setBtn && setPanel) {
      setOpen(setPanel.hidden);
      return;
    }
    var sel =
      e.key === "ArrowLeft" || e.key === "k"
        ? ".pager a.prev"
        : e.key === "ArrowRight" || e.key === "j"
          ? ".pager a.next"
          : null;
    if (!sel) return;
    var a = document.querySelector(sel);
    if (a) location.href = a.href;
  });

  // -- client-side search --------------------------------------------------
  var box = document.getElementById("search-box");
  var res = document.getElementById("search-results");
  var idx = null, idxLoading = false, sel = -1;

  // Root prefix for root-relative paths: "" on index/toc, "../" inside chapters/.
  var script = document.currentScript;
  var root = (script && script.getAttribute("data-root")) || "";

  function ensureIndex() {
    if (idx || idxLoading) return;
    idxLoading = true;
    var s = document.createElement("script");
    s.src = root + "assets/search-index.js";
    s.onload = function () {
      idx = window.SHELF_SEARCH || [];
      for (var i = 0; i < idx.length; i++) {
        idx[i]._tl = idx[i].t.toLowerCase();
        idx[i]._sl = idx[i].s.toLowerCase();
      }
      doSearch(); // a query may have been typed while the index loaded
    };
    s.onerror = function () {
      idx = []; // missing index → "No results" instead of a dead search box
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
      // Index entries store bare chapter names; from inside chapters/ the
      // "../" root prefix lands back in the same directory.
      a.href = root + "chapters/" + r.e.u;
      a.className = "result";
      a.setAttribute("role", "option");
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
      items.forEach(function (a, i) {
        a.classList.toggle("sel", i === sel);
        a.setAttribute("aria-selected", i === sel ? "true" : "false");
      });
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

  // -- copy button on code listings ------------------------------------------
  // Technical readers lift snippets constantly; pre.textContent is clean
  // text even with Pygments <code> markup inside. The button lives in a
  // wrapper, not inside the pre, so overflow-x scrolling can't push it
  // off-screen.
  document.querySelectorAll(".content pre").forEach(function (pre) {
    if (!pre.textContent.trim()) return;
    var w = document.createElement("div");
    w.className = "pre-wrap";
    pre.parentNode.insertBefore(w, pre);
    w.appendChild(pre);
    var b = document.createElement("button");
    b.type = "button";
    b.className = "copy-btn";
    b.textContent = "Copy";
    b.setAttribute("aria-label", "Copy code to clipboard");
    b.addEventListener("click", function () {
      copyText(pre.textContent);
      b.classList.add("copied");
      b.textContent = "Copied";
      setTimeout(function () {
        b.classList.remove("copied");
        b.textContent = "Copy";
      }, 1200);
    });
    w.appendChild(b);
  });

  // -- scroll spy -----------------------------------------------------------
  var spyLinks = [], spyEls = [];
  document.querySelectorAll("nav.sidebar a[href]").forEach(function (a) {
    var href = a.getAttribute("href"), i = href.indexOf("#");
    if (i < 0) return;
    var p = href.slice(0, i);
    if (p && p !== page) return;
    var el = null;
    try {
      el = document.getElementById(decodeURIComponent(href.slice(i + 1)));
    } catch (e) {}
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
<script>(function(){var t="system";try{t=localStorage.getItem("shelf-theme")||"system"}catch(e){}
document.documentElement.dataset.theme=t;
try{if(localStorage.getItem("shelf-wide")==="1")document.documentElement.dataset.wide="1"}catch(e){}
try{if(localStorage.getItem("shelf-imginv")==="0")document.documentElement.dataset.imginv="off"}catch(e){}})()</script>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
<meta name="theme-color" content="#ffffff" media="(prefers-color-scheme:light)"/>
<meta name="theme-color" content="#17181a" media="(prefers-color-scheme:dark)"/>
<title>{page_title}</title>
{book_links}<link rel="stylesheet" href="{root}assets/site.css"/>
{favicon}{extra_head}
</head>
<body>
<a class="skip" href="#content">Skip to content</a>
<header class="top">
<button id="menu-btn" aria-label="Toggle table of contents"
 aria-controls="sidebar" aria-expanded="true"><svg width="18" height="18"
 viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"
 stroke-linecap="round" aria-hidden="true"><path
 d="M2 4h12M2 8h12M2 12h12"/></svg></button>
<span class="booktitle"><a href="{root}index.html">{book_title}</a></span>
<span class="spacer"></span>
<div class="search" role="search">
<input id="search-box" type="search" placeholder="Search book…"
 autocomplete="off" spellcheck="false" aria-label="Search this book"/>
<div id="search-results" class="search-results" role="listbox" hidden></div>
</div>
<div class="settings">
<button id="settings-btn" aria-label="Display settings" aria-expanded="false"
 aria-haspopup="true" aria-controls="settings-panel"
 title="Display settings"><svg width="18" height="18" viewBox="0 0 24 24"
 fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"
 stroke-linejoin="round" aria-hidden="true"><path
 d="M12.22 2h-.44a2 2 0 00-2 2v.18a2 2 0 01-1 1.73l-.43.25a2 2 0 01-2 0l-.15-.08a2
 2 0 00-2.73.73l-.22.38a2 2 0 00.73 2.73l.15.1a2 2 0 011 1.72v.51a2 2 0
 01-1 1.74l-.15.09a2 2 0 00-.73 2.73l.22.38a2 2 0 002.73.73l.15-.08a2 2 0
 012 0l.43.25a2 2 0 011 1.73V20a2 2 0 002 2h.44a2 2 0 002-2v-.18a2 2 0
 011-1.73l.43-.25a2 2 0 012 0l.15.08a2 2 0 002.73-.73l.22-.39a2 2 0
 00-.73-2.73l-.15-.08a2 2 0 01-1-1.74v-.5a2 2 0 011-1.74l.15-.09a2 2 0
 00.73-2.73l-.22-.38a2 2 0 00-2.73-.73l-.15.08a2 2 0 01-2 0l-.43-.25a2 2 0
 01-1-1.73V4a2 2 0 00-2-2z"/><circle cx="12" cy="12" r="3"/></svg></button>
<div id="settings-panel" class="settings-panel" hidden>
<button id="theme-btn" aria-label="Theme: system"
 title="Theme: system"><span class="tglyph">&#9680;</span>
 <span class="lbl">Theme: system</span></button>
<button id="wide-btn" aria-label="Toggle full-width content"
 aria-pressed="false" title="Toggle full-width content"><svg width="18"
 height="18" viewBox="0 0 16 16" fill="none" stroke="currentColor"
 stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"
 aria-hidden="true"><path d="M1.5 8h13M4 5.5 1.5 8 4 10.5M12 5.5 14.5 8 12
 10.5"/></svg><span class="lbl">Full width</span></button>
<button id="imginv-btn" aria-label="Toggle image inversion in dark mode"
 aria-pressed="true" title="Invert images in dark mode"><svg width="18"
 height="18" viewBox="0 0 16 16" fill="none" stroke="currentColor"
 stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"
 aria-hidden="true"><rect x="1.5" y="3" width="13" height="10" rx="1.5"/>
 <circle cx="5.5" cy="6.5" r="1" fill="currentColor" stroke="none"/>
 <path d="M2.5 11.5 6 8l2.5 2.5L11 8l2.5 2.5" fill="none"/></svg>
 <span class="lbl">Invert images</span></button>
</div>
</div>
<a class="toc-link" href="{root}toc.html">Contents</a>
</header>
<div class="scrim" id="scrim"></div>
<nav class="sidebar" id="sidebar" aria-label="Table of contents">{sidebar}</nav>
{toc_script}
<main>
<div class="content" id="content">
{body}
</div>
{pager}
</main>
<script src="{root}assets/site.js" data-root="{root}"></script>
</body>
</html>
"""


# escape() only handles &<> by default — every interpolated value inside a
# double-quoted attribute also needs " escaped or it breaks out of the tag.
_ATTR_ENTITIES = {'"': "&quot;"}


def _attr(text):
    return escape(text, _ATTR_ENTITIES)


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


XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
ASSET_DIRS = ("Images/", "Fonts/", "Styles/")


def _chapter_data(path):
    """One parse of a chapter file → (extra_head, body_html, body_element,
    is_index). Callers render body_html and index body_element — parsing
    twice per chapter (once for each) was the generator's hot spot."""
    doc = html.parse(path).getroot()
    # epub:type is a space-separated list (e.g. "index backmatter").
    is_index = any("index" in (el.get("epub:type") or "").split() for el in doc.iter())
    body = doc.find("body")
    if body is None:
        return "", "", None, is_index
    _rewrite_links(body)
    for img in body.iter("img"):
        img.set("loading", "lazy")
        img.set("decoding", "async")
    # Chapter pages live one level down in chapters/ — root-relative asset
    # paths (Images/x.png etc.) need the "../" bump.
    for el in body.iter():
        for attr in ("src", "href", "poster", XLINK_HREF):
            v = el.get(attr)
            if v and v.startswith(ASSET_DIRS):
                el.set(attr, "../" + v)
        srcset = el.get("srcset")
        if srcset:
            cands = []
            for cand in srcset.split(","):
                url, _, desc = cand.strip().partition(" ")
                if url.startswith(ASSET_DIRS):
                    url = "../" + url
                cands.append((url + " " + desc).rstrip())
            el.set("srcset", ", ".join(cands))
    # Styles living inside <body> already ride along in body_html — hoisting
    # them into extra_head as well would duplicate every rule.
    styles = "".join(
        html.tostring(s, encoding="unicode")
        for s in doc.iter("style")
        if body not in s.iterancestors()
    )
    # Hoisted head <link>s point at Styles/ — same "../" bump for chapter pages.
    styles = styles.replace('href="Styles/', 'href="../Styles/')
    body_html = (body.text or "") + "".join(
        html.tostring(el, encoding="unicode") for el in body
    )
    return styles, body_html, body, is_index


SECTION_TAGS = frozenset(("h1", "h2", "h3", "h4"))
# Elements whose text content is markup noise, not prose — indexing it gives
# search snippets full of CSS rules and MathML tag soup.
SKIP_TEXT_TAGS = frozenset(("style", "script", "noscript", "math", "svg"))


def _nearest_id(el, stop=None):
    """Closest id at or above el, not climbing past stop. <body>/<html> ids
    never make it into the generated page — they'd be phantom fragments."""
    while el is not None and el is not stop:
        i = el.get("id")
        if i:
            return i
        el = el.getparent()
    return ""


def _section_entries(body, chapter_title, page):
    """One entry per heading-delimited section: {t: title, u: url, s: text}.

    Text inside markup-noise elements (style/script/math/svg) is skipped —
    the set is precomputed once so the check is O(1) per element instead of
    an ancestor scan."""
    noise_roots, noise = set(), set()
    for tag in SKIP_TEXT_TAGS:
        for el in body.iter(tag):
            noise_roots.add(el)
            noise.add(el)
            noise.update(el.iterdescendants())

    entries = []
    cur = {"t": chapter_title, "u": page, "s": []}
    for el in body.iter():
        if el in noise:
            # A noise root's tail is ordinary text after it; descendants'
            # tails are still inside the noise.
            if el in noise_roots and el.tail:
                cur["s"].append(el.tail)
            continue
        if not isinstance(el.tag, str):
            # Comments/PIs carry no prose; the tail after them is real text.
            if el.tail:
                cur["s"].append(el.tail)
            continue
        if el.tag in SECTION_TAGS:
            text = " ".join(" ".join(cur["s"]).split())
            if text:
                entries.append({"t": cur["t"], "u": cur["u"], "s": text})
            frag = _nearest_id(el, body)
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


def _sidebar_ul(items, active_item, prefix=""):
    lis = []
    for item in items:
        cls = ' class="active" aria-current="page"' if item is active_item else ""
        children = (
            _sidebar_ul(item["children"], active_item, prefix)
            if item["children"]
            else ""
        )
        if item["href"]:
            href = prefix + _page_name(item["href"])
            if item["fragment"]:
                href += "#" + item["fragment"]
            label = f'<a href="{_attr(href)}"{cls}>{escape(item["label"])}</a>'
        else:
            label = f'<span class="branch">{escape(item["label"])}</span>'
        lis.append(f"<li>{label}{children}</li>")
    return "<ul>" + "".join(lis) + "</ul>"


def _pager(chapters, i):
    prev_link = ""
    if i > 0:
        p = chapters[i - 1]
        prev_link = (
            f'<a class="prev" href="{_attr(_page_name(p["filename"]))}">'
            f"&larr; {escape(p['title'])}</a>"
        )
    next_link = ""
    if i + 1 < len(chapters):
        n = chapters[i + 1]
        next_link = (
            f'<a class="next" href="{_attr(_page_name(n["filename"]))}">'
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

    with open(os.path.join(assets, "site.css"), "w", encoding="utf-8") as f:
        f.write(SITE_CSS)
    with open(os.path.join(assets, "site.js"), "w", encoding="utf-8") as f:
        f.write(SITE_JS)
    # The book's own cover is the favicon — instantly identifiable in tabs.
    # Generic book glyph when the book has no cover. {root} resolves per page.
    if cover_src:
        favicon = f'<link rel="icon" href="{{root}}{_attr(cover_src)}"/>'
    else:
        with open(os.path.join(assets, "icon.svg"), "w", encoding="utf-8") as f:
            f.write(FALLBACK_ICON)
        favicon = '<link rel="icon" href="{root}assets/icon.svg" type="image/svg+xml"/>'

    styles_dir = os.path.join(web_dir, "Styles")
    book_links = ""
    if os.path.isdir(styles_dir):
        book_links = "".join(
            f'<link rel="stylesheet" href="{{root}}Styles/{_attr(n)}"/>\n'
            for n in sorted(os.listdir(styles_dir))
            if n.endswith(".css")
        )

    title = info.get("title", "Book")

    lang = info.get("language") or "en"

    def render(
        page_title,
        sidebar_current,
        body,
        pager="",
        into="index.html",
        extra_head="",
        root="",
        sidebar_prefix="",
        sidebar=None,
        toc_script="",
    ):
        page = PAGE.replace("{lang}", _attr(lang))
        page = page.replace("{page_title}", escape(page_title))
        page = page.replace("{book_title}", escape(title))
        page = page.replace("{book_links}", book_links)
        if sidebar is None:
            sidebar = _sidebar_ul(
                toc_items, _first_stem_match(toc_items, sidebar_current), sidebar_prefix
            )
        page = page.replace("{sidebar}", sidebar)
        page = page.replace("{toc_script}", toc_script)
        page = page.replace("{pager}", pager)
        page = page.replace("{body}", body)
        page = page.replace("{extra_head}", extra_head)
        page = page.replace("{favicon}", favicon)
        # {root} appears both in the template and inside injected chunks
        # (book_links, favicon) — resolve last so nested placeholders expand.
        page = page.replace("{root}", root)
        with open(os.path.join(web_dir, into), "w", encoding="utf-8") as f:
            f.write(page)

    # Chapter pages live under chapters/ so index.html stands alone at the
    # web root. root="../" bumps root-relative paths; sidebar links between
    # chapters are plain filenames (same directory).
    chapters_dir = os.path.join(web_dir, "chapters")
    os.makedirs(chapters_dir, exist_ok=True)

    # The TOC sidebar is shared markup (~60KB+) — ship it once as toc.js and
    # let site.js hydrate + mark the active chapter. Chapter pages keep only
    # a no-JS link to toc.html; index/toc embed the real list.
    toc_js = "window.SHELF_TOC=" + json.dumps(_sidebar_ul(toc_items, None)) + ";"
    with open(os.path.join(assets, "toc.js"), "w", encoding="utf-8") as f:
        f.write(toc_js)

    # Only chapters whose source file exists — otherwise pagers and the
    # "Start reading" link would point at pages that were never rendered.
    flat = [
        c
        for c in chapters
        if os.path.isfile(
            os.path.join(oebps_dir, c["filename"].replace(".html", ".xhtml"))
        )
    ]
    entries = []  # search index — collected here to reuse the parse
    for i, ch in enumerate(flat):
        path = os.path.join(oebps_dir, ch["filename"].replace(".html", ".xhtml"))
        if not os.path.isfile(path):
            continue
        styles, body, body_el, is_index = _chapter_data(path)
        if body_el is not None and not is_index:
            entries.extend(
                _section_entries(body_el, ch["title"], _page_name(ch["filename"]))
            )
        rel_links = ""
        if i > 0:
            rel_links += (
                f'<link rel="prev" '
                f'href="{_attr(_page_name(flat[i - 1]["filename"]))}"/>'
            )
        if i + 1 < len(flat):
            rel_links += (
                f'<link rel="next" '
                f'href="{_attr(_page_name(flat[i + 1]["filename"]))}"/>'
            )
        render(
            f"{ch['title']} — {title}",
            _stem(ch["filename"]),
            body,
            pager=_pager(flat, i),
            into="chapters/" + _page_name(ch["filename"]),
            extra_head=styles + rel_links,
            root="../",
            sidebar=(
                '<noscript><p><a href="../toc.html">'
                "Table of contents &rarr;</a></p></noscript>"
            ),
            toc_script='<script src="../assets/toc.js"></script>',
        )

    # Client-side search index
    with open(os.path.join(assets, "search-index.js"), "w", encoding="utf-8") as f:
        f.write("window.SHELF_SEARCH=")
        f.write(json.dumps(entries, ensure_ascii=False, separators=(",", ":")))
        f.write(";")

    # Full TOC page
    render(
        f"Table of Contents — {title}",
        None,
        "<h1>Table of Contents</h1>"
        '<nav aria-label="Table of contents">'
        f"{_sidebar_ul(toc_items, None, 'chapters/')}</nav>",
        into="toc.html",
        sidebar_prefix="chapters/",
    )

    # Landing page
    hero = ""
    if cover_src:
        hero = f'<img src="{_attr(cover_src)}" alt="Cover"/>'
    authors = ", ".join(info.get("authors", []))
    hero += f"<h1>{escape(title)}</h1>"
    if authors:
        hero += f'<p class="authors">{escape(authors)}</p>'
    first = "chapters/" + _page_name(flat[0]["filename"]) if flat else "toc.html"
    # class="start" lets site.js turn this into a "Continue reading"
    # resume link once the reader has a progress history.
    hero += f'<p><a class="start" href="{_attr(first)}">Start reading &rarr;</a></p>'
    og = (
        f'<meta property="og:title" content="{_attr(title)}"/>'
        '<meta property="og:type" content="book"/>'
    )
    if authors:
        og += f'<meta name="author" content="{_attr(authors)}"/>'
    if info.get("description"):
        # Descriptions ship as HTML markup — reduce to plain text for meta.
        desc = " ".join(html.fromstring(info["description"]).text_content().split())[
            :300
        ]
        og += (
            f'<meta name="description" content="{_attr(desc)}"/>'
            f'<meta property="og:description" content="{_attr(desc)}"/>'
        )
    if cover_src:
        og += f'<meta property="og:image" content="{_attr(cover_src)}"/>'
    render(
        title,
        None,
        f'<div class="index-hero">{hero}</div>',
        into="index.html",
        extra_head=og,
        sidebar_prefix="chapters/",
    )

    return web_dir
