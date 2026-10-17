"""O'Reilly v2 API: book metadata, chapter list, TOC, asset downloads."""

from urllib.parse import urljoin

from lxml import html

from . import constants as C
from .session import AuthError


class ApiError(Exception):
    pass


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

    def _get_json(self, url):
        response = self.http.request(url)
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

        result = {
            "title": data.get("title", ""),
            "authors": authors,
            "identifier": data.get("identifier", ""),
            "isbn": data.get("isbn", self.book_id),
            "publishers": publishers,
            "rights": data.get("rights", ""),
            "description": description,
            "issued": data.get("publication_date", ""),
            "web_url": C.SAFARI_BASE_URL + f"/library/view/-/{self.book_id}/",
            "subjects": subjects,
            "cover": data.get("cover")
            or data.get("cover_url")
            or data.get("cover_image"),
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

    def get_chapter_root(self, chapter):
        url = chapter["content"]
        if not url:
            raise ApiError("Chapter {!r} has no content URL".format(chapter["title"]))
        response = self.http.request(urljoin(C.SAFARI_BASE_URL, url))
        if response.status_code != 200:
            raise ApiError(
                "HTTP {} fetching chapter {!r}".format(
                    response.status_code, chapter["title"]
                )
            )
        try:
            return html.fromstring(response.text, base_url=C.SAFARI_BASE_URL)
        except (html.etree.ParseError, html.etree.ParserError) as exc:
            raise ApiError(
                "Could not parse chapter {!r}".format(chapter["title"])
            ) from exc

    def get_binary(self, url):
        response = self.http.request(urljoin(C.SAFARI_BASE_URL, url))
        if response.status_code != 200:
            raise ApiError(f"HTTP {response.status_code} fetching {url}")
        return response.content, response.headers.get("Content-Type", "")
