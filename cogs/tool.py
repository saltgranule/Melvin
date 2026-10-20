import base64
import contextlib
import logging
import random
import re
import time
import urllib.parse
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import aiohttp
import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands, tasks

import module_settings
from globals import BROWSER, DATA_DIR, THUMBS_DOWN_WHITE, THUMBS_UP_WHITE, WEBSITE_URL
from helpers import durations
from module_registry import Module
from ui import (
    ErrorUI,
    GalleryWithItem,
    GatedUI,
    InfoUI,
    Paginator,
    PositiveUI,
    ResponseUI,
    SmallSeparator,
)

if TYPE_CHECKING:
    from collections.abc import Callable

MODULE = Module(
    "tool",
    "Tools",
    "Encoding, decoding, speak, 8ball, Urban Dictionary, Wikipedia, and reminders.",
)

log = logging.getLogger(__name__)

NO_MENTIONS = discord.AllowedMentions.none()

REMINDER_CHECK_SECONDS = 15
REMINDER_MIN_SECONDS = 60
REMINDER_MAX_SECONDS = 365 * 86400
REMINDER_LIMIT = 25
REMINDER_MESSAGE_LENGTH = 300
REMINDER_PREVIEW_LENGTH = 60

URBAN_API = "https://api.urbandictionary.com/v0/define"
URBAN_DEFINE = "https://www.urbandictionary.com/define.php?term="
URBAN_DEFINITION_LIMIT = 1200
URBAN_EXAMPLE_LIMIT = 600
URBAN_LINK = re.compile(r"\[([^\]]+)\]")

WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"
WIKI_RANDOM = "https://en.wikipedia.org/api/rest_v1/page/random/summary"
WIKI_SEARCH = "https://en.wikipedia.org/w/rest.php/v1/search/title"
WIKI_HEADERS = {"User-Agent": f"Melvin ({WEBSITE_URL})"}
WIKI_EXTRACT_LIMIT = 1500
WIKI_UNREACHABLE = "**Melvin couldn't reach Wikipedia, try again later.**"

EIGHTBALL = (
    "It is certain.",
    "Yes.",
    "Without a doubt.",
    "Yes, definitely.",
    "100%.",
    "Probably not.",
    "My reply is no.",
    "Very doubtful.",
    "No.",
)

MAX_RESULT_LENGTH = 3900

MORSE = {
    "A": ".-", "B": "-...", "C": "-.-.", "D": "-..", "E": ".", "F": "..-.",
    "G": "--.", "H": "....", "I": "..", "J": ".---", "K": "-.-", "L": ".-..",
    "M": "--", "N": "-.", "O": "---", "P": ".--.", "Q": "--.-", "R": ".-.",
    "S": "...", "T": "-", "U": "..-", "V": "...-", "W": ".--", "X": "-..-",
    "Y": "-.--", "Z": "--..",
    "0": "-----", "1": ".----", "2": "..---", "3": "...--", "4": "....-",
    "5": ".....", "6": "-....", "7": "--...", "8": "---..", "9": "----.",
    ".": ".-.-.-", ",": "--..--", "?": "..--..", "'": ".----.", "!": "-.-.--",
    "/": "-..-.", "(": "-.--.", ")": "-.--.-", "&": ".-...", ":": "---...",
    ";": "-.-.-.", "=": "-...-", "+": ".-.-.", "-": "-....-", "_": "..--.-",
    '"': ".-..-.", "$": "...-..-", "@": ".--.-.",
}  # fmt: skip
MORSE_REVERSE = {code: char for char, code in MORSE.items()}


class CodecError(ValueError):
    pass


def _binary_decode(text: str) -> bytes:
    chunks = text.split()
    if not all(len(chunk) == 8 and set(chunk) <= {"0", "1"} for chunk in chunks):
        raise ValueError
    return bytes(int(chunk, 2) for chunk in chunks)


def _base32_decode(text: str) -> bytes:
    cleaned = "".join(text.split()).upper()
    return base64.b32decode(cleaned + "=" * (-len(cleaned) % 8))


def _morse_encode(text: str) -> str:
    upper = text.upper()
    unknown = sorted(
        {char for char in upper if char not in MORSE and not char.isspace()},
    )
    if unknown:
        listed = (
            unknown[0]
            if len(unknown) == 1
            else ", ".join(unknown[:-1]) + " and " + unknown[-1]
        )
        msg = f"{listed} can't be written in Morse."
        raise CodecError(msg)
    return " / ".join(" ".join(MORSE[char] for char in word) for word in upper.split())


