import re
from collections import Counter
from collections.abc import AsyncIterator, Iterable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path

import aiosqlite

from globals import DATA_DIR

DB_PATH = DATA_DIR / "reactionroles.db"

MAX_PANELS = 20
MAX_ROWS = 4
MAX_BUTTONS_PER_ROW = 5
MAX_SELECT_OPTIONS = 25

MAX_TITLE = 100
MAX_BODY = 1500
MAX_FOOTER = 200
MAX_LABEL = 80
MAX_DESCRIPTION = 100
MAX_PLACEHOLDER = 150
MAX_GROUP = 32
MAX_IMAGE_URL = 500

KIND_BUTTONS = "buttons"
KIND_MULTI = "multi"
KIND_SINGLE = "single"
KINDS = (KIND_BUTTONS, KIND_MULTI, KIND_SINGLE)

MODE_TOGGLE = "toggle"
MODE_ADD = "add"
MODE_REMOVE = "remove"
MODES = (MODE_TOGGLE, MODE_ADD, MODE_REMOVE)

STYLES = ("primary", "secondary", "success", "danger")
DEFAULT_STYLE = "secondary"

def button_id(panel_id: int, option_id: int) -> str:
    return f"rr:b:{panel_id}:{option_id}"

def select_id(panel_id: int, row_id: int) -> str:
    return f"rr:s:{panel_id}:{row_id}"

@dataclass(frozen=True, slots=True)
class Option:
    id: int
    row_id: int
    role_id: int
    label: str
    emoji: str | None
    description: str | None
    style: str
    mode: str
    group: str | None
    required_role_id: int | None

@dataclass(frozen=True, slots=True)
class Row:
    id: int
    panel_id: int
    kind: str
    placeholder: str | None
    min_values: int
    max_values: int
    options: tuple[Option, ...] = ()

@dataclass(frozen=True, slots=True)
class Panel:
    id: int
    guild_id: int
    channel_id: int | None
    message_id: int | None
    title: str
    body: str
    footer: str | None
    color: int | None
    image_url: str | None
    rows: tuple[Row, ...] = ()
    _options: Mapping[int, Option] = field(default_factory=dict, repr=False, compare=False)

    @property
    def published(self) -> bool:
        return self.message_id is not None

    @property
    def options(self) -> tuple[Option, ...]:
        return tuple(o for row in self.rows for o in row.options)

    def option(self, option_id: int) -> Option | None:
        return self._options.get(option_id)

    def row(self, row_id: int) -> Row | None:
        return next((r for r in self.rows if r.id == row_id), None)

def build_panel(
    *,
    id: int,
    guild_id: int,
    channel_id: int | None,
    message_id: int | None,
    title: str,
    body: str,
    footer: str | None,
    color: int | None,
    image_url: str | None,
    rows: Iterable[Row],
) -> Panel:
    rows = tuple(rows)
    index = {o.id: o for row in rows for o in row.options}
    return Panel(
        id=id,
        guild_id=guild_id,
        channel_id=channel_id,
        message_id=message_id,
        title=title,
        body=body,
        footer=footer,
        color=color,
        image_url=image_url,
        rows=rows,
        _options=index,
    )

@dataclass(frozen=True, slots=True)
class Plan:
    add: frozenset[int] = frozenset()
    remove: frozenset[int] = frozenset()
    error: str | None = None
    notice: str | None = None

    @property
    def changes(self) -> bool:
        return bool(self.add or self.remove)

def _resolve(panel: Panel, desired: Mapping[int, bool], held: frozenset[int]) -> Plan:
    options = {o.id: o for o in panel.options}
    add: set[int] = set()
    remove: set[int] = set()

    for option_id, want in desired.items():
        opt = options[option_id]
        has = opt.role_id in held
        if want and not has and opt.mode != MODE_REMOVE:
            if opt.required_role_id is not None and opt.required_role_id not in held:
                return Plan(
                    error=f"You need <@&{opt.required_role_id}> before you can get <@&{opt.role_id}>.",
                )
            add.add(opt.role_id)
        elif not want and has and opt.mode != MODE_ADD:
            remove.add(opt.role_id)

    for option_id, want in desired.items():
        opt = options[option_id]
        if not want or opt.group is None or opt.role_id not in add:
            continue
        for other in panel.options:
            if (
                other.group == opt.group
                and other.role_id != opt.role_id
                and other.role_id in held
                and other.role_id not in add
            ):
                remove.add(other.role_id)

    return Plan(frozenset(add), frozenset(remove))

