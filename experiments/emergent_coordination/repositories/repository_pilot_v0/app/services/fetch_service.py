from app.common.http_client import get_url


class FetchService:
    def fetch_remote(self, url: str) -> str | None:
        return get_url(url)
