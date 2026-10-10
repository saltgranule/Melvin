import hashlib
import json
import logging
import operator
import os
import secrets
import sqlite3
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from flask import (
    Blueprint,
    abort,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.wrappers import Response

import charts
import http_client
import module_config
import module_settings
import server_stats
from globals import ADD_BOT_URL, DATA_DIR

log = logging.getLogger(__name__)

SESSIONS_DB = DATA_DIR / "dashboard.db"
BOT_GUILDS_FILE = DATA_DIR / "bot_guilds.json"

DISCORD_API = "https://discord.com/api/v10"
DISCORD_AUTHORIZE = "https://discord.com/oauth2/authorize"
DISCORD_CDN = "https://cdn.discordapp.com"
SCOPES = "identify guilds"

ADMINISTRATOR = 1 << 3
MANAGE_GUILD = 1 << 5
MANAGE_ROLES = 1 << 28
PERMISSION_BITS = {"manage_guild": MANAGE_GUILD, "manage_roles": MANAGE_ROLES}

TEXT_CHANNEL = 0
NEWS_CHANNEL = 5
# channels and roles fetched with the bot's token are reused for this long
BOT_CACHE_SECONDS = 30
# the bot's own user and the app's owners rarely change, so they're kept much longer
BOT_STATIC_CACHE_SECONDS = 3600

# how long a user's server list is trusted before asking discord again. saving a setting
# uses a shorter window, so lost permissions take effect quickly
GUILDS_CACHE_SECONDS = 120
WRITE_CHECK_SECONDS = 15

# the server sidebar, as (endpoint, label)
GUILD_SECTIONS = [
    ("dashboard.modules", "Modules"),
    ("dashboard.server_stats_page", "Server Stats"),
]

# the server stats charts are drawn at this size, then stretched to fit the page
STATS_CHART_WIDTH = 600
STATS_CHART_HEIGHT = 200

bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


class DiscordError(Exception):
    # discord couldn't be reached or refused the request
    pass


def _config() -> dict[str, str | None]:
    return {
        "client_id": os.environ.get("DISCORD_CLIENT_ID", "1468362201197973756"),
        "client_secret": os.environ.get("DISCORD_CLIENT_SECRET"),
        "redirect_uri": os.environ.get("DASHBOARD_REDIRECT_URI"),
    }


def is_configured() -> bool:
    config = _config()
    return bool(config["client_secret"] and config["redirect_uri"])


# expired sessions are cleared at most this often, on any dashboard request
SESSION_CLEANUP_SECONDS = 3600
_state = {"db_ready": False, "cleaned_at": 0.0}


# session storage, the cookie only holds a random id and this keeps its hash
def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SESSIONS_DB)
    conn.row_factory = sqlite3.Row
    if not _state["db_ready"]:
        conn.execute("PRAGMA journal_mode=WAL")
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
        _state["db_ready"] = True
    return conn


def _cleanup_sessions(*, force: bool = False) -> None:
    now = time.time()
    if not force and now - _state["cleaned_at"] < SESSION_CLEANUP_SECONDS:
        return
    _state["cleaned_at"] = now
    with _connect() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))


def _hash_sid(sid: str) -> str:
    return hashlib.sha256(sid.encode()).hexdigest()


def _create_session(user: dict, access_token: str, expires_in: int) -> str:
    sid = secrets.token_urlsafe(32)
    _cleanup_sessions(force=True)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO sessions (sid_hash, user, access_token, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (_hash_sid(sid), json.dumps(user), access_token, time.time() + expires_in),
        )
    return sid


def _delete_session(sid_hash: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM sessions WHERE sid_hash = ?", (sid_hash,))


def current_session() -> sqlite3.Row | None:
    if "dashboard_session" in g:
        return g.dashboard_session

    _cleanup_sessions()
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
    bot: bool = False,
    form: dict[str, str] | None = None,
) -> dict | list:
    headers = {"User-Agent": "Melvin-Dashboard"}
    if token:
        headers["Authorization"] = f"{'Bot' if bot else 'Bearer'} {token}"
    try:
        return http_client.fetch_json(
            f"{DISCORD_API}{path}",
            headers=headers,
            form=form,
        )
    except http_client.RequestError as e:
        raise DiscordError(e.status) from e