def plan_button(panel: Panel, option: Option, held: frozenset[int]) -> Plan:
    has = option.role_id in held
    if option.mode == MODE_ADD:
        want = True
    elif option.mode == MODE_REMOVE:
        want = False
    else:
        want = not has

    plan = _resolve(panel, {option.id: want}, held)
    if plan.error or plan.changes:
        return plan
    if option.mode == MODE_ADD:
        return Plan(notice=f"You already have <@&{option.role_id}>.")
    return Plan(notice=f"You don't have <@&{option.role_id}>.")

def plan_select(
    panel: Panel,
    row: Row,
    chosen: frozenset[int],
    held: frozenset[int],
) -> Plan:
    row_ids = {o.id for o in row.options}
    if not chosen <= row_ids:
        return Plan(error="One of those options was removed. Ask a moderator to republish the panel.")

    picked_groups = Counter(o.group for o in row.options if o.id in chosen and o.group)
    for group, count in picked_groups.items():
        if count > 1:
            return Plan(error=f"Pick only one option from **{group}**.")

    desired = {o.id: o.id in chosen for o in row.options}
    plan = _resolve(panel, desired, held)
    if plan.error or plan.changes:
        return plan
    return Plan(notice="Nothing changed.")

def parse_color(text: str) -> int:
    value = text.strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", value):
        raise ValueError(text)
    return int(value, 16)

def parse_message_id(text: str) -> int | None:
    token = text.strip().rstrip("/").split("/")[-1]
    return int(token) if token.isdigit() else None

def text_error(title: str | None, body: str | None, footer: str | None) -> str | None:
    if title is not None:
        if not title.strip():
            return "The title can't be empty."
        if len(title) > MAX_TITLE:
            return f"Titles can be {MAX_TITLE} characters at most."
    if body is not None and len(body) > MAX_BODY:
        return f"The body can be {MAX_BODY} characters at most."
    if footer is not None and len(footer) > MAX_FOOTER:
        return f"The footer can be {MAX_FOOTER} characters at most."
    return None

def image_error(url: str) -> str | None:
    if not url.startswith("https://") or len(url) > MAX_IMAGE_URL:
        return "The image must be an https:// link."
    return None

CUSTOM_EMOJI = re.compile(r"<a?:\w{2,32}:\d{15,25}>")
EMOJI_ERROR = "That emoji isn't valid. Use one emoji, or a custom server emoji."

def emoji_error(text: str) -> str | None:
    value = text.strip()
    if CUSTOM_EMOJI.fullmatch(value):
        return None
    if value and len(value) <= 16 and all(ord(c) > 127 for c in value):
        return None
    return EMOJI_ERROR

def render_text(text: str | None, server_name: str) -> str | None:
    if text is None:
        return None
    return text.replace("{server}", server_name)

SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS rr_panels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        channel_id INTEGER,
        message_id INTEGER UNIQUE,
        title TEXT NOT NULL,
        body TEXT NOT NULL DEFAULT '',
        footer TEXT,
        color INTEGER,
        image_url TEXT,
        created_by INTEGER NOT NULL,
        created_at INTEGER NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS rr_panels_guild ON rr_panels(guild_id)",
    """
    CREATE TABLE IF NOT EXISTS rr_rows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        panel_id INTEGER NOT NULL REFERENCES rr_panels(id) ON DELETE CASCADE,
        position INTEGER NOT NULL,
        kind TEXT NOT NULL,
        placeholder TEXT,
        min_values INTEGER NOT NULL DEFAULT 0,
        max_values INTEGER NOT NULL DEFAULT 1
    )
    """,
    "CREATE INDEX IF NOT EXISTS rr_rows_panel ON rr_rows(panel_id)",
    """
    CREATE TABLE IF NOT EXISTS rr_options (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        row_id INTEGER NOT NULL REFERENCES rr_rows(id) ON DELETE CASCADE,
        position INTEGER NOT NULL,
        role_id INTEGER NOT NULL,
        label TEXT NOT NULL,
        emoji TEXT,
        description TEXT,
        style TEXT NOT NULL DEFAULT 'secondary',
        mode TEXT NOT NULL DEFAULT 'toggle',
        group_name TEXT,
        required_role_id INTEGER
    )
    """,
    "CREATE INDEX IF NOT EXISTS rr_options_row ON rr_options(row_id)",
    "CREATE INDEX IF NOT EXISTS rr_options_role ON rr_options(role_id)",
)

