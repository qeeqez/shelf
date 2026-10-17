"""Orchestrates downloading a book: chapters, assets, EPUB assembly."""

import os
import re
from urllib.parse import urljoin

from lxml import html

from . import constants as C
from .api import ApiError, OreillyAPI
from .epub import EpubBuilder
from .transform import Transformer


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
    return " ".join(dirname.split())


class BookScraper:
    def __init__(
        self, oreilly_session, output_dir, kindle=False, log=print, progress=None
    ):
        self.http = oreilly_session
        self.output_dir = output_dir
        self.kindle = kindle
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
        builder = EpubBuilder(info, book_id, work_dir)
        tx = Transformer(book_id, info["web_url"], kindle=self.kindle)

        images = []  # full download URLs
        self.log("Downloading chapters...")
        total = len(chapters)
        for i, ch in enumerate(chapters):
            self.progress(i + 1, total, ch["title"])
            out_name = ch["filename"].replace(".html", ".xhtml")
            if builder.has_chapter(out_name):
                continue

            for img_url in ch["images"]:
                if img_url.startswith("http"):
                    images.append(img_url)
                else:
                    images.append(urljoin(api.files_url + "/", img_url))

            chapter_css = [s["url"] for s in ch["stylesheets"]] + ch["site_styles"]
            root = api.get_chapter_root(ch)
            page_css, xhtml = tx.parse(root, chapter_css, first_page=(i == 0))
            builder.write_chapter(out_name, tx.render_page(page_css, xhtml))

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
                "default_cover.xhtml", tx.render_page(page_css, xhtml)
            )
            chapters = [
                {"filename": "default_cover.xhtml", "title": "Cover"}
            ] + chapters

        self.log(f"Downloading stylesheets ({len(tx.css)})...")
        for i, css_url in enumerate(tx.css):
            self.progress(i + 1, len(tx.css), "css")
            try:
                content, _ = api.get_binary(css_url)
                builder.write_css(i, content)
            except (ApiError, OSError) as exc:
                self.log(f"  warning: CSS {css_url} failed: {exc}")

        images = list(dict.fromkeys(images))
        self.log(f"Downloading images ({len(images)})...")
        for i, url in enumerate(images):
            self.progress(i + 1, len(images), "images")
            name = url.split("/")[-1].split("?")[0]
            try:
                content, _ = api.get_binary(url)
                builder.write_image(name, content)
            except (ApiError, OSError) as exc:
                self.log(f"  warning: image {url} failed: {exc}")

        self.log("Building EPUB...")
        toc = api.get_toc()
        epub_path = os.path.join(
            self.output_dir, "{}.epub".format(escape_dirname(info["title"]))
        )
        builder.finalize(chapters, toc, tx.cover, epub_path)
        self.log(f"Done: {epub_path}")
        return epub_path