def _can_manage(guild: dict) -> bool:
    permissions = int(guild.get("permissions", 0))
    return bool(
        guild.get("owner") or permissions & ADMINISTRATOR or permissions & MANAGE_GUILD,
    )


def _fetch_guilds(access_token: str, user_id: str, sid_hash: str) -> list[dict]:
    # asks discord for the user's servers and stores them on the session
    raw = _discord_request("/users/@me/guilds", token=access_token)
    guilds = [
        {
            "id": guild["id"],
            "name": guild["name"],
            "icon": guild.get("icon"),
            "owner": bool(guild.get("owner")),
            "permissions": int(guild.get("permissions", 0)),
        }
        for guild in raw
        if _can_manage(guild)
    ]
    if user_id in bot_owner_ids():
        guilds = _with_bot_guilds(guilds)
    with _connect() as conn:
        conn.execute(
            "UPDATE sessions SET guilds = ?, guilds_fetched_at = ? WHERE sid_hash = ?",
            (json.dumps(guilds), time.time(), sid_hash),
        )
    return guilds


# sessions with a server list refresh already running, so a burst of page views starts one
_refreshing: set[str] = set()
_refreshing_lock = threading.Lock()


def _refresh_guilds_later(row: sqlite3.Row) -> None:
    sid_hash = row["sid_hash"]
    with _refreshing_lock:
        if sid_hash in _refreshing:
            return
        _refreshing.add(sid_hash)

    access_token = row["access_token"]
    user_id = json.loads(row["user"])["id"]

    def refresh() -> None:
        try:
            _fetch_guilds(access_token, user_id, sid_hash)
        except DiscordError as e:
            if e.args[0] == 401:
                # the token was revoked or expired, the next page view asks for a new login
                _delete_session(sid_hash)
            else:
                log.warning(
                    "Couldn't refresh a dashboard server list, keeping the cached one",
                )
        finally:
            with _refreshing_lock:
                _refreshing.discard(sid_hash)

    threading.Thread(target=refresh, daemon=True).start()


def manageable_guilds(
    *,
    max_age: float = GUILDS_CACHE_SECONDS,
    strict: bool = False,
) -> list[dict] | None:
    # the servers the logged in user can manage, or None if they need to log in again.
    # strict always waits for discord once the list is older than max_age, and is used
    # for anything that changes settings
    row = current_session()
    if row is None:
        return None

    cached = json.loads(row["guilds"]) if row["guilds"] else None
    cache_age = time.time() - row["guilds_fetched_at"]
    if cached is not None and cache_age < max_age:
        return cached

    # page views use the older list straight away and refresh it in the background
    if cached is not None and not strict:
        _refresh_guilds_later(row)
        return cached

    try:
        return _fetch_guilds(
            row["access_token"],
            json.loads(row["user"])["id"],
            row["sid_hash"],
        )
    except DiscordError as e:
        if e.args[0] == 401:
            # the token was revoked or expired, so the session is no longer valid
            _delete_session(row["sid_hash"])
            session.pop("sid", None)
            g.dashboard_session = None
            return None
        raise


def has_permission(guild: dict, permission: str | None) -> bool:
    if permission is None or guild.get("owner") or guild.get("bot_owner"):
        return True
    permissions = guild.get("permissions", 0)
    return bool(
        permissions & ADMINISTRATOR or permissions & PERMISSION_BITS[permission],
    )


_bot_cache: dict[str, tuple[float, dict | list]] = {}


def _bot_request(
    path: str,
    *,
    fresh: bool = False,
    max_age: float = BOT_CACHE_SECONDS,
) -> dict | list:
    token = os.environ.get("TOKEN")
    if not token:
        raise DiscordError(0)

    cached = _bot_cache.get(path)
    if cached and not fresh and time.time() - cached[0] < max_age:
        return cached[1]

    data = _discord_request(path, token=token, bot=True)
    _bot_cache[path] = (time.time(), data)
    return data