PANEL_COLUMNS = frozenset({"channel_id", "message_id", "title", "body", "footer", "color", "image_url"})

class Store:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DB_PATH

    @asynccontextmanager

    async def _db(self) -> AsyncIterator[aiosqlite.Connection]:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            yield db

    async def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with self._db() as db:
            await db.execute("PRAGMA journal_mode = WAL")
            for statement in SCHEMA:
                await db.execute(statement)
            await db.commit()

    async def _load(self, db: aiosqlite.Connection, where: str, params: tuple) -> list[Panel]:
        cur = await db.execute(
            "SELECT id, guild_id, channel_id, message_id, title, body, footer, color, image_url "
            f"FROM rr_panels WHERE {where} ORDER BY id",
            params,
        )
        panel_rows = await cur.fetchall()
        panels: list[Panel] = []
        for p in panel_rows:
            cur = await db.execute(
                "SELECT id, kind, placeholder, min_values, max_values FROM rr_rows "
                "WHERE panel_id = ? ORDER BY position, id",
                (p[0],),
            )
            row_data = await cur.fetchall()
            cur = await db.execute(
                "SELECT o.id, o.row_id, o.role_id, o.label, o.emoji, o.description, o.style, "
                "o.mode, o.group_name, o.required_role_id FROM rr_options o "
                "JOIN rr_rows r ON r.id = o.row_id WHERE r.panel_id = ? "
                "ORDER BY r.position, r.id, o.position, o.id",
                (p[0],),
            )
            opts_by_row: dict[int, list[Option]] = {}
            for o in await cur.fetchall():
                opts_by_row.setdefault(o[1], []).append(
                    Option(
                        id=o[0],
                        row_id=o[1],
                        role_id=o[2],
                        label=o[3],
                        emoji=o[4],
                        description=o[5],
                        style=o[6],
                        mode=o[7],
                        group=o[8],
                        required_role_id=o[9],
                    ),
                )
            rows = tuple(
                Row(
                    id=r[0],
                    panel_id=p[0],
                    kind=r[1],
                    placeholder=r[2],
                    min_values=r[3],
                    max_values=r[4],
                    options=tuple(opts_by_row.get(r[0], ())),
                )
                for r in row_data
            )
            panels.append(
                build_panel(
                    id=p[0],
                    guild_id=p[1],
                    channel_id=p[2],
                    message_id=p[3],
                    title=p[4],
                    body=p[5],
                    footer=p[6],
                    color=p[7],
                    image_url=p[8],
                    rows=rows,
                ),
            )
        return panels

    async def panel(self, panel_id: int) -> Panel | None:
        async with self._db() as db:
            found = await self._load(db, "id = ?", (panel_id,))
        return found[0] if found else None

    async def panels_in_guild(self, guild_id: int) -> list[Panel]:
        async with self._db() as db:
            return await self._load(db, "guild_id = ?", (guild_id,))

    async def all_panels(self) -> list[Panel]:
        async with self._db() as db:
            return await self._load(db, "1 = 1", ())

    async def count_in_guild(self, guild_id: int) -> int:
        async with self._db() as db:
            cur = await db.execute("SELECT COUNT(*) FROM rr_panels WHERE guild_id = ?", (guild_id,))
            row = await cur.fetchone()
        return int(row[0]) if row else 0

    async def create_panel(
        self,
        *,
        guild_id: int,
        created_by: int,
        title: str,
        body: str,
        footer: str | None,
        color: int | None,
        image_url: str | None,
        created_at: int,
    ) -> int:
        async with self._db() as db:
            cur = await db.execute(
                "INSERT INTO rr_panels (guild_id, title, body, footer, color, image_url, "
                "created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (guild_id, title, body, footer, color, image_url, created_by, created_at),
            )
            await db.commit()
            return int(cur.lastrowid)

    async def update_panel(self, panel_id: int, **fields: object) -> None:
        bad = set(fields) - PANEL_COLUMNS
        if bad:
            msg = f"not a panel column: {sorted(bad)}"
            raise ValueError(msg)
        if not fields:
            return
        assignments = ", ".join(f"{name} = ?" for name in fields)
        async with self._db() as db:
            await db.execute(
                f"UPDATE rr_panels SET {assignments} WHERE id = ?",
                (*fields.values(), panel_id),
            )
            await db.commit()

    async def delete_panel(self, panel_id: int) -> None:
        async with self._db() as db:
            await db.execute("DELETE FROM rr_panels WHERE id = ?", (panel_id,))
            await db.commit()

    async def delete_guild(self, guild_id: int) -> list[int]:
        async with self._db() as db:
            cur = await db.execute("SELECT id FROM rr_panels WHERE guild_id = ?", (guild_id,))
            ids = [r[0] for r in await cur.fetchall()]
            await db.execute("DELETE FROM rr_panels WHERE guild_id = ?", (guild_id,))
            await db.commit()
        return ids

    async def panel_by_message(self, message_id: int) -> Panel | None:
        async with self._db() as db:
            found = await self._load(db, "message_id = ?", (message_id,))
        return found[0] if found else None

    async def save_panel(self, panel: Panel) -> None:
        async with self._db() as db:
            await db.execute(
                "UPDATE rr_panels SET title = ?, body = ?, footer = ?, color = ?, image_url = ? WHERE id = ?",
                (panel.title, panel.body, panel.footer, panel.color, panel.image_url, panel.id),
            )
            cur = await db.execute("SELECT id FROM rr_rows WHERE panel_id = ?", (panel.id,))
            stored_rows = {r[0] for r in await cur.fetchall()}
            kept_rows = {r.id for r in panel.rows if r.id > 0 and r.id in stored_rows}
            for gone in stored_rows - kept_rows:
                await db.execute("DELETE FROM rr_rows WHERE id = ?", (gone,))

            for position, row in enumerate(panel.rows):
                if row.id > 0 and row.id in stored_rows:
                    row_id = row.id
                    await db.execute(
                        "UPDATE rr_rows SET position = ?, kind = ?, placeholder = ?, min_values = ?, "
                        "max_values = ? WHERE id = ?",
                        (position, row.kind, row.placeholder, row.min_values, row.max_values, row_id),
                    )
                else:
                    cur = await db.execute(
                        "INSERT INTO rr_rows (panel_id, position, kind, placeholder, min_values, max_values) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (panel.id, position, row.kind, row.placeholder, row.min_values, row.max_values),
                    )
                    row_id = cur.lastrowid

                cur = await db.execute("SELECT id FROM rr_options WHERE row_id = ?", (row_id,))
                stored_options = {r[0] for r in await cur.fetchall()}
                kept_options = {o.id for o in row.options if o.id > 0 and o.id in stored_options}
                for gone in stored_options - kept_options:
                    await db.execute("DELETE FROM rr_options WHERE id = ?", (gone,))

                for opos, o in enumerate(row.options):
                    values = (opos, o.role_id, o.label, o.emoji, o.description, o.style, o.mode,
                              o.group, o.required_role_id)
                    if o.id > 0 and o.id in stored_options:
                        await db.execute(
                            "UPDATE rr_options SET position = ?, role_id = ?, label = ?, emoji = ?, "
                            "description = ?, style = ?, mode = ?, group_name = ?, required_role_id = ? "
                            "WHERE id = ?",
                            (*values, o.id),
                        )
                    else:
                        await db.execute(
                            "INSERT INTO rr_options (row_id, position, role_id, label, emoji, description, "
                            "style, mode, group_name, required_role_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (row_id, *values),
                        )
            await db.commit()

    async def _drop_options(
        self,
        db: aiosqlite.Connection,
        where: str,
        params: tuple,
    ) -> set[int]:
        cur = await db.execute(
            "SELECT o.id, o.row_id, r.panel_id FROM rr_options o "
            f"JOIN rr_rows r ON r.id = o.row_id WHERE {where}",
            params,
        )
        found = await cur.fetchall()
        if not found:
            return set()
        option_ids = [f[0] for f in found]
        row_ids = {f[1] for f in found}
        panel_ids = {f[2] for f in found}
        await db.execute(
            f"DELETE FROM rr_options WHERE id IN ({','.join('?' * len(option_ids))})",
            option_ids,
        )
        await db.execute(
            f"DELETE FROM rr_rows WHERE id IN ({','.join('?' * len(row_ids))}) "
            "AND id NOT IN (SELECT row_id FROM rr_options)",
            list(row_ids),
        )
        return panel_ids

    async def remove_role_from_guild(self, guild_id: int, role_id: int) -> set[int]:
        async with self._db() as db:
            affected = await self._drop_options(
                db,
                "o.role_id = ? AND r.panel_id IN (SELECT id FROM rr_panels WHERE guild_id = ?)",
                (role_id, guild_id),
            )
            cur = await db.execute(
                "SELECT DISTINCT r.panel_id FROM rr_options o JOIN rr_rows r ON r.id = o.row_id "
                "WHERE o.required_role_id = ? AND r.panel_id IN "
                "(SELECT id FROM rr_panels WHERE guild_id = ?)",
                (role_id, guild_id),
            )
            affected |= {r[0] for r in await cur.fetchall()}
            await db.execute(
                "UPDATE rr_options SET required_role_id = NULL WHERE required_role_id = ? "
                "AND row_id IN (SELECT r.id FROM rr_rows r JOIN rr_panels p ON p.id = r.panel_id "
                "WHERE p.guild_id = ?)",
                (role_id, guild_id),
            )
            await db.commit()
        return affected

