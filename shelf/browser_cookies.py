"""Harvest oreilly.com cookies from local browsers on macOS.

Chromium-family browsers encrypt cookie values with AES-128-CBC using a key
derived (PBKDF2-SHA1, salt 'saltysalt', 1003 iterations) from a password in
the login keychain ('<Browser> Safe Storage'). Firefox stores them plaintext
in a sqlite db. Safari is not supported (its cookie container requires Full
Disk Access); paste cookies manually instead.
"""

import shutil
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

APP_SUPPORT = Path.home() / "Library/Application Support"

# name -> (profile dir under ~/Library/Application Support, keychain service)
CHROMIUM_BROWSERS = {
    "chrome": ("Google/Chrome", "Chrome Safe Storage"),
    "chromium": ("Chromium", "Chromium Safe Storage"),
    "brave": ("BraveSoftware/Brave-Browser", "Brave Safe Storage"),
    "edge": ("Microsoft Edge", "Microsoft Edge Safe Storage"),
    "arc": ("Arc/User Data", "Arc Safe Storage"),
    "vivaldi": ("Vivaldi", "Vivaldi Safe Storage"),
    "opera": ("com.operasoftware.Opera", "Opera Safe Storage"),
}

CHROME_EPOCH_OFFSET = 11644473600  # seconds between 1601-01-01 and 1970-01-01


class CookieError(Exception):
    pass


def _keychain_password(service):
    try:
        return subprocess.run(
            ["security", "find-generic-password", "-w", "-s", service],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        raise CookieError(
            f"Keychain denied access to {service!r} — click Allow when prompted."
        ) from exc


def _chrome_key(service):
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA1(),
        length=16,
        salt=b"saltysalt",
        iterations=1003,
    )
    return kdf.derive(_keychain_password(service).encode("utf-8"))


def _decrypt_v10(key, blob):
    ct = blob[3:]
    dec = Cipher(algorithms.AES(key), modes.CBC(b" " * 16)).decryptor()
    plain = dec.update(ct) + dec.finalize()
    pad = plain[-1]
    if 1 <= pad <= 16:
        plain = plain[:-pad]
    # Chromium >=130 prepends SHA-256(host_key) to the plaintext — strip it.
    candidates = (plain, plain[32:]) if len(plain) > 32 else (plain,)
    for candidate in candidates:
        try:
            return candidate.decode("utf-8")
        except UnicodeDecodeError:
            continue
    raise CookieError("cookie value is not decodable text")


def _open_db_copy(db_path):
    """Copy a (possibly locked/WAL) sqlite db + siblings to a temp file."""
    tmpdir = tempfile.mkdtemp(prefix="shelf-")
    dest = Path(tmpdir) / db_path.name
    for suffix in ("", "-wal", "-shm"):
        src = Path(str(db_path) + suffix)
        if src.exists():
            shutil.copy2(src, Path(str(dest) + suffix))
    return sqlite3.connect(dest)


def _live(unix_expiry):
    return unix_expiry == 0 or unix_expiry > time.time()


def _chromium_cookies(profile_dir, service):
    key = None
    cookies = {}
    for db_path in sorted(profile_dir.glob("*/Network/Cookies")) + sorted(
        profile_dir.glob("*/Cookies")
    ):
        try:
            db = _open_db_copy(db_path)
        except OSError:
            continue
        try:
            rows = db.execute(
                "SELECT host_key, name, value, encrypted_value, expires_utc "
                "FROM cookies WHERE host_key LIKE '%oreilly.com'"
            ).fetchall()
        except sqlite3.Error:
            db.close()
            continue
        db.close()

        for host, name, value, encrypted, expires_utc in rows:
            unix_expiry = expires_utc / 1_000_000 - CHROME_EPOCH_OFFSET
            if expires_utc and not _live(unix_expiry):
                continue
            if value:
                cookies[name] = value
            elif encrypted.startswith(b"v10"):
                if key is None:
                    key = _chrome_key(service)
                try:
                    cookies[name] = _decrypt_v10(key, encrypted)
                except CookieError:
                    continue  # undecryptable/binary blob — not usable anyway
    return cookies


def _firefox_cookies(profiles_dir):
    cookies = {}
    for db_path in sorted(profiles_dir.glob("*/cookies.sqlite")):
        try:
            db = _open_db_copy(db_path)
            rows = db.execute(
                "SELECT name, value, expiry FROM moz_cookies "
                "WHERE host LIKE '%oreilly.com'"
            ).fetchall()
            db.close()
        except (OSError, sqlite3.Error):
            continue
        for name, value, expiry in rows:
            if _live(expiry):
                cookies[name] = value
    return cookies


def _header_safe(cookies):
    """Cookie values must be ASCII to be sent in a Cookie header."""
    return {k: v for k, v in cookies.items() if v.isascii()}


def load_cookies(browser=None):
    """Return (source_name, {cookie_name: value}) for oreilly.com cookies.

    With browser=None, tries every supported browser in order.
    Raises CookieError when nothing usable is found.
    """
    if browser == "firefox":
        cookies = _header_safe(_firefox_cookies(APP_SUPPORT / "Firefox/Profiles"))
        if cookies:
            return "firefox", cookies
        raise CookieError("No O'Reilly cookies found in firefox.")

    if browser in CHROMIUM_BROWSERS:
        profile_dir, service = CHROMIUM_BROWSERS[browser]
        profile_dir = APP_SUPPORT / profile_dir
        cookies = (
            _header_safe(_chromium_cookies(profile_dir, service))
            if profile_dir.is_dir()
            else {}
        )
        if cookies:
            return browser, cookies
        raise CookieError(f"No O'Reilly cookies found in {browser}.")

    if browser is not None:
        raise CookieError(
            "Unsupported browser {!r}. Supported: {}, firefox.".format(
                browser, ", ".join(CHROMIUM_BROWSERS)
            )
        )

    for name, (profile_dir, service) in CHROMIUM_BROWSERS.items():
        profile_dir = APP_SUPPORT / profile_dir
        if not profile_dir.is_dir():
            continue
        try:
            cookies = _header_safe(_chromium_cookies(profile_dir, service))
        except CookieError:
            continue
        if cookies:
            return name, cookies

    cookies = _header_safe(_firefox_cookies(APP_SUPPORT / "Firefox/Profiles"))
    if cookies:
        return "firefox", cookies

    raise CookieError(
        "No O'Reilly cookies found in any browser. "
        "Log into learning.oreilly.com in your browser first."
    )
