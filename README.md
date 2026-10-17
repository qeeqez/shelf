<img src="assets/icon.svg" width="64" height="64" alt="">

# shelf

Download O'Reilly books you have access to for offline reading. Give it a
`learning.oreilly.com` book URL (or bare book ID), authenticate once, and it
produces a complete **EPUB 3** — plus optional **PDF** and a self-contained
**static web reader**.

## What it does

- Authenticates against your O'Reilly account (browser cookies, saved session,
  manual cookie import, or email/password).
- Downloads every chapter, image, stylesheet, and font via the O'Reilly
  **v2 API** (`/api/v2/epubs/`, `/api/v2/epub-chapters/`).
- Rebuilds clean EPUB 3 output: XHTML content, rewritten links/assets,
  authors/subjects/publisher pulled from the book's own `content.opf`, NCX +
  nav TOC, landmarks, and schema.org accessibility metadata — `epubcheck`
  clean.
- Optionally emits a PDF (WeasyPrint) and a static web version
  (`--web`) styled after the Google SRE book site.

## Install

Requires Python 3.12+. [uv](https://docs.astral.sh/uv/) is the recommended
setup (Python 3.15 is pinned via `.python-version`), but plain pip works too:

```bash
uv sync
# or
pip install .
```

Runs on macOS, Linux, and Windows — one exception: `--browser` cookie
harvesting for Chromium-family browsers is macOS-only (it decrypts via the
login keychain). Firefox cookie reading, `--import-cookies`, and `--login`
work everywhere.

## Usage

```bash
uv run shelf "https://learning.oreilly.com/library/view/book-title/9781098125974/"
# or a bare book ID
uv run shelf 9781098125974
```

On first run it asks how you want to sign in. A verified session is saved to
the platform config dir (e.g. `~/Library/Application Support/shelf/cookies.json`
on macOS, written `0600`) and reused on later runs, auto re-authing when it
expires.

### Authentication options

| Flag | How it works |
|------|--------------|
| *(none)* | Interactive menu on first run |
| `--browser [name]` | Reads `learning.oreilly.com` cookies straight from an installed browser (chrome, firefox, edge, arc, brave, vivaldi, chromium, opera). Handles SSO/2FA for free — just log in normally first. Chromium-family reads are macOS-only and trigger a one-time Keychain access prompt; Firefox works on macOS/Linux/Windows; Safari isn't supported (paste cookies instead). |
| `--import-cookies FILE` | Imports cookies you exported: JSON dict or a raw `document.cookie` string. |
| `--login` / `--cred EMAIL:PASS` | Programmatic password login. May fail if O'Reilly demands ReCaptcha or your account uses SSO. |

To export cookies manually: log in at learning.oreilly.com, open DevTools
console, run:

```js
console.log(JSON.stringify(document.cookie.split(';').map(c => c.split('=')).map(i => [i[0].trim(), i[1].trim()]).reduce((r, i) => {r[i[0]] = i[1]; return r;}, {})))
```

and save the output to a file, then `--import-cookies cookies.json`.

### Output flags

- `-o DIR` — output directory (default `./Books`)
- `--web` — also produce a browsable static site at
  `Books/<Book Title> (<id>)/web/index.html`
- `--pdf` — also produce `<Book Title>.pdf` next to the EPUB
  (via [WeasyPrint](https://weasyprint.org); requires system Pango —
  `brew install pango` / `apt install libpango-1.0-0`)
- `--kindle` — extra CSS to prevent `table`/`pre` overflow on e-readers
- `--validate` — run `epubcheck` on the EPUB after building, when installed
  (`brew install epubcheck` — requires Java — or the epubcheck jar from your
  distro). Expect `0 fatals / 0 errors / 0 warnings / 0 infos`.
- `--force` — delete the working directory and re-download everything
- `--jobs N` — parallel downloads (default 4); a global request-rate cap
  still applies, so higher `N` won't hammer the API
- `--session FILE` — session store location
- `--no-save` — don't persist the session

## The web reader

`--web` generates a fully static site — no server needed, works straight off
the filesystem:

- Collapsible sidebar TOC with the current chapter highlighted and a
  scroll-spy marker that tracks the section you're reading; sidebar scroll
  position survives page switches.
- Instant client-side search (build-time index), keyboard navigable
  (`/` to focus, arrows, Enter, Escape).
- `system / light / dark` theme toggle — dark mode inverts book content
  colors so images and code blocks stay readable.
- Full-width content toggle, heading anchor links (hover `#`, click copies
  the URL), prev/next pager, `←`/`→` chapter keys.
- Mobile-ready: drawer sidebar with scrim, safe-area insets, 44px touch
  targets, no iOS zoom on search.
- Print stylesheet — browser "Print to PDF" produces a clean book layout.
- Honors `prefers-reduced-motion`; usable without JavaScript.

## Output layout

```
Books/<Book Title>.epub                # the EPUB
Books/<Book Title>.pdf                 # with --pdf
Books/<Book Title> (<id>)/
  OEBPS/                               # unpacked EPUB content
  web/                                 # the static site, with --web
  .cache/                              # raw chapter HTML (offline re-transforms)
  meta.json                            # download manifest — enables offline rebuilds
```

Re-running after an interruption resumes where it left off — pass `--force`
to wipe the working directory and download fresh. Raw chapter HTML stays in
`.cache/`, so iterating on `transform.py` or the web output doesn't hit the
API again. A completed download also saves `meta.json` (chapter list, TOC,
asset URLs) — once everything's on disk, re-runs skip authentication and the
API entirely; `--force` refreshes from scratch.

## Development

```console
uv run pytest tests/   # unit tests
uv run ruff check .    # lint
uv run ruff format .   # format
```

## Notes

- Only downloads books your account is entitled to; it checks authentication
  and subscription status first.
- Downloading content you have legitimate access to for personal use is the
  intent. Respect O'Reilly's Terms of Service — no redistribution.