MAX_COMPONENTS = 40

def _with_rows(panel: Panel, rows: Iterable[Row]) -> Panel:
    rows = tuple(rows)
    return replace(panel, rows=rows, _options={o.id: o for r in rows for o in r.options})

def _temp_id(panel: Panel) -> int:
    ids = [r.id for r in panel.rows] + [o.id for o in panel.options]
    return min([0, *ids]) - 1

def _row(panel: Panel, row_id: int) -> Row:
    row = panel.row(row_id)
    if row is None:
        raise ValueError("That row is gone. Pick another one.")
    return row

def _map_row(panel: Panel, row_id: int, fn) -> Panel:
    _row(panel, row_id)
    return _with_rows(panel, (fn(r) if r.id == row_id else r for r in panel.rows))

def _find_option(panel: Panel, option_id: int) -> Option:
    option = panel.option(option_id)
    if option is None:
        raise ValueError("That option is gone. Pick another one.")
    return option

def _map_option(panel: Panel, option_id: int, fn) -> Panel:
    _find_option(panel, option_id)

    def fix(row: Row) -> Row:
        if not any(o.id == option_id for o in row.options):
            return row
        return replace(row, options=tuple(fn(o) if o.id == option_id else o for o in row.options))

    return _with_rows(panel, (fix(r) for r in panel.rows))