def guild_context(
    guild_id: int,
    user_id: str,
    *,
    fresh: bool = False,
    bot_owner: bool = False,
) -> dict:
    bot_user = _bot_request("/users/@me", max_age=BOT_STATIC_CACHE_SECONDS)

    # fetched together, since none of them depend on each other
    paths = {
        "guild": f"/guilds/{guild_id}",
        "channels": f"/guilds/{guild_id}/channels",
        "bot_member": f"/guilds/{guild_id}/members/{bot_user['id']}",
    }
    if not bot_owner:
        paths["member"] = f"/guilds/{guild_id}/members/{user_id}"
    with ThreadPoolExecutor(max_workers=len(paths)) as pool:
        futures = {
            name: pool.submit(_bot_request, path, fresh=fresh)
            for name, path in paths.items()
        }
        results = {name: future.result() for name, future in futures.items()}
    guild, channels = results["guild"], results["channels"]

    positions = {role["id"]: role["position"] for role in guild["roles"]}
    is_owner = bot_owner or guild["owner_id"] == user_id
    bot_top = max(
        (positions.get(role, 0) for role in results["bot_member"]["roles"]),
        default=0,
    )
    user_top = (
        None
        if is_owner
        else max(
            (positions.get(role, 0) for role in results["member"]["roles"]),
            default=0,
        )
    )

    roles = sorted(guild["roles"], key=operator.itemgetter("position"), reverse=True)
    return {
        "channels": [
            (channel["id"], f"#{channel['name']}")
            for channel in sorted(channels, key=operator.itemgetter("position"))
            if channel["type"] == TEXT_CHANNEL
        ],
        "any_channels": [
            (channel["id"], f"#{channel['name']}")
            for channel in sorted(channels, key=operator.itemgetter("position"))
            if channel["type"] in {TEXT_CHANNEL, NEWS_CHANNEL}
        ],
        # the same rules as the discord side, so neither can hand out more than the other
        "roles": [
            (role["id"], role["name"])
            for role in roles
            if role["id"] != str(guild_id)
            and not role.get("managed")
            and role["position"] < bot_top
            and (user_top is None or role["position"] < user_top)
        ],
        "role_names": {role["id"]: role["name"] for role in roles},
    }


def bot_owner_ids() -> set[str]:
    try:
        app = _bot_request("/oauth2/applications/@me", max_age=BOT_STATIC_CACHE_SECONDS)
    except DiscordError:
        log.warning("Couldn't load Melvin's owners, owner access is off for now")
        return set()
    team = app.get("team")
    if team:
        return {
            member["user"]["id"]
            for member in team["members"]
            if member.get("role") in {"admin", "developer"}
        }
    return {app["owner"]["id"]}


def _with_bot_guilds(guilds: list[dict]) -> list[dict]:
    # every server melvin is in, marked as managed through owner access. servers the
    # owner could already manage keep their real details
    try:
        bot_guilds = []
        after = "0"
        while True:
            page = _bot_request(f"/users/@me/guilds?limit=200&after={after}")
            bot_guilds += page
            if len(page) < 200:
                break
            after = page[-1]["id"]
    except DiscordError:
        log.warning("Couldn't load Melvin's servers for owner access")
        return guilds

    known = {guild["id"]: guild for guild in guilds}
    in_bot = {guild["id"] for guild in bot_guilds}
    return [
        {
            **known.get(
                guild["id"],
                {
                    "id": guild["id"],
                    "name": guild["name"],
                    "icon": guild.get("icon"),
                    "owner": False,
                    "permissions": 0,
                },
            ),
            "bot_owner": True,
        }
        for guild in bot_guilds
    ] + [guild for guild in guilds if guild["id"] not in in_bot]


def bot_guild_ids() -> set[str]:
    try:
        return {str(guild_id) for guild_id in json.loads(BOT_GUILDS_FILE.read_text())}
    except FileNotFoundError, ValueError, OSError:
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


