"""Orchestrates downloading a book: chapters, assets, EPUB assembly."""

import os
import re
import shutil
import subprocess
from urllib.parse import urljoin

from lxml import html

from . import constants as C
from .api import FONT_EXTENSIONS, ApiError, OreillyAPI
from .epub import EpubBuilder
from .pdf import build_pdf
from .session import AuthError
from .transform import Transformer
from .web import build_web


def extract_book_id(text):
    """Accept a learning.oreilly.com library URL or a bare book ID."""
    text = text.strip()
    m = re.search(r"/library/view/[^/]+/([0-9A-Za-z]+)", text)
    if m:
        return m.group(1)
    m = re.search(r"api/v2/epubs/urn:orm:book:([0-9A-Za-z]+)", text)
    if m:
        return m.group(1)
    if (
        "/" not in text
        and len(text) >= 6
        and re.search(r"\d", text)
        and re.fullmatch(r"[0-9A-Za-z_-]+", text)
    ):
        return text
    raise ValueError(
        f"Could not extract a book ID from {text!r}.\nExpected a URL like "
        f"{C.SAFARI_BASE_URL}/library/view/title/XXXXXXXXXXXXX/ or a bare numeric ID."
    )


def escape_dirname(dirname):
    if ":" in dirname and dirname.index(":") > 15:
        dirname = dirname.split(":")[0]
    dirname = re.sub(r"[<>:\"/\\|?*]", " ", dirname)
    dirname = " ".join(dirname.split())
    while len(dirname.encode("utf-8")) > 180:  # stay under 255-byte fs limits
        dirname = dirname[:-1]
    return dirname.rstrip()


def _basename(url):
    return url.split("/")[-1].split("?")[0].split("#")[0]


def _norm(s):
    return re.sub(r"\s+", "", s).lower()


def _font_faces(fonts_dir, css_text):
    """Generate @font-face rules for downloaded fonts. Aliases both the real
    family names inside each font (name IDs 1, 4, 1+2) and family names the
    book CSS requests that fuzzy-match a font (e.g. "Ubuntu Mono Ital" or
    "DejaVuSans")."""
    requested = set()
    for decl in re.findall(r"font-family:[^;}]+", css_text):
        requested.update(re.findall(r'"([^"]+)"|\'([^\']+)\'', decl))
    requested = {n for pair in requested for n in pair if n}
    rules = []
    for name in sorted(os.listdir(fonts_dir)):
        path = os.path.join(fonts_dir, name)
        try:
            from fontTools.ttLib import TTFont, TTLibError

            tt = TTFont(path, fontNumber=0)
            name_table = tt["name"]
            family = name_table.getDebugName(1) or os.path.splitext(name)[0]
            subfam = name_table.getDebugName(2) or ""
            full = name_table.getDebugName(4)
            os2 = tt["OS/2"]
            weight = 700 if os2.usWeightClass >= 600 else 400
            style = "italic" if os2.fsSelection & 0x01 else "normal"
        except (ImportError, TTLibError, KeyError, OSError):
            family, subfam, full = os.path.splitext(name)[0], "", None
            weight, style = 400, "normal"
        families = {f for f in (family, full, f"{family} {subfam}".strip()) if f}
        known = {_norm(f) for f in families}
        for q in requested:
            nq = _norm(q)
            if q not in families and (
                nq in known or any(k.startswith(nq) for k in known)
            ):
                families.add(q)
        for fam in families:
            rules.append(
                f'@font-face{{font-family:"{fam}";src:url("../Fonts/{name}");'
                f"font-weight:{weight};font-style:{style}}}"
            )
    return "".join(rules)


CSS_URL_RE = re.compile(r"url\((['\"]?)([^)'\"]+)(['\"]?)\)")


def rewrite_css_urls(content, image_names, font_names):
    """Point relative url() refs in book CSS at our Images/Fonts dirs."""
    text = content.decode("utf-8", "replace") if isinstance(content, bytes) else content

    def repl(m):
        url = m.group(2).strip()
        if url.startswith(("data:", "http:", "https:", "//")):
            return m.group(0)
        base = _basename(url)
        if base in image_names:
            return f"url({m.group(1)}../Images/{base}{m.group(3)})"
        if base in font_names:
            return f"url({m.group(1)}../Fonts/{base}{m.group(3)})"
        return m.group(0)

    return CSS_URL_RE.sub(repl, text).encode("utf-8")