def _morse_decode(text: str) -> str:
    words = [word.split() for word in text.split("/")]
    try:
        return " ".join(
            "".join(MORSE_REVERSE[code] for code in word) for word in words if word
        )
    except KeyError:
        raise ValueError from None


def _unicode_decode(text: str) -> str:
    chars = []
    for token in filter(None, re.split(r"[\s,]+", text)):
        digits = token.upper().removeprefix("U+").removeprefix("0X")
        try:
            code_point = int(digits, 16)
        except ValueError:
            code_point = -1
        if not 0 <= code_point <= 0x10FFFF or 0xD800 <= code_point <= 0xDFFF:
            raise ValueError
        chars.append(chr(code_point))
    return "".join(chars)


FORMATS: dict[str, tuple[str, Callable[[str], str], Callable[[str], str | bytes]]] = {
    "base64": (
        "Base64",
        lambda text: base64.b64encode(text.encode("utf-8")).decode("ascii"),
        lambda text: base64.b64decode(text, validate=True),
    ),
    "binary": (
        "Binary",
        lambda text: " ".join(f"{byte:08b}" for byte in text.encode("utf-8")),
        _binary_decode,
    ),
    "hex": (
        "Hex",
        lambda text: text.encode("utf-8").hex(" "),
        bytes.fromhex,
    ),
    "url": (
        "URL",
        lambda text: urllib.parse.quote(text, safe=""),
        lambda text: urllib.parse.unquote(text, errors="strict"),
    ),
    "base32": (
        "Base32",
        lambda text: base64.b32encode(text.encode("utf-8")).decode("ascii"),
        _base32_decode,
    ),
    "morse": ("Morse", _morse_encode, _morse_decode),
    "unicode": (
        "Unicode",
        lambda text: " ".join(f"U+{ord(char):04X}" for char in text),
        _unicode_decode,
    ),
}
FORMAT_CHOICES = [
    app_commands.Choice(name=label, value=key) for key, (label, _, _) in FORMATS.items()
]


def _result_view(result: str, action: str, label: str) -> discord.ui.LayoutView:
    if not result:
        return ErrorUI("**There's nothing to show.**")
    if len(result) > MAX_RESULT_LENGTH:
        return ErrorUI("**That result is too long to send.**")
    return ResponseUI(f"**{result}** was the {label} {action} result.")


def _encode_view(key: str, text: str) -> discord.ui.LayoutView:
    label, encoder, _ = FORMATS[key]
    try:
        result = encoder(text)
    except CodecError as e:
        return ErrorUI(f"**{e}**")
    return _result_view(result, "encoded", label)


def _decode_view(key: str, text: str) -> discord.ui.LayoutView:
    label, _, decoder = FORMATS[key]
    try:
        decoded = decoder(text)
        result = decoded.decode("utf-8") if isinstance(decoded, bytes) else decoded
    except UnicodeDecodeError:
        return ErrorUI("**That decodes to something that isn't text.**")
    except ValueError:
        return ErrorUI(f"**That doesn't look like {label}.**")
    return _result_view(result, "decoded", label)


def _decode_menu_view(text: str, selected: str | None = None) -> discord.ui.LayoutView:
    view = (
        ResponseUI("**Pick a format to decode this message from.**")
        if selected is None
        else _decode_view(selected, text)
    )
    select = discord.ui.Select(
        placeholder="Decode from...",
        options=[
            discord.SelectOption(label=label, value=key, default=key == selected)
            for key, (label, _, _) in FORMATS.items()
        ],
    )

    async def _callback(interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            view=_decode_menu_view(text, select.values[0]),
            allowed_mentions=NO_MENTIONS,
        )

    select.callback = _callback
    view.container.add_item(discord.ui.ActionRow(select))
    return view


def _urban_text(text: str, limit: int) -> str:
    text = text.replace("\r", "").strip()
    if len(text) > limit:
        text = text[:limit].rstrip() + "..."
        if text.rfind("[") > text.rfind("]"):
            text = text[: text.rfind("[")].rstrip() + "..."
    return URBAN_LINK.sub(
        lambda m: f"[{m[1]}]({URBAN_DEFINE}{urllib.parse.quote(m[1])})",
        text,
    )


