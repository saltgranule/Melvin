import hashlib
import json
import logging
import os
import secrets
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from flask import (
    Blueprint,
    abort,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.wrappers import Response

import module_settings
from globals import ADD_BOT_URL

log = logging.getLogger(__name__)

DATA_DIR = Path("data")
SESSIONS_DB = DATA_DIR / "dashboard.db"
BOT_GUILDS_FILE = DATA_DIR / "bot_guilds.json"

DISCORD_API = "https://discord.com/api/v10"
DISCORD_AUTHORIZE = "https://discord.com/oauth2/authorize"
DISCORD_CDN = "https://cdn.discordapp.com"
SCOPES = "identify guilds"

ADMINISTRATOR = 1 << 3
MANAGE_GUILD = 1 << 5

# how long a user's server list is trusted before asking discord again, saving a
# setting uses a much shorter window so lost permissions take effect quickly
GUILDS_CACHE_SECONDS = 120
WRITE_CHECK_SECONDS = 15

# sections in the server sidebar, as (endpoint, label)
GUILD_SECTIONS = [("dashboard.modules", "Modules")]

bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


class DiscordError(Exception):
    """Discord couldn't be reached or refused the request."""


def _config() -> dict[str, str | None]:
    return {
        "client_id": os.environ.get("DISCORD_CLIENT_ID", "1468362201197973756"),
        "client_secret": os.environ.get("DISCORD_CLIENT_SECRET"),
        "redirect_uri": os.environ.get("DASHBOARD_REDIRECT_URI"),
    }


def is_configured() -> bool:
    config = _config()
    return bool(config["client_secret"] and config["redirect_uri"])


# session storage, the cookie only holds a random id and this keeps its hash
def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SESSIONS_DB)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            sid_hash TEXT PRIMARY KEY,
            user TEXT NOT NULL,
            access_token TEXT NOT NULL,
            guilds TEXT,
            guilds_fetched_at REAL NOT NULL DEFAULT 0,
            expires_at REAL NOT NULL
        )
        """,
    )
    return conn


def _hash_sid(sid: str) -> str:
    return hashlib.sha256(sid.encode()).hexdigest()


def _create_session(user: dict, access_token: str, expires_in: int) -> str:
    sid = secrets.token_urlsafe(32)
    with _connect() as conn:
        # clear out expired sessions while we're here
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (time.time(),))
        conn.execute(
            """
            INSERT INTO sessions (sid_hash, user, access_token, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (_hash_sid(sid), json.dumps(user), access_token, time.time() + expires_in),
        )
    return sid


def _delete_session(sid: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM sessions WHERE sid_hash = ?", (_hash_sid(sid),))


def current_session() -> sqlite3.Row | None:
    if "dashboard_session" in g:
        return g.dashboard_session

    row = None
    sid = session.get("sid")
    if sid:
        with _connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE sid_hash = ? AND expires_at > ?",
                (_hash_sid(sid), time.time()),
            ).fetchone()
        if row is None:
            session.pop("sid", None)

    g.dashboard_session = row
    return row


def current_user() -> dict | None:
    row = current_session()
    return json.loads(row["user"]) if row else None


def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def _check_csrf() -> None:
    sent = request.form.get("csrf", "")
    expected = session.get("csrf", "")
    if not expected or not secrets.compare_digest(sent, expected):
        abort(400)