def _check_row_bounds(kind: str, placeholder: str | None, lo: int, hi: int) -> tuple[int, int]:
    if kind not in KINDS:
        raise ValueError("Pick buttons, a multi-select, or a single-select.")
    if placeholder is not None and len(placeholder) > MAX_PLACEHOLDER:
        raise ValueError(f"Placeholders can be {MAX_PLACEHOLDER} characters at most.")
    if kind == KIND_BUTTONS:
        return 0, 1
    if kind == KIND_SINGLE:
        return min(lo, 1), 1
    if not 0 <= lo <= hi <= MAX_SELECT_OPTIONS or hi < 1:
        raise ValueError(f"Choices must be between 0 and {MAX_SELECT_OPTIONS}, with min no higher than max.")
    return lo, hi

def set_text(
    panel: Panel,
    *,
    title: str,
    body: str,
    footer: str | None,
    color: int | None,
    image_url: str | None,
) -> Panel:
    error = text_error(title, body, footer or None)
    if error is None and image_url:
        error = image_error(image_url)
    if error:
        raise ValueError(error)
    return replace(
        panel,
        title=title.strip(),
        body=body,
        footer=footer or None,
        color=color,
        image_url=image_url or None,
    )

def add_row(panel: Panel, *, kind: str, placeholder: str | None, lo: int, hi: int) -> Panel:
    if len(panel.rows) >= MAX_ROWS:
        raise ValueError(f"A panel can have {MAX_ROWS} rows at most.")
    lo, hi = _check_row_bounds(kind, placeholder, lo, hi)
    row = Row(
        id=_temp_id(panel),
        panel_id=panel.id,
        kind=kind,
        placeholder=placeholder or None,
        min_values=lo,
        max_values=hi,
    )
    return _with_rows(panel, (*panel.rows, row))

