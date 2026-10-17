ORLY_BASE_HOST = "oreilly.com"
SAFARI_BASE_HOST = "learning." + ORLY_BASE_HOST
API_ORIGIN_HOST = "api." + ORLY_BASE_HOST

ORLY_BASE_URL = "https://www." + ORLY_BASE_HOST
SAFARI_BASE_URL = "https://" + SAFARI_BASE_HOST
API_ORIGIN_URL = "https://" + API_ORIGIN_HOST

PROFILE_URL = SAFARI_BASE_URL + "/profile/"
LOGIN_URL = ORLY_BASE_URL + "/member/auth/login/"
LOGIN_ENTRY_URL = SAFARI_BASE_URL + "/login/unified/?next=/home/"

EPUB_API = SAFARI_BASE_URL + "/api/v2/epubs/urn:orm:book:{0}/"
EPUB_FILES_API = SAFARI_BASE_URL + "/api/v2/epubs/urn:orm:book:{0}/files"
CHAPTERS_API = (
    SAFARI_BASE_URL + "/api/v2/epub-chapters/?epub_identifier=urn:orm:book:{0}"
)

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Referer": LOGIN_ENTRY_URL,
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}
