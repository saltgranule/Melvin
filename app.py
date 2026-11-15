import asyncio
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
from flask import Flask, Response, abort, redirect, render_template, url_for
from werkzeug.exceptions import HTTPException

import dashboard
import site_banner
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
    log.warning("SECRET_KEY isn't set, using a temporary one")
    app.secret_key = secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "true").lower()
    == "true",
    PERMANENT_SESSION_LIFETIME=datetime.timedelta(days=7),
    MAX_CONTENT_LENGTH=9 * 1024 * 1024,
)
app.register_blueprint(dashboard.bp)

ROOT = Path(app.root_path)
DOCS_DIR = ROOT / "docs"
LEGAL_DIR = ROOT / "legal"
BOT_STATS_FILE = DATA_DIR / "bot_stats.json"

GITHUB_API = "https://api.github.com/repos/saltgranule/Melvin"
HIDDEN_CONTRIBUTORS = {"replit-agent"}
SHOWN_CONTRIBUTORS = 6
REPO_META_TTL = 600

SECURITY_HEADERS = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
}

ERROR_MESSAGES = {
    400: "Invalid request body, try again?",
    401: "This page requires you to be logged in",
    403: "Nope, you don't have permission to view this page",
    404: "Page doesn't exist, or was removed",
    405: "Invalid request",
    413: "Too big of an upload",
    429: "Too many requests",
    500: "Melvin is dead",
    502: "Discord is dead",
    503: "Melvin is dead",
}


def _rgb(color: str) -> tuple[int, int, int]:
    value = int(color.lstrip("#"), 16)
    return value >> 16, (value >> 8) & 0xFF, value & 0xFF


def mix(color: str, other: str, weight: float) -> str:
    return "#" + "".join(
        f"{round(x * weight + y * (1 - weight)):02x}"
        for x, y in zip(_rgb(color), _rgb(other), strict=True)
    )


def alpha(color: str, opacity: float) -> str:
    r, g, b = _rgb(color)
    return f"rgba({r}, {g}, {b}, {opacity})"


THEME = {
    "primary": PRIMARY,
    "secondary": SECONDARY,
    "tertiary": TERTIARY,
    "quaternary": QUATERNARY,
}

DARK_SURFACE = "#252422"
_dark_chart_2_fill = mix(PRIMARY, "#ffffff", 0.55)
THEME_SHADES = {
    "light": {
        "chart-2-fill": mix(PRIMARY, "#ffffff", 0.45),
        "chart-key-1": mix(PRIMARY, "#ffffff", 0.55),
        "chart-key-2": mix(PRIMARY, "#ffffff", 0.32),
        "mark-bg": alpha(PRIMARY, 0.35),
    },
    "dark": {
        "chart-2-fill": _dark_chart_2_fill,
        "chart-key-1": mix(PRIMARY, DARK_SURFACE, 0.8),
        "chart-key-2": mix(_dark_chart_2_fill, DARK_SURFACE, 0.9),
    },
}

LINKS = {
    "add": ADD_BOT_URL,
    "invite": INVITE_URL,
    "github": MELVIN_GITHUB_URL,
}

bot_process: subprocess.Popen | None = None
_repo_meta: tuple[float, dict] | None = None


def start_bot() -> None:
    global bot_process
    bot_process = subprocess.Popen([sys.executable, str(ROOT / "main.py")])


@app.after_request
def add_security_headers(response: Response) -> Response:
    for header, value in SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    return response


@app.context_processor
def inject_globals() -> dict:
    user = dashboard.current_user()
    return {
        "theme": THEME,
        "theme_shades": THEME_SHADES,
        "links": LINKS,
        "dashboard_user": user,
        "dashboard_avatar": dashboard.user_avatar_url(user) if user else None,
        "csrf_token": dashboard.csrf_token,
        # called by the login page, which several routes render
        "bot_stats": get_bot_stats,
        "repo_meta": get_repo_meta,
        "site_banner": site_banner.load(),
    }


def _github_get(path: str) -> dict | list:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Melvin-Frontend",
    }
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    return http_client.fetch_json(f"{GITHUB_API}{path}", headers=headers, timeout=5)


def get_repo_meta() -> dict:
    global _repo_meta
    now = time.time()
    if _repo_meta is not None and now - _repo_meta[0] < REPO_META_TTL:
        return _repo_meta[1]

    try:
        contributors = [
            {
                "login": c["login"],
                "avatar_url": c["avatar_url"],
                "html_url": c["html_url"],
            }
            for c in _github_get("/contributors?per_page=30")
            if c.get("type") == "User"
            and c.get("login", "").lower() not in HIDDEN_CONTRIBUTORS
        ]
    except http_client.RequestError:
        contributors = []

    data = {
        "contributors": contributors[:SHOWN_CONTRIBUTORS],
        "extra_contributors": max(0, len(contributors) - SHOWN_CONTRIBUTORS),
    }
    _repo_meta = (now, data)
    return data


@functools.lru_cache(maxsize=1)
def _read_bot_stats(_mtime: float) -> dict[str, int]:
    try:
        raw = json.loads(BOT_STATS_FILE.read_text(encoding="utf-8"))
        return {
            "guild_count": int(raw.get("guild_count", 0)),
            "member_count": int(raw.get("member_count", 0)),
        }
    except ValueError, OSError:
        return {"guild_count": 0, "member_count": 0}


def get_bot_stats() -> dict[str, int]:
    try:
        mtime = BOT_STATS_FILE.stat().st_mtime
    except OSError:
        return {"guild_count": 0, "member_count": 0}
    return _read_bot_stats(mtime)


@functools.lru_cache(maxsize=64)
def _parse_doc(path: Path, _mtime: float) -> dict:
    text = path.read_text(encoding="utf-8")
    md = markdown.Markdown(
        extensions=["fenced_code", "tables", "toc"],
        extension_configs={"toc": {"toc_depth": "2-3"}},
    )
    content = md.convert(text)

    title = next(
        (line[2:].strip() for line in text.splitlines() if line.startswith("# ")),
        path.stem.replace("-", " ").replace("_", " ").title(),
    )

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
    return load_doc(path) if path.is_file() else None


@app.route("/")
def home() -> str | Response:
    if dashboard.current_session() is not None:
        return redirect(url_for("dashboard.index"))
    return render_template("login.html", active="home", error=None)

# routes (probably shouldve labelled this sooner)
@app.route("/donations")
def donations() -> str:
    return render_template("donations.html", active="donations")


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
    shards, metrics = await asyncio.gather(get_shard_status(), get_metrics_status())
    return render_template(
        "status.html",
        active="status",
        shards=shards,
        overall=summarize_status(shards),
        metrics=metrics,
    )


def legal_page(slug: str) -> str:
    return render_template(
        "legal.html",
        active=slug,
        doc=load_doc(LEGAL_DIR / f"{slug}.md"),
    )


@app.route("/privacy")
def privacy() -> str:
    return legal_page("privacy")


@app.route("/terms")
def terms() -> str:
    return legal_page("terms")


def error_page(error: HTTPException) -> tuple[str, int]:
    code = error.code or 500
    page = render_template(
        "error.html",
        active=None,
        code=code,
        message=ERROR_MESSAGES[code],
    )
    return page, code


for _code in ERROR_MESSAGES:
    app.register_error_handler(_code, error_page)


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
