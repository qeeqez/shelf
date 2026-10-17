# Agent notes

## Commands

- `uv run book-scraper <URL_OR_ID>` — run the CLI (flags: `--web --pdf --kindle --validate --force`)
- `uv run pytest tests/` — unit tests
- `uv run ruff check .` / `uv run ruff format .` — lint / format
- `node --check "Books/<Title> (<id>)/web/assets/site.js"` — generated JS syntax
- `epubcheck` via `--validate` (`brew install epubcheck`) — expect `0 fatals / 0 errors / 0 warnings / 0 infos`

## Iterating without re-downloading

Raw chapter HTML is cached in `Books/<Title> (<id>)/.cache/`. Delete a
generated `.xhtml` under `OEBPS/` and re-run — the transform/web rebuild
runs fully offline from the cache. `--force` wipes the whole working dir.

## Conventions

- Only `META-INF/` + `OEBPS/` may ship inside the EPUB zip — `finalize()`
  must never include `.cache/`, `web/` or dotfiles (see
  `TestFinalize.test_zip_excludes_work_dir_junk`).
- Commits take exactly one trailer: `Co-authored-by: Rixl <agent@rixl.com>`.
  No other attribution lines.
- Web output is fully generated — `build_web` rmtrees `web/` first; stale
  pages must never linger.
