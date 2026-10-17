"""O'Reilly v2 API: book metadata, chapter list, TOC, asset downloads."""

import re
from urllib.parse import urljoin

from lxml import html

from . import constants as C
from .session import AuthError


class ApiError(Exception):
    pass


OPF_NS = {
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
}

FONT_EXTENSIONS = {"otf", "ttf", "woff", "woff2", "ttc", "otc", "sfnt"}


def _names(values):
    """Normalize a metadata list of strings or {name: ...} dicts."""
    out = []
    for v in values or []:
        if isinstance(v, dict):
            out.append(v.get("name") or v.get("full_name") or "")
        else:
            out.append(str(v))
    return [n for n in out if n]


class OreillyAPI:
    def __init__(self, oreilly_session, book_id):
        self.http = oreilly_session
        self.book_id = book_id
        self.api_url = C.EPUB_API.format(book_id)
        self.files_url = C.EPUB_FILES_API.format(book_id)
        self._files = None

    def _get_json(self, url):
        response = self.http.request(url, retry_403=True)
        if response.status_code == 403:
            raise AuthError(
                "Access denied — session expired or not entitled to this book."
            )
        if response.status_code != 200:
            raise ApiError(f"API error {response.status_code} for {url}")
        try:
            return response.json()
        except ValueError as exc:
            raise ApiError(f"API returned non-JSON for {url}") from exc

    # -- metadata ------------------------------------------------------------

    def get_files(self):
        """Every file in the epub package, from the files/ endpoint (cached)."""
        if self._files is not None:
            return self._files
        files = []
        next_url = urljoin(self.api_url, "files/")
        while next_url:
            data = self._get_json(next_url)
            if not isinstance(data, dict) or "results" not in data:
                raise ApiError(f"Unexpected file listing: {(data,)[:300]!r}")
            files.extend(data["results"])
            next_url = data.get("next")
        self._files = files
        return files

    def file_url(self, full_path):
        return urljoin(self.api_url, "files/" + full_path)

    def get_opf_metadata(self):
        """Authoritative metadata from the package's content.opf (best effort)."""
        try:
            files = self.get_files()
        except (ApiError, AuthError):
            return {}
        opf_path = next(
            (f["full_path"] for f in files if f["full_path"].endswith(".opf")),
            None,
        )
        if not opf_path:
            return {}
        response = self.http.request(self.file_url(opf_path))
        if response.status_code != 200:
            return {}
        try:
            root = html.etree.fromstring(response.content)
        except (html.etree.ParseError, html.etree.ParserError):
            return {}

        def texts(tag):
            return [
                e.text.strip()
                for e in root.findall(f".//dc:{tag}", OPF_NS)
                if e.text and e.text.strip()
            ]

        # dc:creator may be one element per author, or a single
        # "A. One, B. Two, and C. Three" string.
        creators = []
        for c in texts("creator"):
            creators.extend(
                n
                for n in (p.strip() for p in re.split(r",\s+and\s+|,\s+|\s+and\s+", c))
                if n
            )

        cover = ""
        items = root.findall(".//opf:manifest/opf:item", OPF_NS)
        item = next(
            (i for i in items if "cover-image" in (i.get("properties") or "")),
            None,
        )
        if item is None:
            meta = root.find('.//opf:metadata/opf:meta[@name="cover"]', OPF_NS)
            if meta is not None:
                item = next(
                    (i for i in items if i.get("id") == meta.get("content")),
                    None,
                )
        if item is not None and item.get("href"):
            cover = self.file_url(item.get("href"))

        def first(tag):
            values = texts(tag)
            return values[0] if values else ""

        modified = next(
            (
                e.text.strip()
                for e in root.findall(".//opf:meta", OPF_NS)
                if e.get("property") == "dcterms:modified" and e.text and e.text.strip()
            ),
            "",
        )

        return {
            "authors": creators,
            "modified": modified,
            "publishers": texts("publisher"),
            "subjects": texts("subject"),
            "issued": first("date"),
            "description": first("description"),
            "rights": first("rights"),
            "isbn": first("identifier").replace("urn:isbn:", "").replace("-", ""),
            "cover": cover,
        }

    def get_book_info(self):
        data = self._get_json(self.api_url)
        if not isinstance(data, dict) or "title" not in data:
            raise ApiError(f"Unexpected book metadata: {(data,)[:300]!r}")

        descriptions = data.get("descriptions") or {}
        description = (
            descriptions.get("text/html") or descriptions.get("text/plain") or ""
        )

        authors = _names(
            data.get("authors") or data.get("creators") or data.get("contributors")
        )
        subjects = _names(
            data.get("subjects") or data.get("tags") or data.get("topics")
        )
        publishers = _names(data.get("publishers"))

        # The v2 metadata has no authors/publisher — those live only in the
        # package's content.opf. OPF values win where both exist.
        opf = self.get_opf_metadata()

        result = {
            "title": data.get("title", ""),
            "authors": opf.get("authors") or authors,
            "identifier": data.get("identifier", ""),
            "isbn": opf.get("isbn") or data.get("isbn", self.book_id),
            "publishers": opf.get("publishers") or publishers,
            "rights": opf.get("rights") or data.get("rights", ""),
            "description": description or opf.get("description"),
            "issued": data.get("publication_date", "") or opf.get("issued"),
            "modified": opf.get("modified", ""),
            "web_url": C.SAFARI_BASE_URL + f"/library/view/-/{self.book_id}/",
            "subjects": subjects or opf.get("subjects"),
            "cover": data.get("cover")
            or data.get("cover_url")
            or data.get("cover_image")
            or opf.get("cover"),
        }
        return {k: (v if v is not None else "") for k, v in result.items()}

    # -- chapters --------------------------------------------------------------

    def _normalize_chapter(self, c):
        ourn = c.get("ourn", "")
        filename = ourn.split("chapter:")[-1] if "chapter:" in ourn else ""
        if not filename:
            filename = (c.get("title") or "chapter").strip().replace(" ", "_") + ".html"

        assets = c.get("related_assets") or {}
        return {
            "filename": filename.split("/")[-1],
            "title": c.get("title", ""),
            "content": c.get("content_url", ""),
            "asset_base_url": self.files_url,
            "images": assets.get("images", []),
            "fonts": assets.get("fonts", []),
            "stylesheets": [{"url": u} for u in assets.get("stylesheets", [])],
            "site_styles": [],
        }

    def get_book_chapters(self):
        chapters = []
        next_url = C.CHAPTERS_API.format(self.book_id)
        while next_url:
            data = self._get_json(next_url)
            if not isinstance(data, dict) or "results" not in data:
                raise ApiError(f"Unexpected chapter listing: {(data,)[:300]!r}")
            chapters.extend(self._normalize_chapter(c) for c in data["results"])
            next_url = data.get("next")

        if not chapters:
            raise ApiError("Book has no chapters.")

        covers = [
            c
            for c in chapters
            if "cover" in c["filename"].lower() or "cover" in c["title"].lower()
        ]
        rest = [c for c in chapters if c not in covers]
        return covers + rest

    # -- table of contents ------------------------------------------------------

    def _normalize_toc(self, items):
        result = []
        for item in items:
            ourn = item.get("ourn", "")
            filename = ourn.split("chapter:")[-1] if "chapter:" in ourn else ""
            fragment = item.get("fragment", "")
            result.append(
                {
                    "depth": item.get("depth", 1),
                    "fragment": fragment,
                    "id": filename or fragment,
                    "label": item.get("title", ""),
                    "href": filename.split("/")[-1],
                    "children": self._normalize_toc(item.get("children", [])),
                }
            )
        return result

    def get_toc(self):
        data = self._get_json(urljoin(self.api_url, "table-of-contents/"))
        if not isinstance(data, list):
            raise ApiError(f"Unexpected TOC payload: {(data,)[:300]!r}")
        return self._normalize_toc(data)

    # -- content & assets ---------------------------------------------------------

    def get_chapter_html(self, chapter):
        url = chapter["content"]
        if not url:
            raise ApiError("Chapter {!r} has no content URL".format(chapter["title"]))
        response = self.http.request(urljoin(C.SAFARI_BASE_URL, url), retry_403=True)
        if response.status_code != 200:
            raise ApiError(
                "HTTP {} fetching chapter {!r}".format(
                    response.status_code, chapter["title"]
                )
            )
        return response.text

    def get_chapter_root(self, chapter):
        try:
            return html.fromstring(
                self.get_chapter_html(chapter), base_url=C.SAFARI_BASE_URL
            )
        except (html.etree.ParseError, html.etree.ParserError) as exc:
            raise ApiError(
                "Could not parse chapter {!r}".format(chapter["title"])
            ) from exc

    def get_binary(self, url):
        response = self.http.request(urljoin(C.SAFARI_BASE_URL, url), retry_403=True)
        if response.status_code != 200:
            raise ApiError(f"HTTP {response.status_code} fetching {url}")
        return response.content, response.headers.get("Content-Type", "")
