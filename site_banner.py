import functools
import json

from globals import DATA_DIR
from helpers.files import write_json

PATH = DATA_DIR / "site_banner.json"
MAX_LENGTH = 200
KINDS = {"primary": "misc", "positive": "success", "negative": "error"}


def save(text: str, kind: str) -> None:
    write_json(PATH, {"text": text, "kind": kind})


def clear() -> None:
    PATH.unlink(missing_ok=True)


@functools.lru_cache(maxsize=1)
def _read(_mtime: float) -> dict | None:
    try:
        raw = json.loads(PATH.read_text(encoding="utf-8"))
    except ValueError, OSError:
        return None
    text, kind = raw.get("text"), raw.get("kind")
    if not isinstance(text, str) or not text.strip() or kind not in KINDS:
        return None
    return {"text": text, "kind": kind, "style": KINDS[kind]}


def load() -> dict | None:
    try:
        mtime = PATH.stat().st_mtime
    except OSError:
        return None
    return _read(mtime)
