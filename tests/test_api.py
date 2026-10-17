"""Tests for api.py normalization and OPF metadata parsing."""

from shelf import constants as C
from shelf.api import OreillyAPI
from shelf.downloader import extract_book_id

BOOK_ID = "9798341607675"
OPF_XML = b"""<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier>urn:isbn:9798341607682</dc:identifier>
<dc:title>Site Reliability Engineering</dc:title>
<dc:creator>Betsy Beyer, Chris Jones, Christof Leng, David Huska, \
Jennifer Petoff, and Niall Richard Murphy</dc:creator>
<dc:publisher>O'Reilly Media, Inc.</dc:publisher>
<dc:date>2026-09-16</dc:date>
<dc:description>Desc.</dc:description>
</metadata>
<manifest>
<item id="cover-img" href="assets/cover.png" properties="cover-image"/>
</manifest></package>"""


class FakeResp:
    def __init__(self, json_data=None, content=b"", status=200):
        self._j = json_data
        self.content = content
        self.status_code = status

    def json(self):
        return self._j


class FakeHTTP:
    def __init__(self, routes):
        self.routes = routes

    def request(self, url, **kwargs):
        for prefix in sorted(self.routes, key=len, reverse=True):
            if url.startswith(prefix):
                return self.routes[prefix]
        return FakeResp(status=404)


def make_api(routes):
    return OreillyAPI(FakeHTTP(routes), BOOK_ID)


class TestExtractBookId:
    def test_library_url(self):
        assert (
            extract_book_id(
                "https://learning.oreilly.com/library/view/-/9798341607675/"
            )
            == "9798341607675"
        )

    def test_bare_id(self):
        assert extract_book_id("9798341607675") == "9798341607675"

    def test_junk_rejected(self):
        for bad in ["", "hello", "https://example.com/", "a/b/c"]:
            try:
                extract_book_id(bad)
            except ValueError:
                pass
            else:
                raise AssertionError(f"accepted {bad!r}")


class TestNormalizeToc:
    def test_fields_and_children(self):
        api = make_api({})
        out = api._normalize_toc(
            [
                {
                    "ourn": "urn:orm:book:X:chapter:ch01.html",
                    "title": "Ch 1",
                    "depth": 1,
                    "fragment": "ch01_sec",
                    "children": [
                        {
                            "ourn": "urn:orm:book:X:chapter:ch02.html",
                            "title": "Sub",
                            "depth": 2,
                            "children": [],
                        }
                    ],
                }
            ]
        )
        assert out[0]["href"] == "ch01.html"
        assert out[0]["fragment"] == "ch01_sec"
        assert out[0]["label"] == "Ch 1"
        assert out[0]["children"][0]["href"] == "ch02.html"


class TestOpfMetadata:
    def test_authors_publisher_cover(self):
        api_url = C.EPUB_API.format(BOOK_ID)
        files_json = {
            "results": [{"full_path": "OEBPS/content.opf"}],
            "next": None,
        }
        api = make_api(
            {
                api_url + "files/": FakeResp(json_data=files_json),
                api_url + "files/OEBPS/content.opf": FakeResp(content=OPF_XML),
            }
        )
        meta = api.get_opf_metadata()
        assert meta["authors"] == [
            "Betsy Beyer",
            "Chris Jones",
            "Christof Leng",
            "David Huska",
            "Jennifer Petoff",
            "Niall Richard Murphy",
        ]
        assert meta["publishers"] == ["O'Reilly Media, Inc."]
        assert meta["issued"] == "2026-09-16"
        assert meta["isbn"] == "9798341607682"
        assert meta["cover"].endswith("files/assets/cover.png")

    def test_missing_opf_returns_empty(self):
        api_url = C.EPUB_API.format(BOOK_ID)
        api = make_api(
            {api_url + "files/": FakeResp(json_data={"results": [], "next": None})}
        )
        assert api.get_opf_metadata() == {}