def _guild_header(guild: dict) -> dict:
    return {
        "id": guild["id"],
        "name": guild["name"],
        "icon_url": guild_icon_url(guild),
        "initials": initials(guild["name"]),
    }


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
            {**_guild_header(guild), "has_bot": guild["id"] in present}
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
    except DiscordError, KeyError:
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
        _delete_session(_hash_sid(sid))
    _cleanup_sessions(force=True)
    session.clear()
    return redirect(url_for("home"))


def _find_guild(guilds: list[dict], guild_id: int) -> dict | None:
    match = next((item for item in guilds if item["id"] == str(guild_id)), None)
    # melvin has to be in the server for there to be anything to manage
    if match is None or match["id"] not in bot_guild_ids():
        return None
    return match


def _require_guild(guild_id: int, *, strict: bool = False) -> dict:
    try:
        guilds = manageable_guilds(
            **({"max_age": WRITE_CHECK_SECONDS, "strict": True} if strict else {}),
        )
    except DiscordError:
        abort(redirect(url_for("dashboard.index")))
    if guilds is None:
        abort(redirect(url_for("dashboard.index")))

    match = _find_guild(guilds, guild_id)
    if match is None:
        abort(404)
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
    match = _require_guild(guild_id)

    await module_settings.init_db()
    disabled = await module_settings.disabled_modules(guild_id)

    # set after a save made without the page's script, see _toggle_reply
    toggled = request.args.get("toggled")
    saved_message = (
        f"{module_settings.MODULES[toggled][0]} turned "
        f"{'off' if toggled in disabled else 'on'}. "
        "Changes apply in Discord within a few seconds."
        if toggled in module_settings.MODULES
        else None
    )

    return render_template(
        "dashboard_guild.html",
        saved_message=saved_message,
        active="dashboard",
        guild=_guild_header(match),
        sections=_sidebar(guild_id, "dashboard.modules"),
        modules=[
            {
                "key": key,
                "label": label,
                "description": description,
                "enabled": key not in disabled,
                "configurable": module_config.is_configurable(key),
            }
            for key, (label, description) in module_settings.MODULES.items()
        ],
    )


