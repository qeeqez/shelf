"""HTTP session handling: cookies, login, auth verification."""

import json
import os
import re
import time
from urllib.parse import parse_qs, quote_plus, urljoin, urlparse

import httpx
from lxml import html

from . import constants as C


class AuthError(Exception):
    pass


class OreillySession:
    COOKIE_FLOAT_MAX_AGE = re.compile(r"(max-age=\d*\.\d*)", re.IGNORECASE)
    RETRYABLE_STATUSES = (429, 500, 502, 503, 504)

    def __init__(self, cookies_file):
        self.cookies_file = cookies_file
        self.client = httpx.Client(
            headers=C.HEADERS, timeout=30.0, follow_redirects=False
        )
        self.jwt = {}

    # -- low-level request handling ----------------------------------------

    def _update_cookies(self, response):
        # CookieJar silently drops cookies with a float max-age; keep them
        for header in response.headers.get_list("set-cookie"):
            if self.COOKIE_FLOAT_MAX_AGE.search(header):
                key, value = header.split(";")[0].split("=", 1)
                self.client.cookies.set(key, value)

    def request(self, url, is_post=False, perform_redirect=True, retries=3, **kwargs):
        response = None
        for attempt in range(retries):
            try:
                response = self.client.request(
                    "POST" if is_post else "GET", url, **kwargs
                )
            except httpx.TransportError as exc:
                if attempt == retries - 1:
                    raise AuthError(f"Unable to reach {url}: {exc}") from exc
                time.sleep(1 + attempt)
                continue
            except UnicodeError as exc:
                raise AuthError(f"Bad cookie data in session: {exc}") from exc
            if (
                response.status_code in self.RETRYABLE_STATUSES
                and attempt < retries - 1
            ):
                retry_after = response.headers.get("retry-after")
                delay = float(retry_after) if retry_after else 1 + attempt
                time.sleep(delay)
                continue
            break

        self._update_cookies(response)

        if response.is_redirect and perform_redirect:
            location = urljoin(url, response.headers["location"])
            return self.request(
                location, is_post=False, perform_redirect=True, retries=retries
            )
        return response

    # -- cookie persistence -------------------------------------------------

    def load_cookies(self):
        if not os.path.isfile(self.cookies_file):
            return False
        try:
            with open(self.cookies_file) as f:
                self.client.cookies.update(json.load(f))
            return True
        except (json.JSONDecodeError, OSError, TypeError):
            return False

    def save_cookies(self):
        with open(self.cookies_file, "w") as f:
            json.dump(dict(self.client.cookies), f, indent=2)

    def import_cookies(self, cookies):
        """cookies: dict, or a 'name=value; name2=value2' header string."""
        if isinstance(cookies, str):
            for part in cookies.split(";"):
                if "=" in part:
                    k, v = part.split("=", 1)
                    self.client.cookies.set(k.strip(), v.strip())
        else:
            self.client.cookies.update(cookies)

    def cookies_from_browser(self, browser_name=None):
        """Pull oreilly.com cookies from installed browsers (macOS)."""
        from . import browser_cookies

        try:
            source, cookies = browser_cookies.load_cookies(browser_name or None)
        except browser_cookies.CookieError as exc:
            raise AuthError(str(exc)) from exc
        self.client.cookies.update(cookies)
        return source

    # -- authentication -----------------------------------------------------

    def do_login(self, email, password):
        """Programmatic email/password login.

        NOTE: O'Reilly may require ReCaptcha; if so this raises AuthError and
        cookie auth should be used instead.
        """
        response = self.request(C.LOGIN_ENTRY_URL)
        try:
            next_parameter = parse_qs(urlparse(response.request.url).query)["next"][0]
        except (AttributeError, ValueError, IndexError, KeyError) as exc:
            raise AuthError("Could not parse the login entry page.") from exc

        redirect_uri = C.API_ORIGIN_URL + quote_plus(next_parameter)
        response = self.request(
            C.LOGIN_URL,
            is_post=True,
            json={"email": email, "password": password, "redirect_uri": redirect_uri},
            perform_redirect=False,
        )

        if response.status_code != 200:
            messages = []
            try:
                error_page = html.fromstring(response.text)
                messages = [
                    e
                    for e in error_page.xpath("//ul[@class='errorlist']//li/text()")
                    if "password" in e or "email" in e
                ]
                if error_page.xpath("//div[@class='g-recaptcha']"):
                    messages.append(
                        "ReCaptcha required — log in via your browser and use "
                        "cookie auth instead."
                    )
            except (html.etree.ParseError, html.etree.ParserError):
                pass
            raise AuthError(
                "Login failed (HTTP {}).{}".format(
                    response.status_code,
                    "\n  " + "\n  ".join(messages) if messages else "",
                )
            )

        self.jwt = response.json()
        self.request(self.jwt["redirect_uri"])

    def check(self):
        """Verify the session is authenticated and the subscription is active."""
        response = self.request(C.PROFILE_URL, perform_redirect=False)
        if response.status_code != 200:
            return False, f"not authenticated (HTTP {response.status_code})"
        if '"user_type":"Expired"' in response.text:
            return False, "subscription expired"
        return True, None