def _urban_page(entry: dict) -> str:
    lines = [_urban_text(entry["definition"], URBAN_DEFINITION_LIMIT)]
    if entry.get("example", "").strip():
        quoted = "\n".join(
            f"> {line}"
            for line in _urban_text(entry["example"], URBAN_EXAMPLE_LIMIT).split("\n")
        )
        lines.append(f"\n**Example**\n{quoted}")
    lines.append(
        f"\n-# {THUMBS_UP_WHITE} {entry['thumbs_up']}  {THUMBS_DOWN_WHITE} "
        f"{entry['thumbs_down']} | by {entry['author'].strip()} on {entry.get('written_on', '')[:10]} | "
        f"{BROWSER} [Permalink]({entry['permalink']})",
    )
    return "\n".join(lines)


async def _get_json(
    session: aiohttp.ClientSession,
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 10,
    missing_ok: bool = False,
) -> dict | None:
    async with session.get(
        url,
        params=params,
        headers=headers,
        timeout=aiohttp.ClientTimeout(total=timeout),
    ) as response:
        if missing_ok and response.status == 404:
            return None
        response.raise_for_status()
        return await response.json()


async def _wiki_fetch(
    session: aiohttp.ClientSession,
    url: str,
    params: dict[str, str] | None = None,
    timeout: float = 10,
) -> dict | None:
    return await _get_json(
        session,
        url,
        params=params,
        headers=WIKI_HEADERS,
        timeout=timeout,
        missing_ok=True,
    )


async def _wiki_random(session: aiohttp.ClientSession) -> dict | None:
    for _ in range(3):
        page = await _wiki_fetch(session, WIKI_RANDOM)
        if page is not None and page.get("type") == "standard":
            return page
    return None


