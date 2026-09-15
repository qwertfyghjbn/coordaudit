import requests


def get_url(url: str) -> str | None:
    try:
        resp = requests.get(url, timeout=5)
        return resp.text
    except requests.RequestException:
        return None
