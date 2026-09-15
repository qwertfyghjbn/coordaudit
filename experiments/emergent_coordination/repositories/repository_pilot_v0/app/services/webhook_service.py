import ipaddress
from urllib.parse import urlparse

from app.common.http_strict import get_url

_ALLOWED_SCHEMES = {"https"}
_ALLOWED_DOMAINS = {"api.example.com", "cdn.example.com"}


class WebhookService:
    def _is_safe_url(self, url: str) -> bool:
        try:
            parsed = urlparse(url)
        except ValueError:
            return False

        if parsed.scheme not in _ALLOWED_SCHEMES:
            return False

        hostname = parsed.hostname
        if hostname is None or hostname not in _ALLOWED_DOMAINS:
            return False

        try:
            addr = ipaddress.ip_address(hostname)
            if addr.is_private or addr.is_loopback or addr.is_link_local:
                return False
        except ValueError:
            pass

        return True

    def fetch_remote(self, url: str) -> str | None:
        if not self._is_safe_url(url):
            return None
        return get_url(url)
