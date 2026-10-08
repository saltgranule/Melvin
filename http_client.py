import json
import urllib.error
import urllib.parse
import urllib.request


class RequestError(Exception):
    def __init__(self, status: int) -> None:
        super().__init__(status)
        self.status = status


def fetch_json(
    url: str,
    *,
    headers: dict[str, str],
    form: dict[str, str] | None = None,
    timeout: float = 10,
) -> dict | list:
    if not url.startswith("https://"):
        msg = "only https urls are fetched"
        raise ValueError(msg)

    headers = {"Accept": "application/json", **headers}
    data = None
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    request = urllib.request.Request(url, data=data, headers=headers)  # ruff: ignore[suspicious-url-open-usage]
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # ruff: ignore[suspicious-url-open-usage]
            return json.load(response)
    except urllib.error.HTTPError as e:
        raise RequestError(e.code) from e
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise RequestError(0) from e
