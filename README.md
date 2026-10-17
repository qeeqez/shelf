<img src="assets/icon.svg" width="64" height="64" alt="">

# book-scraper

Download O'Reilly books you have access to as EPUB files. Point it at a
`learning.oreilly.com` book URL, authenticate once, and it produces a complete
EPUB (chapters, images, stylesheets, table of contents).

Uses the O'Reilly **v2 API** (`/api/v2/epubs/`, `/api/v2/epub-chapters/`).

## Install

Requires [uv](https://docs.astral.sh/uv/) and macOS. Python 3.15 is pinned
via `.python-version`.

```bash
uv sync
```

## Usage

```bash
uv run book-scraper "https://learning.oreilly.com/library/view/book-title/9781098125974/"
# or a bare book ID
uv run book-scraper 9781098125974
```

On first run it asks how you want to sign in. A verified session is saved to
`~/Library/Application Support/book-scraper/cookies.json` and reused on later
runs (it auto re-auths when expired).

### Authentication options

| Flag | How it works |
|------|--------------|
| *(none)* | Interactive menu on first run |
| `--browser [name]` | Reads `learning.oreilly.com` cookies straight from an installed browser (chrome, firefox, edge, arc, brave, vivaldi, chromium, opera). Handles SSO/2FA for free — just log in normally first. Chromium reads trigger a one-time Keychain access prompt; Safari isn't supported (paste cookies instead). |
| `--import-cookies FILE` | Imports cookies you exported: JSON dict or a raw `document.cookie` string. |
| `--login` / `--cred EMAIL:PASS` | Programmatic password login. May fail if O'Reilly demands ReCaptcha or your account uses SSO. |

To export cookies manually: log in at learning.oreilly.com, open DevTools
console, run:

```js
console.log(JSON.stringify(document.cookie.split(';').map(c => c.split('=')).map(i => [i[0].trim(), i[1].trim()]).reduce((r, i) => {r[i[0]] = i[1]; return r;}, {})))
```

and save the output to a file, then `--import-cookies cookies.json`.

### Other flags

- `-o DIR` — output directory (default `./Books`)
- `--pdf` — also produce `<Book Title>.pdf` next to the EPUB
  (via [WeasyPrint](https://weasyprint.org); requires system Pango —
  `brew install pango` on macOS)
- `--web` — also produce a browsable static site at
  `Books/<Book Title> (<id>)/web/index.html` (sre.google-style layout:
  collapsible sidebar TOC, prev/next pager, `←`/`→` keyboard nav)
- `--kindle` — extra CSS to prevent `table`/`pre` overflow on e-readers
- `--session FILE` — session store location
- `--no-save` — don't persist the session

## Output

`Books/<Book Title>.epub` (and `.pdf` with `--pdf`) plus a
`Books/<Book Title> (<id>)/` working
directory with the unpacked content. Re-running after an interruption resumes
where it left off — delete the working directory to force a clean download.

## Notes

- Only downloads books your account is entitled to; it checks authentication
  and subscription status first.
- Downloading content you have legitimate access to for personal use is the
  intent. Respect O'Reilly's Terms of Service — no redistribution.
