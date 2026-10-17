"""Command-line interface: auth resolution + download orchestration."""

import argparse
import json
import os
import sys

from platformdirs import user_config_dir
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.prompt import Prompt

from . import constants as C
from .api import ApiError
from .scraper import BookScraper, extract_book_id
from .session import AuthError, OreillySession

DEFAULT_SESSION = os.path.join(user_config_dir("book-scraper"), "cookies.json")


class Printer:
    def __init__(self):
        self.console = Console()
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=self.console,
        )
        self._progress.start()
        self._task_id = None

    def log(self, msg):
        self.console.print(msg)

    def error(self, msg):
        self.console.print(f"[bold red]Error:[/] {msg}")

    def progress(self, done, total, label=""):
        if done <= 1 or self._task_id is None:
            self._task_id = self._progress.add_task(label[:50], total=total)
        self._progress.update(self._task_id, completed=done, description=label[:50])


def parse_cookie_text(text):
    """Accept a JSON cookie dict or a raw 'a=b; c=d' document.cookie string."""
    text = text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    if "=" in text:
        return text
    raise ValueError(
        "That doesn't look like cookies — expected JSON or 'name=value; ...'."
    )


def parse_cred(cred):
    if ":" not in cred:
        raise AuthError("Invalid --cred format. Expected EMAIL:PASSWORD.")
    sep = cred.index(":")
    email = cred[:sep].strip("'\"")
    if "@" not in email:
        raise AuthError("Invalid email in --cred.")
    return email, cred[sep + 1 :]


def password_login(sess, printer, cred=None):
    if cred is None:
        email = Prompt.ask("O'Reilly email").strip()
        cred = (email, Prompt.ask("Password", password=True))
    printer.log("Logging into O'Reilly...")
    sess.do_login(*cred)


def _verified(sess):
    ok, _ = sess.check()
    return ok


def interactive_auth(sess, printer):
    # Best-effort: try harvesting cookies from installed browsers first
    try:
        name = sess.cookies_from_browser()
        if _verified(sess):
            printer.log(f"Authenticated using [cyan]{name}[/] cookies.")
            return
    except AuthError:
        pass

    printer.log("Not signed in. How do you want to authenticate to O'Reilly?")
    while True:
        choice = Prompt.ask(
            "  [b] Read cookies from your browser"
            f" (log in at {C.SAFARI_BASE_URL} first, recommended)\n"
            "  [p] Paste exported cookies (DevTools console: document.cookie)\n"
            "  [l] Email + password login (may fail with ReCaptcha/SSO)\n"
            "  [q] Quit\nauth",
            choices=["b", "p", "l", "q"],
        )
        try:
            if choice == "q":
                sys.exit(1)
            elif choice == "p":
                sess.import_cookies(parse_cookie_text(Prompt.ask("Paste cookies")))
            elif choice == "b":
                name = sess.cookies_from_browser()
                printer.log(f"Loaded cookies from [cyan]{name}[/].")
            elif choice == "l":
                password_login(sess, printer)
        except (AuthError, ValueError) as exc:
            printer.error(str(exc))
            continue

        ok, reason = sess.check()
        if ok:
            printer.log("[green]Successfully authenticated.[/]")
            return
        printer.log(f"Still not authenticated: {reason}")


def ensure_auth(sess, args, printer):
    try:
        if args.cred:
            password_login(sess, printer, parse_cred(args.cred))
        elif args.login:
            password_login(sess, printer)
        elif args.import_cookies:
            with open(args.import_cookies) as f:
                sess.import_cookies(parse_cookie_text(f.read()))
        elif args.browser is not None:
            name = sess.cookies_from_browser(args.browser or None)
            printer.log(f"Loaded cookies from [cyan]{name}[/].")
        elif sess.load_cookies():
            if _verified(sess):
                printer.log("Authenticated with saved session.")
                return
            printer.log("Saved session expired — re-authenticating.")
            interactive_auth(sess, printer)
            return
        else:
            interactive_auth(sess, printer)
            return
    except AuthError as exc:
        printer.error(str(exc))
        sys.exit(1)

    ok, reason = sess.check()
    if not ok:
        printer.error(f"Authentication failed: {reason}")
        sys.exit(1)
    printer.log("[green]Successfully authenticated.[/]")


def build_parser():
    p = argparse.ArgumentParser(
        prog="book-scraper",
        description="Download O'Reilly books as EPUB files.",
    )
    auth = p.add_mutually_exclusive_group()
    auth.add_argument(
        "--login", action="store_true", help="Prompt for O'Reilly email/password"
    )
    auth.add_argument(
        "--cred", metavar="EMAIL:PASSWORD", help="O'Reilly account credentials"
    )
    auth.add_argument(
        "--import-cookies",
        metavar="FILE",
        help="Import cookies exported from your browser (JSON or raw)",
    )
    auth.add_argument(
        "--browser",
        nargs="?",
        const="",
        metavar="NAME",
        help="Read O'Reilly cookies from a browser "
        "(chrome, firefox, edge, arc, brave, vivaldi, "
        "chromium, opera)",
    )
    p.add_argument(
        "--session",
        metavar="FILE",
        default=DEFAULT_SESSION,
        help="Where the session is stored (default: %(default)s)",
    )
    p.add_argument(
        "--no-save", action="store_true", help="Do not save session cookies after login"
    )
    p.add_argument(
        "--kindle",
        action="store_true",
        help="Extra CSS rules to avoid table/pre overflow on e-readers",
    )
    p.add_argument(
        "--pdf",
        action="store_true",
        help="Also produce a PDF next to the EPUB (requires system Pango)",
    )
    p.add_argument(
        "--web",
        action="store_true",
        help="Also produce a browsable web version (sre.google-style layout)",
    )
    p.add_argument(
        "-o",
        "--output",
        metavar="DIR",
        default="Books",
        help="Output directory (default: %(default)s)",
    )
    p.add_argument(
        "book",
        metavar="URL_OR_ID",
        help="learning.oreilly.com book URL or bare book ID",
    )
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    printer = Printer()

    try:
        book_id = extract_book_id(args.book)
    except ValueError as exc:
        printer.error(str(exc))
        return 1

    sess = OreillySession(os.path.expanduser(args.session))
    try:
        ensure_auth(sess, args, printer)
    except (AuthError, OSError) as exc:
        printer.error(f"Authentication failed: {exc}")
        return 1

    if not args.no_save:
        session_dir = os.path.dirname(os.path.expanduser(args.session))
        if session_dir:
            os.makedirs(session_dir, exist_ok=True)
        sess.save_cookies()

    try:
        BookScraper(
            sess,
            args.output,
            kindle=args.kindle,
            pdf=args.pdf,
            web=args.web,
            log=printer.log,
            progress=printer.progress,
        ).run(book_id)
    except (AuthError, ApiError) as exc:
        printer.error(str(exc))
        return 1
    except KeyboardInterrupt:
        printer.log("\nInterrupted — re-run to resume (downloaded chapters are kept).")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
