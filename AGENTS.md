# Agent notes

## Commands

- `uv run shelf <URL_OR_ID>` — run the CLI (flags: `--web --pdf --kindle --validate --force --jobs N`)
- `uv run pytest tests/` — unit tests
- `uv run ruff check .` / `uv run ruff format .` — lint / format
- `node --check "Books/<Title> (<id>)/web/assets/site.js"` — generated JS syntax
- `epubcheck` via `--validate` (`brew install epubcheck`, needs Java) — expect `0 fatals / 0 errors / 0 warnings / 0 infos`

## Iterating without re-downloading

Raw chapter HTML is cached in `Books/<Title> (<id>)/.cache/` and the book's
listing data in `meta.json`. Delete a generated `.xhtml` under `OEBPS/` and
re-run — the transform/web rebuild runs fully offline (no auth, no API).
`--force` wipes the whole working dir and downloads fresh.

## Conventions

- **Any change to `epub.py`, `transform.py`, or packaging MUST be validated
  against a real book**: rebuild with `--validate` (or `epubcheck` directly)
  and require `0 fatals / 0 errors / 0 warnings / 0 infos`. epubcheck is the
  Java validator — `brew install epubcheck` pulls in openjdk. Unit tests
  alone are not enough; metadata/structural bugs only surface under
  epubcheck (e.g. `dtb:uid`/`dc:identifier` mismatch).
- Only `META-INF/` + `OEBPS/` may ship inside the EPUB zip — `finalize()`
  must never include `.cache/`, `web/` or dotfiles (see
  `TestFinalize.test_zip_excludes_work_dir_junk`).
- Commits take exactly one trailer: `Co-authored-by: Rixl <agent@rixl.com>`.
  No other attribution lines.
- Web output is fully generated — `build_web` rmtrees `web/` first; stale
  pages must never linger.
