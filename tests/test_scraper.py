"""Tests for downloader.py helpers: basenames, css urls, font faces."""

from shelf.downloader import (
    _basename,
    _font_faces,
    _norm,
    escape_dirname,
    rewrite_css_urls,
)


class TestBasename:
    def test_strips_query_and_fragment(self):
        assert _basename("https://x/a/b.png?w=1#f") == "b.png"
        assert _basename("a/b.png") == "b.png"


class TestEscapeDirname:
    def test_special_chars(self):
        # Colon beyond pos 15 splits the subtitle; earlier colons sanitize.
        assert escape_dirname('Title: A "Book"?') == "Title A Book"
        assert escape_dirname("A very long title: subtitle") == "A very long title"
        assert escape_dirname("SRE, 2nd Edition") == "SRE, 2nd Edition"


class TestRewriteCssUrls:
    def test_relative_to_dirs(self):
        css = b'a{background:url("images/x.png")}b{src:url(../fonts/f.otf)}'
        out = rewrite_css_urls(css, {"x.png"}, {"f.otf"}).decode()
        assert 'url("../Images/x.png")' in out
        assert "url(../Fonts/f.otf)" in out

    def test_absolute_and_data_untouched(self):
        css = b'a{background:url("https://x/y.png");b:url(data:image/png,i)}'
        out = rewrite_css_urls(css, {"y.png"}, set()).decode()
        assert "https://x/y.png" in out
        assert "data:image/png" in out

    def test_unknown_relative_untouched(self):
        css = b'a{src:url("other/z.bin")}'
        out = rewrite_css_urls(css, set(), set()).decode()
        assert 'url("other/z.bin")' in out


class TestFontFaces:
    def test_corrupt_font_falls_back_to_stem(self, tmp_path):
        fonts = tmp_path / "Fonts"
        fonts.mkdir()
        (fonts / "UbuntuMono-Bold.otf").write_bytes(b"not-a-font")
        rules = _font_faces(str(fonts), "")
        assert 'font-family:"UbuntuMono-Bold"' in rules
        assert 'src:url("../Fonts/UbuntuMono-Bold.otf")' in rules

    def test_aliases_for_css_names(self, tmp_path, monkeypatch):
        fonts = tmp_path / "Fonts"
        fonts.mkdir()
        (fonts / "UbuntuMono-Italic.otf").write_bytes(b"fake")

        class FakeName:
            def getDebugName(self, n):
                return {
                    1: "Ubuntu Mono",
                    2: "Italic",
                    4: "Ubuntu Mono Italic",
                }.get(n)

        class FakeOS2:
            usWeightClass = 400
            fsSelection = 0x01

        class FakeTT:
            def __init__(self, *a, **k):
                pass

            def __getitem__(self, key):
                return {"name": FakeName(), "OS/2": FakeOS2()}[key]

        import fontTools.ttLib

        monkeypatch.setattr(fontTools.ttLib, "TTFont", FakeTT)
        css = 'pre{font-family:"Ubuntu Mono Ital",monospace}'
        rules = _font_faces(str(fonts), css)
        assert 'font-family:"Ubuntu Mono"' in rules
        assert 'font-family:"Ubuntu Mono Ital"' in rules  # css alias
        assert "font-style:italic" in rules


def test_norm():
    assert _norm("Ubuntu Mono Ital") == "ubuntumonoital"
    assert _norm(" DejaVuSans ") == "dejavusans"