class BookScraper:
    def __init__(
        self,
        oreilly_session,
        output_dir,
        kindle=False,
        pdf=False,
        web=False,
        validate=False,
        force=False,
        log=print,
        progress=None,
    ):
        self.http = oreilly_session
        self.output_dir = output_dir
        self.kindle = kindle
        self.pdf = pdf
        self.web = web
        self.validate = validate
        self.force = force
        self.log = log
        self.progress = progress or (lambda done, total, label="": None)

    def run(self, book_id):
        api = OreillyAPI(self.http, book_id)

        self.log("Retrieving book info...")
        info = api.get_book_info()
        self.log("  Title: {}".format(info["title"]))
        if info["authors"]:
            self.log("  Authors: {}".format(", ".join(info["authors"])))
        self.log(f"  ID: {book_id}")

        self.log("Retrieving chapter list...")
        chapters = api.get_book_chapters()
        self.log(f"  {len(chapters)} chapters")

        title_dir = escape_dirname(info["title"].split(",")[0]) + f" ({book_id})"
        work_dir = os.path.join(self.output_dir, title_dir)
        if self.force and os.path.isdir(work_dir):
            shutil.rmtree(work_dir)
        builder = EpubBuilder(info, book_id, work_dir)
        tx = Transformer(
            book_id, info["web_url"], kindle=self.kindle, lang=info["language"]
        )

        # Same-basename chapters would clobber each other when written flat.
        seen_names = set()
        for ch in chapters:
            if ch["filename"] in seen_names:
                self.log(
                    "  warning: duplicate chapter filename"
                    f" {ch['filename']} — chapters may be lost"
                )
            seen_names.add(ch["filename"])

        images = []  # full download URLs
        fonts = []
        asset_failures = 0
        self.log("Downloading chapters...")
        total = len(chapters)
        for i, ch in enumerate(chapters):
            self.progress(i + 1, total, ch["title"])
            out_name = ch["filename"].replace(".html", ".xhtml")

            for img_url in ch["images"]:
                if img_url.startswith("http"):
                    images.append(img_url)
                else:
                    images.append(urljoin(api.files_url + "/", img_url))
            for font_url in ch.get("fonts", []):
                if font_url.startswith("http"):
                    fonts.append(font_url)
                else:
                    fonts.append(urljoin(api.files_url + "/", font_url))

            if builder.has_chapter(out_name):
                continue

            chapter_css = [s["url"] for s in ch["stylesheets"]] + ch["site_styles"]
            # Cache raw HTML so re-transforming (after transform changes or
            # deleted .xhtml) doesn't hit the API again.
            cache_file = os.path.join(work_dir, ".cache", ch["filename"])
            if os.path.isfile(cache_file):
                with open(cache_file, encoding="utf-8") as f:
                    raw = f.read()
            else:
                raw = api.get_chapter_html(ch)
                os.makedirs(os.path.dirname(cache_file), exist_ok=True)
                with open(cache_file, "w", encoding="utf-8") as f:
                    f.write(raw)
            try:
                root = html.fromstring(raw, base_url=C.SAFARI_BASE_URL)
            except (html.etree.ParseError, html.etree.ParserError) as exc:
                raise ApiError(
                    "Could not parse chapter {!r}".format(ch["title"])
                ) from exc
            page_css, xhtml = tx.parse(root, chapter_css, first_page=(i == 0))
            builder.write_chapter(
                out_name, tx.render_page(page_css, xhtml, title=ch["title"])
            )

        # On resume the first page is skipped before tx.parse, so recover the
        # cover image from the previously written chapter file.
        if not tx.cover:
            first_file = builder.chapter_path(
                chapters[0]["filename"].replace(".html", ".xhtml")
            )
            if os.path.isfile(first_file):
                with open(first_file, encoding="utf-8") as f:
                    m = re.search(r'src="(Images/[^"]*cover[^"]*)"', f.read())
                    if m:
                        tx.cover = m.group(1)

        # Fallback cover: use metadata cover URL when no cover page was detected
        if not tx.cover and info.get("cover"):
            content, ctype = api.get_binary(info["cover"])
            ext = ctype.split("/")[-1].split(";")[0].replace("jpeg", "jpg") or "jpg"
            name = "default_cover." + ext
            builder.write_image(name, content)
            fake = html.fromstring(
                f'<div id="sbo-rt-content"><img src="Images/{name}"/></div>'
            )
            page_css, xhtml = tx.parse(fake, first_page=True)
            builder.write_chapter(
                "default_cover.xhtml",
                tx.render_page(page_css, xhtml, title="Cover"),
            )
            chapters = [
                {"filename": "default_cover.xhtml", "title": "Cover"}
            ] + chapters

        # related_assets can miss package files (fonts, extra images);
        # the files/ endpoint is the canonical list — merge both.
        try:
            for f in api.get_files():
                ext = f.get("filename_ext", "").lstrip(".")
                media_type = f.get("media_type", "")
                if (
                    f.get("kind") == "image" or media_type.startswith("image/")
                ) and f.get("url"):
                    images.append(f["url"])
                elif (ext in FONT_EXTENSIONS or "font" in media_type) and f.get("url"):
                    fonts.append(f["url"])
        except (ApiError, AuthError) as exc:
            self.log(f"  warning: could not list package files: {exc}")

        # Warn on basename collisions — chapter markup maps assets by basename,
        # so two distinct files named the same would clobber each other.
        for urls in (images, fonts):
            seen = {}
            for u in urls:
                b = _basename(u)
                if b in seen and seen[b] != u:
                    self.log(f"  warning: asset name collision: {u} vs {seen[b]}")
                seen[b] = u

        image_names = {_basename(u) for u in images}
        font_names = {_basename(u) for u in fonts}
        self.log(f"Downloading stylesheets ({len(tx.css)})...")
        for i, css_url in enumerate(tx.css):
            self.progress(i + 1, len(tx.css), "css")
            target = os.path.join(builder.css_path, f"Style{i:0>2}.css")
            if os.path.isfile(target):
                continue
            try:
                content, _ = api.get_binary(css_url)
                builder.write_css(i, rewrite_css_urls(content, image_names, font_names))
            except (ApiError, OSError) as exc:
                asset_failures += 1
                self.log(f"  warning: CSS {css_url} failed: {exc}")

        images = list(dict.fromkeys(images))
        self.log(f"Downloading images ({len(images)})...")
        for i, url in enumerate(images):
            self.progress(i + 1, len(images), "images")
            if os.path.isfile(os.path.join(builder.images_path, _basename(url))):
                continue
            try:
                content, _ = api.get_binary(url)
                builder.write_image(_basename(url), content)
            except (ApiError, OSError) as exc:
                asset_failures += 1
                self.log(f"  warning: image {url} failed: {exc}")

        fonts = list(dict.fromkeys(fonts))
        for i, url in enumerate(fonts):
            self.progress(i + 1, len(fonts), "fonts")
            if os.path.isfile(os.path.join(builder.fonts_path, _basename(url))):
                continue
            try:
                content, _ = api.get_binary(url)
                builder.write_font(_basename(url), content)
            except (ApiError, OSError) as exc:
                asset_failures += 1
                self.log(f"  warning: font {url} failed: {exc}")

        # Wire downloaded fonts into the shared stylesheet — book CSS often
        # names embedded fonts (e.g. "Ubuntu Mono") without @font-face.
        css_text = tx.base_css
        for css_name in os.listdir(builder.css_path):
            with open(
                os.path.join(builder.css_path, css_name),
                encoding="utf-8",
                errors="replace",
            ) as f:
                css_text += f.read()
        builder.write_named_css(
            "BookScraper.css",
            tx.base_css + _font_faces(builder.fonts_path, css_text),
        )

        if asset_failures:
            self.log(
                f"  warning: {asset_failures} assets failed to download"
                " — re-run to retry (session may have expired)"
            )

        self.log("Building EPUB...")
        toc = api.get_toc()
        epub_path = os.path.join(
            self.output_dir, "{}.epub".format(escape_dirname(info["title"]))
        )
        builder.finalize(chapters, toc, tx.cover, epub_path)
        self.log(f"Done: {epub_path}")

        if self.validate:
            self.log("Validating EPUB...")
            epubcheck = shutil.which("epubcheck")
            if not epubcheck:
                self.log(
                    "  epubcheck not installed — skipping (brew install epubcheck)"
                )
            else:
                proc = subprocess.run(
                    [epubcheck, epub_path],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=600,
                )
                lines = proc.stdout.splitlines()
                problems = [
                    line
                    for line in lines
                    if line.startswith(("FATAL", "ERROR", "WARNING"))
                ]
                for line in problems[:15]:
                    self.log(f"  {line}")
                if len(problems) > 15:
                    self.log(f"  ... and {len(problems) - 15} more")
                summary = next(
                    (
                        line
                        for line in reversed(lines)
                        if line.startswith(("Messages:", "No errors"))
                    ),
                    "",
                )
                self.log(f"  {summary or 'epubcheck finished'}")

        if self.pdf:
            self.log("Building PDF...")
            pdf_path = epub_path[:-5] + ".pdf"
            build_pdf(builder.oebps, chapters, info["title"], pdf_path)
            self.log(f"Done: {pdf_path}")

        if self.web:
            self.log("Building web version...")
            web_dir = build_web(
                builder.oebps,
                chapters,
                toc,
                info,
                os.path.join(work_dir, "web"),
                cover_src=tx.cover,
            )
            self.log(f"Done: {os.path.join(web_dir, 'index.html')}")
        return epub_path
