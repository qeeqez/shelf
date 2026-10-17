"""Tests for session.py cookie handling and request retry."""

import json

import httpx

from book_scraper.session import OreillySession


class TestCookieSave:
    def test_duplicate_names_across_domains_do_not_crash(self, tmp_path):
        f = str(tmp_path / "cookies.json")
        s = OreillySession(f)
        # _abck-style duplicate names on different domains raised
        # httpx.CookieConflict with dict(cookies) — jar iteration must not.
        s.client.cookies.set("tok", "a", domain="a.example.com")
        s.client.cookies.set("tok", "b", domain="b.example.com")
        s.save_cookies()
        with open(f) as fh:
            saved = json.loads(fh.read())
        assert saved["tok"] in ("a", "b")

    def test_roundtrip(self, tmp_path):
        f = str(tmp_path / "cookies.json")
        s = OreillySession(f)
        s.client.cookies.set("a", "1")
        s.client.cookies.set("b", "2")
        s.save_cookies()
        s2 = OreillySession(f)
        assert s2.load_cookies()
        assert s2.client.cookies.get("a") == "1"


class TestImportCookies:
    def test_header_string(self, tmp_path):
        s = OreillySession(str(tmp_path / "c.json"))
        s.import_cookies("a=1; b=two")
        assert s.client.cookies.get("a") == "1"
        assert s.client.cookies.get("b") == "two"

    def test_dict(self, tmp_path):
        s = OreillySession(str(tmp_path / "c.json"))
        s.import_cookies({"x": "y"})
        assert s.client.cookies.get("x") == "y"


class TestRequestRetry:
    def _session(self, tmp_path, statuses):
        s = OreillySession(str(tmp_path / "c.json"))
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(statuses[min(calls["n"] - 1, len(statuses) - 1)])

        s.client = httpx.Client(transport=httpx.MockTransport(handler))
        s.MIN_INTERVAL = 0  # don't slow the test down
        return s, calls

    def test_403_retried_when_asked(self, tmp_path):
        s, calls = self._session(tmp_path, [403, 200])
        r = s.request("https://x/", retry_403=True)
        assert r.status_code == 200 and calls["n"] == 2

    def test_403_not_retried_by_default(self, tmp_path):
        s, calls = self._session(tmp_path, [403, 200])
        r = s.request("https://x/")
        assert r.status_code == 403 and calls["n"] == 1

    def test_5xx_retried_then_success(self, tmp_path):
        s, calls = self._session(tmp_path, [503, 502, 200])
        r = s.request("https://x/")
        assert r.status_code == 200 and calls["n"] == 3

    def test_gives_up_after_retries(self, tmp_path):
        s, calls = self._session(tmp_path, [500] * 5)
        r = s.request("https://x/")
        assert r.status_code == 500 and calls["n"] == 3