def _toggle_reply(
    guild_id: int,
    message: str | None,
    status: int,
    *,
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
    # tells the page which module changed, so it can confirm the save
    return redirect(
        url_for(
            "dashboard.modules",
            guild_id=guild_id,
            toggled=request.view_args["module"],
        ),
    )


@bp.route("/<int:guild_id>/modules/<module>", methods=["POST"])
async def toggle_module(guild_id: int, module: str) -> Response | tuple[Response, int]:
    _check_csrf()
    if module not in module_settings.MODULES:
        abort(404)

    # permissions are checked with discord again before anything is saved
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

    return _toggle_reply(guild_id, None, 200, enabled=enabled)


def _check_value(
    setting: module_config.Setting,
    value: str | None,
    guild: dict,
    context: dict,
) -> None:
    # checks that only the dashboard can do, raising ConfigError like clean_value
    if not has_permission(guild, setting.permission):
        needed = (setting.permission or "").replace("_", " ").title()
        msg = f"You need {needed} to change this."
        raise module_config.ConfigError(msg)
    if value is None:
        return
    if setting.kind in {"channel", "channels"}:
        available = dict(_channel_options(setting, context))
        if any(part not in available for part in value.split(",")):
            msg = (
                "That channel isn't available, Melvin can only use text channels here."
            )
            raise module_config.ConfigError(msg)
    if setting.kind == "role" and value not in dict(context["roles"]):
        msg = "That role is above Melvin's or your top role, or can't be given out."
        raise module_config.ConfigError(msg)


def _channel_options(
    setting: module_config.Setting,
    context: dict,
) -> list[tuple[str, str]]:
    return list(
        context["any_channels"]
        if setting.channel_type == "any"
        else context["channels"],
    )


def _config_fields(
    module: str,
    values: dict[str, str | None],
    errors: dict[str, str],
    guild: dict,
    context: dict,
) -> list[dict]:
    fields = []
    for setting in module_config.CONFIG[module]:
        value = values.get(setting.key)
        options: list[tuple[str, str]] = []
        if setting.kind in {"channel", "channels"}:
            options = _channel_options(setting, context)
        elif setting.kind == "role":
            options = list(context["roles"])
        elif setting.kind == "choice":
            options = list(setting.choices)

        # keep showing a saved channel or role that's since gone or out of reach
        if value and setting.kind in {"channel", "role"} and value not in dict(options):
            name = context["role_names"].get(value) if setting.kind == "role" else None
            options.insert(0, (value, name or f"Unknown {setting.kind}"))
        selected = value.split(",") if setting.kind == "channels" and value else []
        options += [
            (part, "Unknown channel") for part in selected if part not in dict(options)
        ]

        fields.append(
            {
                "setting": setting,
                "value": value,
                "options": options,
                "selected": selected,
                "error": errors.get(setting.key),
                "locked": not has_permission(guild, setting.permission),
                # only valid hex codes get a swatch, values from a failed save aren't checked yet
                "colors": (
                    value.split("-")
                    if setting.kind == "color"
                    and value
                    and module_config.COLOR_PATTERN.match(value)
                    else []
                ),
            },
        )
    return fields


@bp.route("/<int:guild_id>/modules/<module>/config", methods=["GET", "POST"])
async def module_config_page(
    guild_id: int,
    module: str,
) -> str | Response | tuple[str, int]:
    if not module_config.is_configurable(module):
        abort(404)

    posting = request.method == "POST"
    if posting:
        _check_csrf()

    match = _require_guild(guild_id, strict=posting)

    user = current_user()
    try:
        context = guild_context(
            guild_id,
            user["id"],
            fresh=posting,
            bot_owner=bool(match.get("bot_owner")),
        )
    except DiscordError, KeyError:
        log.exception("Couldn't load channels and roles for guild %s", guild_id)
        context = None

    await module_config.init_db()
    values = await module_config.get_all(guild_id, module)
    errors: dict[str, str] = {}

    if posting and context is not None:
        updates: dict[str, str | None] = {}
        images: dict[str, object] = {}
        submitted = dict(values)

        for setting in module_config.CONFIG[module]:
            key = setting.key
            if setting.kind == "image":
                upload = request.files.get(key)
                if upload and upload.filename:
                    images[key] = upload
                elif request.form.get(f"{key}__remove") == "on" and values[key]:
                    images[key] = None
                continue

            if setting.kind == "channels":
                raw = ",".join(request.form.getlist(key))
            else:
                raw = request.form.get(key, "")
            submitted[key] = raw or None
            try:
                value = module_config.clean_value(setting, raw)
                # an empty field resets to the default, which counts as unchanged
                if (value or setting.default) == values[key]:
                    continue
                _check_value(setting, value, match, context)
                updates[key] = value
            except module_config.ConfigError as e:
                errors[key] = str(e)

        for key, upload in images.items():
            setting = module_config.get_setting(module, key)
            try:
                _check_value(setting, None, match, context)
                if upload is None:
                    await module_config.remove_image(guild_id, module, key)
                else:
                    data = upload.read(module_config.MAX_IMAGE_BYTES + 1)
                    await module_config.replace_image(
                        guild_id,
                        module,
                        key,
                        upload.filename,
                        data,
                    )
            except module_config.ConfigError as e:
                errors[key] = str(e)

        if not errors:
            if updates:
                await module_config.set_values(guild_id, module, updates)
            return redirect(
                url_for(
                    "dashboard.module_config_page",
                    guild_id=guild_id,
                    module=module,
                    saved=1,
                ),
            )
        values = submitted

    label, description = module_settings.MODULES[module]
    page = render_template(
        "dashboard_config.html",
        active="dashboard",
        guild=_guild_header(match),
        sections=_sidebar(guild_id, "dashboard.modules"),
        module={
            "key": module,
            "label": label,
            "description": description,
            "enabled": module not in await module_settings.disabled_modules(guild_id),
        },
        fields=_config_fields(module, values, errors, match, context)
        if context
        else [],
        unavailable=context is None,
        saved=request.args.get("saved") == "1" and not posting,
        errors=errors,
    )
    return (page, 400) if errors else page


@bp.route("/<int:guild_id>/modules/<module>/config/<key>.image")
async def config_image(guild_id: int, module: str, key: str) -> Response:
    if not module_config.is_configurable(module):
        abort(404)
    try:
        setting = module_config.get_setting(module, key)
        guilds = manageable_guilds()
    except KeyError, DiscordError:
        abort(404)
    if (
        setting.kind != "image"
        or guilds is None
        or _find_guild(guilds, guild_id) is None
    ):
        abort(404)

    # only ever serves files from the data folder
    file = module_config.image_file(await module_config.get(guild_id, module, key))
    if file is None:
        abort(404)
    return send_file(file)


def _time_ago(start: int) -> str:
    # how long ago a point began, for its tooltip
    seconds = max(0, int(time.time()) - start)
    for unit, length in (("day", 86400), ("hour", 3600), ("minute", 60)):
        if seconds >= length:
            amount = seconds // length
            return f"{amount} {unit}{'' if amount == 1 else 's'} ago"
    return "Just now"


# pretty much a statcord.xyz rewrite, will be appended with more soon!!
@bp.route("/<int:guild_id>/stats")
async def server_stats_page(guild_id: int) -> str | Response:
    match = _require_guild(guild_id)

    range_key = request.args.get("range", server_stats.DEFAULT_RANGE)
    if range_key not in server_stats.RANGES:
        range_key = server_stats.DEFAULT_RANGE

    await server_stats.init_db()
    series = await server_stats.get_series(guild_id, range_key)
    width, height = STATS_CHART_WIDTH, STATS_CHART_HEIGHT
    whens = [_time_ago(start) for start in series["starts"]]

    # messages and voice minutes are stacked, so their scale starts at zero
    messages, voice = series["messages"], series["voice"]
    totals = [m + v for m, v in zip(messages, voice, strict=True)]
    top = max(totals) or 1
    total_ys = charts.scale(totals, 0, top, height)
    message_ys = charts.scale(messages, 0, top, height)

    # the member scale fits the counts, like the status charts, so changes are visible.
    # periods before the first reading use the first reading
    known = [count for count in series["members"] if count is not None]
    members = [
        count if count is not None else (known[0] if known else 0)
        for count in series["members"]
    ]
    member_ys = charts.scale(members, min(members), max(members), height)

    return render_template(
        "dashboard_stats.html",
        active="dashboard",
        guild=_guild_header(match),
        sections=_sidebar(guild_id, "dashboard.server_stats_page"),
        ranges=[(key, label) for key, (label, _, _) in server_stats.RANGES.items()],
        range_key=range_key,
        range_label=series["label"],
        has_data=series["has_data"],
        counting=await module_settings.is_enabled(guild_id, "serverstats"),
        width=width,
        height=height,
        cards=[
            {
                "label": "Total messages",
                "value": f"{series['total_messages']:,}",
                "meta": f"In the last {series['label']}",
            },
            {
                "label": "Total voice minutes",
                "value": f"{series['total_voice']:,}",
                "meta": f"In the last {series['label']}",
            },
            {
                "label": "Member count",
                "value": f"{series['member_count'] or 0:,}",
                "meta": "Right now",
            },
            {
                "label": "Net growth",
                # joins minus leaves over the range, signed so a drop is clear
                "value": f"{series['member_change']:+,}"
                if series["member_change"]
                else "0",
                "meta": f"In the last {series['label']}",
            },
        ],
        activity={
            "messages": charts.area_points(message_ys, width, height),
            "voice": charts.band_points(total_ys, message_ys, width),
            "tooltip": charts.tooltip_points(
                whens,
                total_ys,
                height,
                [
                    ("Messages", messages, "", "series-1"),
                    ("Voice minutes", voice, "", "series-2"),
                ],
            ),
        },
        members={
            "points": charts.area_points(member_ys, width, height),
            "tooltip": charts.tooltip_points(
                whens,
                member_ys,
                height,
                [("Members", members, "", "series-1")],
            ),
        },
        start_label=series["start_label"],
    )
