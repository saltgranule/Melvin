import datetime
import functools
import html
import json
import logging
import os
import secrets
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
import time
from pathlib import Path

import markdown
from dotenv import load_dotenv
from flask import Flask, Response, abort, render_template

import dashboard
import http_client
from globals import (
    ADD_BOT_URL,
    DATA_DIR,
    INVITE_URL,
    MELVIN_GITHUB_URL,
    PRIMARY,
    QUATERNARY,
    SECONDARY,
    TERTIARY,
)
from status import get_metrics_status, get_shard_status, summarize_status

load_dotenv()
log = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY")
if not app.secret_key:
    # still works, but everyone gets logged out of the dashboard on every restart
    log.warning("SECRET_KEY isn't set, using a temporary one")
    app.secret_key = secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # browsers still accept secure cookies on http://localhost
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "true").lower()
    == "true",
    PERMANENT_SESSION_LIFETIME=datetime.timedelta(days=7),
    # a little over the 8 MB image limit, so flask turns away anything bigger
    # before reading it, instead of the dashboard finding out afterwards
    MAX_CONTENT_LENGTH=9 * 1024 * 1024,
)
app.register_blueprint(dashboard.bp)


@app.after_request
def add_security_headers(response: Response) -> Response:
    # no framing the site, no guessing file types, and no full urls sent to other sites
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response


DOCS_DIR = Path(app.root_path) / "docs"
LEGAL_DIR = Path(app.root_path) / "legal"
bot_process = None


def start_bot() -> None:
    globals()["bot_process"] = subprocess.Popen(
        [sys.executable, str(Path(app.root_path) / "main.py")],
    )


THEME = {
    "primary": PRIMARY,
    "secondary": SECONDARY,
    "tertiary": TERTIARY,
    "quaternary": QUATERNARY,
}

LINKS = {
    "add": ADD_BOT_URL,
    "invite": INVITE_URL,
    "github": MELVIN_GITHUB_URL,
}


@app.context_processor
def inject_globals() -> dict:
    user = dashboard.current_user()
    return {
        "theme": THEME,
        "links": LINKS,
        "dashboard_user": user,
        "dashboard_avatar": dashboard.user_avatar_url(user) if user else None,
        "csrf_token": dashboard.csrf_token,
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
    return http_client.fetch_json(f"{GITHUB_API}{path}", headers=headers, timeout=5)


def get_repo_meta() -> dict:
    now = time.time()
    cached = _repo_meta_cache["data"]
    if cached is not None and now - _repo_meta_cache["fetched_at"] < REPO_META_TTL:
        return cached

    contributors = []

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
    except http_client.RequestError:
        pass

    data = {
        "contributors": contributors[:6],
        "extra_contributors": max(0, len(contributors) - 6),
    }

    _repo_meta_cache["data"] = data
    _repo_meta_cache["fetched_at"] = now
    return data


BOT_STATS_FILE = DATA_DIR / "bot_stats.json"


def get_bot_stats() -> dict[str, int]:
    try:
        raw = json.loads(BOT_STATS_FILE.read_text(encoding="utf-8"))
        guild_count = int(raw.get("guild_count", 0))
        member_count = int(raw.get("member_count", 0))
    except FileNotFoundError, ValueError, OSError:
        guild_count = 0
        member_count = 0

    return {
        "guild_count": guild_count,
        "member_count": member_count,
    }


@functools.lru_cache(maxsize=64)
def _parse_doc(path: Path, _mtime: float) -> dict:
    # _mtime is only part of the cache key, so edited docs get re-parsed
    text = path.read_text(encoding="utf-8")
    md = markdown.Markdown(
        extensions=["fenced_code", "tables", "toc"],
        extension_configs={"toc": {"toc_depth": "2-3"}},
    )
    content = md.convert(text)

    title = path.stem.replace("-", " ").replace("_", " ").title()
    for line in text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break

    headings = []
    for token in md.toc_tokens:
        headings.append(
            {"id": token["id"], "name": html.unescape(token["name"]), "level": 2},
        )
        headings.extend(
            {"id": child["id"], "name": html.unescape(child["name"]), "level": 3}
            for child in token["children"]
        )

    return {"title": title, "content": content, "headings": headings}


def load_doc(path: Path) -> dict:
    return _parse_doc(path, path.stat().st_mtime)


def get_docs_list() -> list[dict]:
    if not DOCS_DIR.is_dir():
        return []

    docs = []
    for path in sorted(DOCS_DIR.glob("*.md")):
        doc = load_doc(path)
        docs.append(
            {"slug": path.stem, "title": doc["title"], "headings": doc["headings"]},
        )
    return docs


def render_doc(slug: str) -> dict | None:
    path = DOCS_DIR / f"{slug}.md"
    if not path.is_file():
        return None
    return load_doc(path)


@app.route("/")
def home() -> str:
    return render_template(
        "index.html",
        active="home",
        repo=get_repo_meta(),
        stats=get_bot_stats(),
    )


@app.route("/docs")
def docs_index() -> str:
    return render_template(
        "docs.html",
        active="docs",
        docs=get_docs_list(),
        doc=None,
        active_slug=None,
    )


@app.route("/docs/<slug>")
def docs_page(slug: str) -> str:
    doc = render_doc(slug)
    if doc is None:
        abort(404)
    return render_template(
        "docs.html",
        active="docs",
        docs=get_docs_list(),
        doc=doc,
        active_slug=slug,
    )


@app.route("/status")
async def status() -> str:
    shards = await get_shard_status()
    return render_template(
        "status.html",
        active="status",
        shards=shards,
        overall=summarize_status(shards),
        metrics=await get_metrics_status(),
    )


def legal_page(slug: str, active: str) -> str:
    return render_template(
        "legal.html",
        active=active,
        doc=load_doc(LEGAL_DIR / f"{slug}.md"),
    )


@app.route("/privacy")
def privacy() -> str:
    return legal_page("privacy", "privacy")


@app.route("/terms")
def terms() -> str:
    return legal_page("terms", "terms")


@app.errorhandler(404)
def not_found(_error: Exception) -> tuple[str, int]:
    return render_template("404.html", active=None), 404


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