# discord api
def _discord_request(
    path: str,
    *,
    token: str | None = None,
    form: dict[str, str] | None = None,
) -> dict | list:
    headers = {"Accept": "application/json", "User-Agent": "Melvin-Dashboard"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    data = None
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    request_ = urllib.request.Request(f"{DISCORD_API}{path}", data=data, headers=headers)  # ruff: ignore[suspicious-url-open-usage]
    try:
        with urllib.request.urlopen(request_, timeout=10) as response:  # ruff: ignore[suspicious-url-open-usage]
            return json.load(response)
    except urllib.error.HTTPError as e:
        raise DiscordError(e.code) from e
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise DiscordError(0) from e


def _can_manage(guild: dict) -> bool:
    permissions = int(guild.get("permissions", 0))
    return bool(
        guild.get("owner")
        or permissions & ADMINISTRATOR
        or permissions & MANAGE_GUILD,
    )


def manageable_guilds(
    *,
    max_age: float = GUILDS_CACHE_SECONDS,
    strict: bool = False,
) -> list[dict] | None:
    """The servers the logged in user can manage, or None if they need to log in again.

    strict never falls back to an older list when discord can't be reached, for
    anything that changes settings.
    """
    row = current_session()
    if row is None:
        return None

    cached = json.loads(row["guilds"]) if row["guilds"] else None
    cache_age = time.time() - row["guilds_fetched_at"]
    if cached is not None and cache_age < max_age:
        return cached

    try:
        raw = _discord_request("/users/@me/guilds", token=row["access_token"])
    except DiscordError as e:
        if e.args[0] == 401:
            # the token was revoked or expired, so the session is no good
            _delete_session(session.pop("sid"))
            g.dashboard_session = None
            return None
        if strict or cached is None:
            raise
        log.warning("Couldn't refresh a dashboard server list, using the cached one")
        return cached

    guilds = [
        {"id": guild["id"], "name": guild["name"], "icon": guild.get("icon")}
        for guild in raw
        if _can_manage(guild)
    ]
    with _connect() as conn:
        conn.execute(
            "UPDATE sessions SET guilds = ?, guilds_fetched_at = ? WHERE sid_hash = ?",
            (json.dumps(guilds), time.time(), row["sid_hash"]),
        )
    return guilds


def bot_guild_ids() -> set[str]:
    try:
        return {str(guild_id) for guild_id in json.loads(BOT_GUILDS_FILE.read_text())}
    except (FileNotFoundError, ValueError, OSError):
        return set()


def guild_icon_url(guild: dict) -> str | None:
    if not guild.get("icon"):
        return None
    return f"{DISCORD_CDN}/icons/{guild['id']}/{guild['icon']}.png?size=96"


def user_avatar_url(user: dict) -> str:
    if user.get("avatar"):
        return f"{DISCORD_CDN}/avatars/{user['id']}/{user['avatar']}.png?size=64"
    # discord's default avatars are picked from the user id
    return f"{DISCORD_CDN}/embed/avatars/{(int(user['id']) >> 22) % 6}.png"


def initials(name: str) -> str:
    return "".join(word[0] for word in name.split()[:2]).upper() or "?"


# routes
@bp.route("/")
def index() -> str:
    if current_session() is None:
        return render_template("dashboard_login.html", active="dashboard", error=None)

    try:
        guilds = manageable_guilds()
    except DiscordError:
        return render_template(
            "dashboard_login.html",
            active="dashboard",
            error="Couldn't reach Discord to load your servers, please try again.",
        )
    if guilds is None:
        return redirect(url_for("dashboard.index"))

    present = bot_guild_ids()
    cards = sorted(
        (
            {
                "id": guild["id"],
                "name": guild["name"],
                "icon_url": guild_icon_url(guild),
                "initials": initials(guild["name"]),
                "has_bot": guild["id"] in present,
            }
            for guild in guilds
        ),
        key=lambda card: (not card["has_bot"], card["name"].lower()),
    )
    return render_template(
        "dashboard.html",
        active="dashboard",
        guilds=cards,
        add_bot_url=ADD_BOT_URL,
    )


@bp.route("/login")
def login() -> str | Response:
    if not is_configured():
        log.warning(
            "Dashboard login needs DISCORD_CLIENT_SECRET and DASHBOARD_REDIRECT_URI",
        )
        return render_template(
            "dashboard_login.html",
            active="dashboard",
            error="The dashboard isn't set up yet.",
        )

    config = _config()
    state = secrets.token_urlsafe(24)
    session["oauth_state"] = state
    query = urllib.parse.urlencode(
        {
            "client_id": config["client_id"],
            "redirect_uri": config["redirect_uri"],
            "response_type": "code",
            "scope": SCOPES,
            "state": state,
            "prompt": "none",
        },
    )
    return redirect(f"{DISCORD_AUTHORIZE}?{query}")


@bp.route("/callback")
def callback() -> str | Response:
    expected_state = session.pop("oauth_state", None)
    state = request.args.get("state", "")
    if not expected_state or not secrets.compare_digest(state, expected_state):
        return render_template(
            "dashboard_login.html",
            active="dashboard",
            error="That login link expired, please try again.",
        )

    code = request.args.get("code")
    if not code:
        # discord sends an error instead of a code when the user cancels
        return render_template(
            "dashboard_login.html",
            active="dashboard",
            error="Login was cancelled.",
        )

    config = _config()
    try:
        token = _discord_request(
            "/oauth2/token",
            form={
                "client_id": config["client_id"],
                "client_secret": config["client_secret"],
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": config["redirect_uri"],
            },
        )
        user = _discord_request("/users/@me", token=token["access_token"])
    except (DiscordError, KeyError):
        log.exception("Dashboard login failed")
        return render_template(
            "dashboard_login.html",
            active="dashboard",
            error="Couldn't log you in with Discord, please try again.",
        )

    sid = _create_session(
        {
            "id": user["id"],
            "name": user.get("global_name") or user["username"],
            "avatar": user.get("avatar"),
        },
        token["access_token"],
        int(token.get("expires_in", 604800)),
    )
    # a fresh cookie on login, so nothing from before carries over
    session.clear()
    session.permanent = True
    session["sid"] = sid
    return redirect(url_for("dashboard.index"))


@bp.route("/logout", methods=["POST"])
def logout() -> Response:
    _check_csrf()
    sid = session.get("sid")
    if sid:
        _delete_session(sid)
    session.clear()
    return redirect(url_for("home"))


def _find_guild(guilds: list[dict], guild_id: int) -> dict | None:
    match = next((item for item in guilds if item["id"] == str(guild_id)), None)
    # melvin has to be in the server for there to be anything to manage
    if match is None or match["id"] not in bot_guild_ids():
        return None
    return match


def _sidebar(guild_id: int, active: str) -> list[dict]:
    return [
        {
            "label": label,
            "url": url_for(endpoint, guild_id=guild_id),
            "active": endpoint == active,
        }
        for endpoint, label in GUILD_SECTIONS
    ]


@bp.route("/<int:guild_id>")
def guild(guild_id: int) -> Response:
    return redirect(url_for("dashboard.modules", guild_id=guild_id))


@bp.route("/<int:guild_id>/modules")
async def modules(guild_id: int) -> str | Response:
    try:
        guilds = manageable_guilds()
    except DiscordError:
        return redirect(url_for("dashboard.index"))
    if guilds is None:
        return redirect(url_for("dashboard.index"))

    # not finding it and not being allowed look the same from outside
    match = _find_guild(guilds, guild_id)
    if match is None:
        abort(404)

    await module_settings.init_db()
    disabled = await module_settings.disabled_modules(guild_id)
    return render_template(
        "dashboard_guild.html",
        active="dashboard",
        guild={
            "id": match["id"],
            "name": match["name"],
            "icon_url": guild_icon_url(match),
            "initials": initials(match["name"]),
        },
        sections=_sidebar(guild_id, "dashboard.modules"),
        modules=[
            {
                "key": key,
                "label": label,
                "description": description,
                "enabled": key not in disabled,
            }
            for key, (label, description) in module_settings.MODULES.items()
        ],
    )


def _toggle_reply(
    guild_id: int,
    message: str | None,
    status: int,
    enabled: bool | None = None,
) -> Response | tuple[Response, int]:
    # the page's script asks for json, a plain form post goes back to the page
    if request.headers.get("X-Requested-With") == "fetch":
        if message is None:
            return jsonify(enabled=enabled)
        return jsonify(error=message), status
    if status == 401:
        return redirect(url_for("dashboard.index"))
    if message is not None:
        abort(status)
    return redirect(url_for("dashboard.modules", guild_id=guild_id))


@bp.route("/<int:guild_id>/modules/<module>", methods=["POST"])
async def toggle_module(guild_id: int, module: str) -> Response | tuple[Response, int]:
    _check_csrf()
    if module not in module_settings.MODULES:
        abort(404)

    # permissions are checked against discord again before anything is saved
    try:
        guilds = manageable_guilds(max_age=WRITE_CHECK_SECONDS, strict=True)
    except DiscordError as e:
        message = (
            "Discord is busy right now, try again in a few seconds."
            if e.args[0] == 429
            else "Couldn't reach Discord to check your permissions, try again."
        )
        return _toggle_reply(guild_id, message, 503)
    if guilds is None:
        return _toggle_reply(guild_id, "Your login expired, please log in again.", 401)
    if _find_guild(guilds, guild_id) is None:
        return _toggle_reply(
            guild_id,
            "You don't have Manage Server in this server.",
            403,
        )

    enabled = request.form.get("enabled") == "true"
    try:
        await module_settings.init_db()
        await module_settings.set_enabled(guild_id, module, enabled=enabled)
    except Exception:
        log.exception("Failed to save module %s for guild %s", module, guild_id)
        return _toggle_reply(guild_id, "Couldn't save that, please try again.", 500)

    return _toggle_reply(guild_id, None, 200, enabled)
