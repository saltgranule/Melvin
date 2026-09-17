import json
import os
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import markdown
from flask import Flask, abort, render_template

from globals import (
    INVITE_URL,
    MELVIN_GITHUB_URL,
    PRIMARY,
    QUATERNARY,
    SECONDARY,
    TERTIARY,
)
from status import get_shard_status, get_metrics_status

app = Flask(__name__)

DOCS_DIR = Path(app.root_path) / "docs"
bot_process = None


def start_bot() -> None:
    globals()["bot_process"] = subprocess.Popen([sys.executable, "main.py"])


THEME = {
    "primary": PRIMARY,
    "secondary": SECONDARY,
    "tertiary": TERTIARY,
    "quaternary": QUATERNARY,
}

LINKS = {
    "invite": INVITE_URL,
    "github": MELVIN_GITHUB_URL,
}

GITHUB_REPO = "saltgranule/Melvin"
GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}"
HIDDEN_CONTRIBUTORS = {"replit-agent"}
REPO_META_TTL = 600
_repo_meta_cache = {"data": None, "fetched_at": 0}


def _github_get(path: str) -> dict | list:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Melvin-Frontend",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"{GITHUB_API}{path}"
    if not url.startswith("https://"):
        raise ValueError("Invalid URL scheme")

    request = urllib.request.Request(url, headers=headers)  # ruff: ignore[suspicious-url-open-usage]
    with urllib.request.urlopen(request, timeout=5) as response:  # ruff: ignore[suspicious-url-open-usage]
        return json.load(response)


def format_count(count: int) -> str:
    if count >= 1000:
        return f"{count / 1000:.1f}".rstrip("0").rstrip(".") + "k"
    return str(count)


def get_repo_meta() -> int | dict:
    now = time.time()
    cached = _repo_meta_cache["data"]
    if cached is not None and now - _repo_meta_cache["fetched_at"] < REPO_META_TTL:
        return cached

    star_count = 0
    contributors = []

    try:
        repo = _github_get("")
        star_count = repo.get("stargazers_count", 0)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
        pass

    try:
        raw_contributors = _github_get("/contributors?per_page=30")
        contributors = [
            {
                "login": c["login"],
                "avatar_url": c["avatar_url"],
                "html_url": c["html_url"],
            }
            for c in raw_contributors
            if c.get("type") == "User"
            and c.get("login", "").lower() not in HIDDEN_CONTRIBUTORS
        ]
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
        pass

    data = {
        "star_count": format_count(star_count),
        "contributors": contributors[:6],
        "extra_contributors": max(0, len(contributors) - 6),
    }

    _repo_meta_cache["data"] = data
    _repo_meta_cache["fetched_at"] = now
    return data


BOT_STATS_FILE = Path(app.root_path) / "data" / "bot_stats.json"


def get_bot_stats() -> dict[str, str]:
    try:
        raw = json.loads(BOT_STATS_FILE.read_text(encoding="utf-8"))
        guild_count = int(raw.get("guild_count", 0))
        member_count = int(raw.get("member_count", 0))
    except (FileNotFoundError, ValueError, OSError):
        guild_count = 0
        member_count = 0

    return {
        "guild_count": format_count(guild_count),
        "member_count": format_count(member_count),
    }


def get_docs_list() -> list[str]:
    if not DOCS_DIR.is_dir():
        return []

    docs = []
    for path in sorted(DOCS_DIR.glob("*.md")):
        title = path.stem.replace("-", " ").replace("_", " ").title()
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
        docs.append({"slug": path.stem, "title": title})
    return docs


def render_doc(slug: str) -> str | None:
    path = DOCS_DIR / f"{slug}.md"
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    return markdown.markdown(text, extensions=["fenced_code", "tables"])


@app.route("/")
def home() -> str:
    return render_template(
        "index.html",
        active="home",
        theme=THEME,
        links=LINKS,
        repo=get_repo_meta(),
        stats=get_bot_stats(),
    )


@app.route("/docs")
def docs_index() -> str:
    return render_template(
        "docs.html",
        active="docs",
        theme=THEME,
        links=LINKS,
        docs=get_docs_list(),
        content=None,
        active_slug=None,
    )


@app.route("/docs/<slug>")
def docs_page(slug: str) -> str:
    content = render_doc(slug)
    if content is None:
        abort(404)
    return render_template(
        "docs.html",
        active="docs",
        theme=THEME,
        links=LINKS,
        docs=get_docs_list(),
        content=content,
        active_slug=slug,
    )


@app.route("/status")
async def status() -> str:
    return render_template(
        "status.html",
        active="status",
        theme=THEME,
        links=LINKS,
        shards=await get_shard_status(),
        metrics=await get_metrics_status(),
    )


@app.errorhandler(404)
def not_found(_error: Exception) -> tuple[str, int]:
    return render_template("404.html", active=None, theme=THEME, links=LINKS), 404


if __name__ == "__main__":
    start_bot()

    try:
        app.run(
            host=os.environ.get("HOST", "0.0.0.0"),  # ruff: ignore[hardcoded-bind-all-interfaces]
            port=int(os.environ.get("PORT", "3005")),
            debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true",
            use_reloader=False,
        )
    finally:
        if bot_process is not None:
            bot_process.terminate()