def update_row(
    panel: Panel,
    row_id: int,
    *,
    kind: str,
    placeholder: str | None,
    lo: int,
    hi: int,
) -> Panel:
    current = _row(panel, row_id)
    if (current.kind == KIND_BUTTONS) != (kind == KIND_BUTTONS):
        raise ValueError("A button row can't become a dropdown, or the other way round. Add a new row.")
    lo, hi = _check_row_bounds(kind, placeholder, lo, hi)
    return _map_row(
        panel,
        row_id,
        lambda r: replace(r, kind=kind, placeholder=placeholder or None, min_values=lo, max_values=hi),
    )

def remove_row(panel: Panel, row_id: int) -> Panel:
    _row(panel, row_id)
    return _with_rows(panel, (r for r in panel.rows if r.id != row_id))

def add_option(
    panel: Panel,
    row_id: int,
    *,
    role_id: int,
    label: str,
    emoji: str | None,
    description: str | None,
    style: str,
    mode: str,
    group: str | None,
    required_role_id: int | None,
) -> Panel:
    row = _row(panel, row_id)
    if row.kind == KIND_BUTTONS and len(row.options) >= MAX_BUTTONS_PER_ROW:
        raise ValueError(f"A button row holds {MAX_BUTTONS_PER_ROW} buttons at most.")
    if row.kind != KIND_BUTTONS and len(row.options) >= MAX_SELECT_OPTIONS:
        raise ValueError(f"A dropdown holds {MAX_SELECT_OPTIONS} options at most.")
    if any(o.role_id == role_id for o in panel.options):
        raise ValueError(f"<@&{role_id}> is already in this panel.")
    _check_option_fields(label, emoji, description, style, mode, group)
    option = Option(
        id=_temp_id(panel),
        row_id=row_id,
        role_id=role_id,
        label=label.strip(),
        emoji=emoji.strip() if emoji else None,
        description=description or None,
        style=style,
        mode=mode,
        group=group.strip().lower() if group and group.strip() else None,
        required_role_id=required_role_id,
    )
    return _map_row(panel, row_id, lambda r: replace(r, options=(*r.options, option)))

def _check_option_fields(
    label: str,
    emoji: str | None,
    description: str | None,
    style: str,
    mode: str,
    group: str | None,
) -> None:
    if not label.strip():
        raise ValueError("The label can't be empty.")
    if len(label.strip()) > MAX_LABEL:
        raise ValueError(f"Labels can be {MAX_LABEL} characters at most.")
    if description and len(description) > MAX_DESCRIPTION:
        raise ValueError(f"Descriptions can be {MAX_DESCRIPTION} characters at most.")
    if emoji and emoji.strip() and (error := emoji_error(emoji)):
        raise ValueError(error)
    if style not in STYLES:
        raise ValueError("Pick a button color.")
    if mode not in MODES:
        raise ValueError("Pick a mode.")
    if group and len(group.strip()) > MAX_GROUP:
        raise ValueError(f"Group names can be {MAX_GROUP} characters at most.")

def update_option(
    panel: Panel,
    option_id: int,
    *,
    label: str,
    emoji: str | None,
    description: str | None,
    style: str,
    mode: str,
) -> Panel:
    _check_option_fields(label, emoji, description, style, mode, None)
    return _map_option(
        panel,
        option_id,
        lambda o: replace(
            o,
            label=label.strip(),
            emoji=emoji.strip() if emoji and emoji.strip() else None,
            description=description or None,
            style=style,
            mode=mode,
        ),
    )

def set_rules(
    panel: Panel,
    option_id: int,
    *,
    group: str | None,
    required_role_id: int | None,
) -> Panel:
    if group and len(group.strip()) > MAX_GROUP:
        raise ValueError(f"Group names can be {MAX_GROUP} characters at most.")
    key = group.strip().lower() if group and group.strip() else None
    return _map_option(
        panel,
        option_id,
        lambda o: replace(o, group=key, required_role_id=required_role_id),
    )

def remove_option(panel: Panel, option_id: int) -> Panel:
    _find_option(panel, option_id)
    return _with_rows(
        panel,
        (replace(r, options=tuple(o for o in r.options if o.id != option_id)) for r in panel.rows),
    )