class WikiView(discord.ui.LayoutView):
    def __init__(
        self,
        page: dict,
        session: aiohttp.ClientSession,
        *,
        random_mode: bool,
    ) -> None:
        super().__init__(timeout=300)
        self.message: discord.Message | None = None
        self.session = session
        self.random_mode = random_mode
        self.show(page)

    def show(self, page: dict) -> None:
        self.clear_items()

        heading = f"### {discord.utils.escape_markdown(page['title'])}"
        if page.get("description"):
            heading += f"\n-# **{discord.utils.escape_markdown(page['description'])}**"

        extract = page.get("extract", "").strip()
        if len(extract) > WIKI_EXTRACT_LIMIT:
            extract = extract[:WIKI_EXTRACT_LIMIT].rstrip() + "..."
        body = discord.ui.TextDisplay(
            discord.utils.escape_markdown(extract) or "No summary available.",
        )
        thumbnail = page.get("thumbnail")

        container = discord.ui.Container(
            discord.ui.Section(
                heading,
                accessory=discord.ui.Button(
                    label="Wikipedia",
                    emoji=BROWSER,
                    style=discord.ButtonStyle.link,
                    url=page["content_urls"]["desktop"]["page"],
                ),
            ),
            SmallSeparator(),
            discord.ui.Section(
                body,
                accessory=discord.ui.Thumbnail(thumbnail["source"]),
            )
            if thumbnail
            else body,
            SmallSeparator(),
        )

        if self.random_mode:
            another = discord.ui.Button(
                label="Another",
                style=discord.ButtonStyle.secondary,
            )
            another.callback = self.another
            container.add_item(discord.ui.ActionRow(another))

        self.add_item(container)

    async def another(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        try:
            page = await _wiki_random(self.session)
        except aiohttp.ClientError, TimeoutError:
            log.exception("Wikipedia random lookup failed")
            page = None

        if page is None:
            await interaction.followup.send(
                view=ErrorUI(WIKI_UNREACHABLE),
                ephemeral=True,
            )
            return

        self.show(page)
        await interaction.edit_original_response(
            view=self,
            allowed_mentions=NO_MENTIONS,
        )

    async def on_timeout(self) -> None:
        for item in self.walk_children():
            if isinstance(item, discord.ui.Button) and not item.url:
                item.disabled = True

        if self.message:
            with contextlib.suppress(discord.HTTPException):
                await self.message.edit(view=self)


def _preview(text: str) -> str:
    return (
        text
        if len(text) <= REMINDER_PREVIEW_LENGTH
        else text[: REMINDER_PREVIEW_LENGTH - 3] + "..."
    )


class ToolCog(
    commands.GroupCog,
    name="tool",
    description="Utility tools and helper commands.",
):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot
        self.session: aiohttp.ClientSession | None = None
        self.db_path = DATA_DIR / "reminders.db"
        self.decode_menu = app_commands.ContextMenu(
            name="Decode",
            callback=self.decode_message,
        )
        self.bot.tree.add_command(self.decode_menu)

    async def cog_load(self) -> None:
        self.session = aiohttp.ClientSession()
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER,
                    channel_id INTEGER NOT NULL,
                    message TEXT NOT NULL,
                    due_at REAL NOT NULL
                )
                """,
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS reminders_due ON reminders (due_at)",
            )
            await conn.commit()
        self.check_reminders.start()

    async def cog_unload(self) -> None:
        self.check_reminders.cancel()
        self.bot.tree.remove_command(self.decode_menu.name, type=self.decode_menu.type)
        if self.session is not None:
            await self.session.close()

    async def decode_message(
        self,
        interaction: discord.Interaction,
        message: discord.Message,
    ) -> None:
        if not message.content:
            await interaction.response.send_message(
                view=ErrorUI("**That message has no text to decode.**"),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            view=_decode_menu_view(message.content),
            ephemeral=True,
            allowed_mentions=NO_MENTIONS,
        )

    @app_commands.command(
        name="encode",
        description="Encode text into another format.",
    )
    @app_commands.rename(fmt="format")
    @app_commands.describe(fmt="The format to encode into.", text="The text to encode.")
    @app_commands.choices(fmt=FORMAT_CHOICES)
    async def encode(
        self,
        interaction: discord.Interaction,
        fmt: app_commands.Choice[str],
        text: str,
    ) -> None:
        await interaction.response.defer()
        await interaction.edit_original_response(
            view=_encode_view(fmt.value, text),
            allowed_mentions=NO_MENTIONS,
        )

    @app_commands.command(
        name="decode",
        description="Decode text from another format.",
    )
    @app_commands.rename(fmt="format")
    @app_commands.describe(fmt="The format to decode from.", text="The text to decode.")
    @app_commands.choices(fmt=FORMAT_CHOICES)
    async def decode(
        self,
        interaction: discord.Interaction,
        fmt: app_commands.Choice[str],
        text: str,
    ) -> None:
        await interaction.response.defer()
        await interaction.edit_original_response(
            view=_decode_view(fmt.value, text),
            allowed_mentions=NO_MENTIONS,
        )

    @app_commands.command(name="speak", description="Speak through Melvin.")
    @app_commands.describe(
        text="The message text to send.",
        attachment="Optional attachment to include with the message.",
        containerized="Send the message in a container. Defaults to true.",
    )
    async def speak(
        self,
        interaction: discord.Interaction,
        text: str,
        attachment: discord.Attachment | None = None,
        *,
        containerized: bool = True,
    ) -> None:
        await interaction.response.defer(ephemeral=False)

        if (
            isinstance(interaction.user, discord.Member)
            and not interaction.user.guild_permissions.manage_messages
        ):
            await interaction.followup.send(view=GatedUI(), ephemeral=True)
            return

        kwargs = {"allowed_mentions": NO_MENTIONS}
        if attachment is not None:
            kwargs["file"] = await attachment.to_file()

        if not containerized:
            await interaction.followup.send(text, **kwargs)
            return

        container = discord.ui.Container(discord.ui.TextDisplay(text))
        if attachment is not None:
            container.add_item(
                GalleryWithItem(f"attachment://{kwargs['file'].filename}"),
            )
        view = discord.ui.LayoutView()
        view.add_item(container)
        await interaction.followup.send(view=view, **kwargs)

    @app_commands.command(
        name="urban",
        description="Look up a word on Urban Dictionary.",
    )
    @app_commands.describe(word="The word or phrase to look up.")
    async def urban(self, interaction: discord.Interaction, word: str) -> None:
        await interaction.response.defer()

        try:
            data = await _get_json(self.session, URBAN_API, params={"term": word})
        except aiohttp.ClientError, TimeoutError:
            log.exception("Urban Dictionary lookup failed")
            await interaction.followup.send(
                view=ErrorUI(
                    "**Melvin couldn't reach the urban dictionary API, try again later**",
                ),
                ephemeral=True,
            )
            return

        entries = data.get("list", [])
        if not entries:
            await interaction.followup.send(
                view=ErrorUI(
                    f"**No definitions found for `{word.replace('`', '')}`.**",
                ),
                ephemeral=True,
            )
            return

        word = entries[0]["word"]
        view = Paginator(
            f"### {word.replace('`', '')}",
            [_urban_page(entry) for entry in entries],
            data_name="Definitions",
            per_page=1,
            container=True,
            timeout=300,
        )
        view.set_title_button(
            discord.ui.Button(
                label="Urban Dictionary",
                emoji=BROWSER,
                style=discord.ButtonStyle.link,
                url=URBAN_DEFINE + urllib.parse.quote(word),
            ),
        )
        view.message = await interaction.followup.send(
            view=view,
            allowed_mentions=NO_MENTIONS,
            wait=True,
        )

    async def wiki_autocomplete(
        self,
        _interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        if not current.strip():
            return []
        try:
            data = await _wiki_fetch(
                self.session,
                WIKI_SEARCH,
                params={"q": current, "limit": "25"},
                timeout=2.5,
            )
        except aiohttp.ClientError, TimeoutError:
            return []
        return [
            app_commands.Choice(name=page["title"], value=page["title"])
            for page in (data or {}).get("pages", [])
            if len(page["title"]) <= 100
        ]

    @app_commands.command(
        name="wiki",
        description="Look up a Wikipedia article, or get a random one.",
    )
    @app_commands.describe(
        query="The article to look up. Leave it empty for a random article.",
    )
    @app_commands.autocomplete(query=wiki_autocomplete)
    async def wiki(
        self,
        interaction: discord.Interaction,
        query: str | None = None,
    ) -> None:
        await interaction.response.defer()

        query = (query or "").strip()
        try:
            if query:
                page = await _wiki_fetch(
                    self.session,
                    WIKI_SUMMARY + urllib.parse.quote(query, safe=""),
                )
            else:
                page = await _wiki_random(self.session)
        except aiohttp.ClientError, TimeoutError:
            log.exception("Wikipedia lookup failed")
            page, failed = None, True
        else:
            failed = page is None and not query

        if failed:
            error = WIKI_UNREACHABLE
        elif page is None or page.get("type") == "mainpage":
            error = f"**No Wikipedia article found for `{query.replace('`', '')}`.**"
        elif page.get("type") == "disambiguation":
            error = (
                f"**`{page['title'].replace('`', '')}` could mean a few "
                "different things, try something more specific or pick one "
                "of the suggestions.**"
            )
        else:
            error = None
        if error:
            await interaction.followup.send(view=ErrorUI(error), ephemeral=True)
            return

        view = WikiView(page, self.session, random_mode=not query)
        view.message = await interaction.followup.send(
            view=view,
            allowed_mentions=NO_MENTIONS,
            wait=True,
        )

    @app_commands.command(name="8ball", description="Game of fate")
    @app_commands.describe(prompt="The prompt for the 8ball")
    async def eightball(self, interaction: discord.Interaction, prompt: str) -> None:
        await interaction.response.defer(ephemeral=False)
        answer = random.choice(EIGHTBALL)
        await interaction.followup.send(
            view=ResponseUI(f"**{prompt}**\n<:8ball:1548098650482413608>**{answer}**"),
            allowed_mentions=NO_MENTIONS,
        )

    @app_commands.command(name="remind", description="Set a reminder.")
    @app_commands.describe(
        duration="How long from now, like 10m, 2h, or 3d.",
        message="What to remind you about.",
    )
    async def remind(
        self,
        interaction: discord.Interaction,
        duration: str,
        message: app_commands.Range[str, 1, REMINDER_MESSAGE_LENGTH],
    ) -> None:
        seconds = durations.parse_duration(duration.strip())
        if seconds is None or not (
            REMINDER_MIN_SECONDS <= seconds <= REMINDER_MAX_SECONDS
        ):
            await interaction.response.send_message(
                view=ErrorUI(
                    "**Use a time from 1 minute to 365 days, like `10m`, `2h`, or `3d`.**",
                ),
                ephemeral=True,
            )
            return

        due_at = time.time() + seconds
        async with aiosqlite.connect(self.db_path) as conn:
            async with conn.execute(
                "SELECT COUNT(*) FROM reminders WHERE user_id = ?",
                (interaction.user.id,),
            ) as cursor:
                (count,) = await cursor.fetchone()
            if count >= REMINDER_LIMIT:
                await interaction.response.send_message(
                    view=ErrorUI(
                        f"**You can have up to {REMINDER_LIMIT} reminders at once. "
                        "Use /tool forget to remove one.**",
                    ),
                    ephemeral=True,
                )
                return

            async with conn.execute(
                """
                INSERT INTO reminders (user_id, guild_id, channel_id, message, due_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    interaction.user.id,
                    interaction.guild_id,
                    interaction.channel_id,
                    message,
                    due_at,
                ),
            ) as cursor:
                reminder_id = cursor.lastrowid
            await conn.commit()

        due = discord.utils.format_dt(datetime.fromtimestamp(due_at, UTC), style="R")
        await interaction.response.send_message(
            view=PositiveUI(
                title=f"Reminder #{reminder_id} set",
                subtitle=f"**Due** {due}",
            ),
            ephemeral=True,
        )

    @app_commands.command(name="reminders", description="List your reminders.")
    async def reminders(self, interaction: discord.Interaction) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            async with conn.execute(
                "SELECT id, due_at, message FROM reminders WHERE user_id = ? ORDER BY due_at",
                (interaction.user.id,),
            ) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            await interaction.response.send_message(
                view=InfoUI(
                    title="Reminders", subtitle="**You have no reminders set.**"
                ),
                ephemeral=True,
            )
            return

        lines = [
            f"**#{reminder_id}** {discord.utils.format_dt(datetime.fromtimestamp(due_at, UTC), style='R')} | "
            f"{discord.utils.escape_markdown(_preview(message))}"
            for reminder_id, due_at, message in rows
        ]
        await interaction.response.send_message(
            view=InfoUI(title="Reminders", subtitle="\n".join(lines)),
            ephemeral=True,
        )

    @app_commands.command(name="forget", description="Cancel one of your reminders.")
    @app_commands.describe(reminder_id="The reminder number from /tool reminders.")
    async def forget(
        self,
        interaction: discord.Interaction,
        reminder_id: app_commands.Range[int, 1],
    ) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            async with conn.execute(
                "DELETE FROM reminders WHERE id = ? AND user_id = ?",
                (reminder_id, interaction.user.id),
            ) as cursor:
                deleted = cursor.rowcount
            await conn.commit()

        if not deleted:
            await interaction.response.send_message(
                view=ErrorUI(f"**You have no reminder #{reminder_id}.**"),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            view=PositiveUI(
                title=f"Reminder #{reminder_id} cancelled", subtitle="**Removed.**"
            ),
            ephemeral=True,
        )

    @tasks.loop(seconds=REMINDER_CHECK_SECONDS)
    async def check_reminders(self) -> None:
        try:
            await self._send_due_reminders()
        except Exception:
            log.exception("failed to send due reminders")

    @check_reminders.before_loop
    async def _wait_for_bot(self) -> None:
        await self.bot.wait_until_ready()

    async def _send_due_reminders(self) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            async with conn.execute(
                """
                SELECT id, user_id, guild_id, channel_id, message
                FROM reminders
                WHERE due_at <= ?
                ORDER BY due_at
                """,
                (time.time(),),
            ) as cursor:
                due = await cursor.fetchall()

            for reminder_id, user_id, guild_id, channel_id, message in due:
                if guild_id is not None and not await module_settings.is_enabled(
                    guild_id,
                    "tool",
                ):
                    continue
                try:
                    await self._deliver(channel_id, user_id, message)
                except discord.HTTPException:
                    log.exception("failed to deliver reminder %s", reminder_id)
                    continue
                await conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
            await conn.commit()

    async def _deliver(self, channel_id: int, user_id: int, message: str) -> None:
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except discord.NotFound, discord.Forbidden:
                return
        if not isinstance(channel, discord.abc.Messageable):
            return

        view = discord.ui.LayoutView()
        view.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"### Reminder\n<@{user_id}> {message}"),
            ),
        )
        try:
            await channel.send(
                view=view,
                allowed_mentions=discord.AllowedMentions(
                    everyone=False,
                    roles=False,
                    users=True,
                ),
            )
        except discord.Forbidden:
            return


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ToolCog(bot))
