import base64
import contextlib
import logging
import random
import re
import urllib.parse
from typing import TYPE_CHECKING

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from globals import BROWSER, THUMBS_DOWN_WHITE, THUMBS_UP_WHITE, WEBSITE_URL
from module_registry import Module
from ui import (
    ErrorUI,
    GalleryWithItem,
    GatedUI,
    Paginator,
    ResponseUI,
    SmallSeparator,
)

MODULE = Module(
    "tool",
    "Tools",
    "Encoding, decoding, speak, 8ball, Urban Dictionary, and Wikipedia.",
)

if TYPE_CHECKING:
    from collections.abc import Callable

log = logging.getLogger(__name__)

URBAN_API = "https://api.urbandictionary.com/v0/define"
URBAN_DEFINE = "https://www.urbandictionary.com/define.php?term="
# raw text is cut before links are added, so each page stays under discord's limit
URBAN_DEFINITION_LIMIT = 1200
URBAN_EXAMPLE_LIMIT = 600

WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"
WIKI_RANDOM = "https://en.wikipedia.org/api/rest_v1/page/random/summary"
WIKI_SEARCH = "https://en.wikipedia.org/w/rest.php/v1/search/title"
# metadata so we dont get throttled
WIKI_HEADERS = {"User-Agent": f"Melvin ({WEBSITE_URL})"}
WIKI_EXTRACT_LIMIT = 1500

EIGHTBALL = [
    "It is certain.",
    "Yes.",
    "Without a doubt.",
    "Yes, definitely.",
    "100%.",
    "Probably not.",
    "My reply is no.",
    "Very doubtful.",
    "No.",
]

# leaves room for the rest of the reply inside discord's 4000 character limit
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
    """An encode failure whose message is a full sentence that's safe to show users."""


def _binary_decode(text: str) -> bytes:
    chunks = text.split()
    if not all(set(chunk) <= {"0", "1"} and len(chunk) == 8 for chunk in chunks):
        raise ValueError
    return bytes(int(chunk, 2) for chunk in chunks)


def _base32_decode(text: str) -> bytes:
    cleaned = "".join(text.split()).upper()
    # padding is often left off when base32 is copied around
    cleaned += "=" * (-len(cleaned) % 8)
    return base64.b32decode(cleaned)


def _morse_encode(text: str) -> str:
    upper = text.upper()
    unknown = sorted(
        {char for char in upper if char not in MORSE and not char.isspace()},
    )
    if unknown:
        listed = unknown[0]
        if len(unknown) > 1:
            listed = ", ".join(unknown[:-1]) + " and " + unknown[-1]
        msg = f"{listed} can't be written in Morse."
        raise CodecError(msg)
    return " / ".join(" ".join(MORSE[char] for char in word) for word in upper.split())


def _morse_decode(text: str) -> str:
    words = [word.split() for word in text.split("/")]
    unknown = sorted(
        {code for word in words for code in word if code not in MORSE_REVERSE},
    )
    if unknown:
        raise ValueError
    return " ".join(
        "".join(MORSE_REVERSE[code] for code in word) for word in words if word
    )


def _unicode_decode(text: str) -> str:
    chars = []
    for token in filter(None, re.split(r"[\s,]+", text)):
        digits = token.upper().removeprefix("U+").removeprefix("0X")
        try:
            code_point = int(digits, 16)
        except ValueError:
            code_point = -1
        # surrogates can't be sent as text, so they're rejected with the invalid ones
        if not 0 <= code_point <= 0x10FFFF or 0xD800 <= code_point <= 0xDFFF:
            raise ValueError
        chars.append(chr(code_point))
    return "".join(chars)


# each format's encoder takes text, and its decoder returns text or utf-8 bytes
FORMATS: dict[
    str,
    tuple[str, Callable[[str], str], Callable[[str], str | bytes]],
] = {
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
    if selected is None:
        view = ResponseUI("**Pick a format to decode this message from.**")
    else:
        view = _decode_view(selected, text)

    select = discord.ui.Select(
        placeholder="Decode from...",
        options=[
            discord.SelectOption(label=label, value=key, default=key == selected)
            for key, (label, _, _) in FORMATS.items()
        ],
    )

    # each pick rebuilds the reply, keeping the thing so another format can be tried
    async def _callback(interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            view=_decode_menu_view(text, select.values[0]),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    select.callback = _callback
    view.container.add_item(discord.ui.ActionRow(select))
    return view


def _urban_links(text: str) -> str:
    # urban dictionary marks linked words with [brackets]
    return re.sub(
        r"\[([^\]]+)\]",
        lambda m: f"[{m[1]}]({URBAN_DEFINE}{urllib.parse.quote(m[1])})",
        text,
    )


def _urban_text(text: str, limit: int) -> str:
    text = text.replace("\r", "").strip()
    if len(text) > limit:
        text = text[:limit].rstrip() + "..."
        if text.rfind("[") > text.rfind("]"):
            text = text[: text.rfind("[")].rstrip() + "..."
    return _urban_links(text)


def _urban_page(entry: dict) -> str:
    lines = [_urban_text(entry["definition"], URBAN_DEFINITION_LIMIT)]
    example = entry.get("example", "").strip()
    if example:
        quoted = "\n".join(
            f"> {line}"
            for line in _urban_text(example, URBAN_EXAMPLE_LIMIT).split("\n")
        )
        lines.append(f"\n**Example**\n{quoted}")
    written = entry.get("written_on", "")[:10]
    lines.append(
        f"\n-# {THUMBS_UP_WHITE} {entry['thumbs_up']}  {THUMBS_DOWN_WHITE} "
        f"{entry['thumbs_down']} | by {entry['author'].strip()} on {written} | "
        f"{BROWSER} [Permalink]({entry['permalink']})",
    )
    return "\n".join(lines)


async def _wiki_fetch(
    url: str,
    params: dict[str, str] | None = None,
    timeout: float = 10,
) -> dict | None:
    async with (
        aiohttp.ClientSession(headers=WIKI_HEADERS) as session,
        session.get(
            url,
            params=params,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as response,
    ):
        if response.status == 404:
            return None
        response.raise_for_status()
        return await response.json()


async def _wiki_random() -> dict | None:
    for _ in range(3):
        page = await _wiki_fetch(WIKI_RANDOM)
        if page is not None and page.get("type") == "standard":
            return page
    return None


class WikiView(discord.ui.LayoutView):
    def __init__(self, page: dict, *, random_mode: bool) -> None:
        super().__init__(timeout=300)
        self.message: discord.Message | None = None
        self.random_mode = random_mode
        self.show(page)

    def show(self, page: dict) -> None:
        self.clear_items()

        heading = f"### {discord.utils.escape_markdown(page['title'])}"
        if page.get("description"):
            description = discord.utils.escape_markdown(page["description"])
            heading += f"\n-# **{description}**"

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
            discord.ui.Section(body, accessory=discord.ui.Thumbnail(thumbnail["source"]))
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
            page = await _wiki_random()
        except aiohttp.ClientError, TimeoutError:
            log.exception("Wikipedia random lookup failed")
            page = None

        if page is None:
            await interaction.followup.send(
                view=ErrorUI("**Melvin couldn't reach Wikipedia, try again later.**"),
                ephemeral=True,
            )
            return

        self.show(page)
        await interaction.edit_original_response(
            view=self,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def on_timeout(self) -> None:
        for item in self.walk_children():
            if isinstance(item, discord.ui.Button) and not item.url:
                item.disabled = True

        if self.message:
            with contextlib.suppress(discord.HTTPException):
                await self.message.edit(view=self)


class ToolCog(
    commands.GroupCog,
    name="tool",
    description="Utility tools and helper commands.",
):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot
        self.decode_menu = app_commands.ContextMenu(
            name="Decode",
            callback=self.decode_message,
        )
        self.bot.tree.add_command(self.decode_menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(
            self.decode_menu.name,
            type=self.decode_menu.type,
        )

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
            allowed_mentions=discord.AllowedMentions.none(),
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
            allowed_mentions=discord.AllowedMentions.none(),
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
            allowed_mentions=discord.AllowedMentions.none(),
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

        file = await attachment.to_file() if attachment is not None else None
        mentions = discord.AllowedMentions.none()

        if not containerized:
            # Raw text, with the attachment as a regular file
            if file is not None:
                await interaction.followup.send(
                    text,
                    file=file,
                    allowed_mentions=mentions,
                )
            else:
                await interaction.followup.send(text, allowed_mentions=mentions)
            return

        view = discord.ui.LayoutView()
        container = discord.ui.Container(discord.ui.TextDisplay(text))
        view.add_item(container)

        if file is not None:
            container.add_item(GalleryWithItem(f"attachment://{file.filename}"))
            await interaction.followup.send(
                view=view,
                file=file,
                allowed_mentions=mentions,
            )
        else:
            await interaction.followup.send(view=view, allowed_mentions=mentions)

    @app_commands.command(
        name="urban",
        description="Look up a word on Urban Dictionary.",
    )
    @app_commands.describe(word="The word or phrase to look up.")
    async def urban(self, interaction: discord.Interaction, word: str) -> None:
        await interaction.response.defer()

        try:
            async with (
                aiohttp.ClientSession() as session,
                session.get(
                    URBAN_API,
                    params={"term": word},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response,
            ):
                response.raise_for_status()
                data = await response.json()
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

        title_word = entries[0]["word"].replace("`", "")
        view = Paginator(
            f"### {title_word}",
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
                url=URBAN_DEFINE + urllib.parse.quote(entries[0]["word"]),
            ),
        )
        view.message = await interaction.followup.send(
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
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
            # discord stops waiting for suggestions after three seconds
            data = await _wiki_fetch(
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
        page = None
        try:
            if query:
                page = await _wiki_fetch(
                    WIKI_SUMMARY + urllib.parse.quote(query, safe=""),
                )
            else:
                page = await _wiki_random()
        except aiohttp.ClientError, TimeoutError:
            log.exception("Wikipedia lookup failed")
            failed = True
        else:
            # a random lookup only comes back empty when every try missed
            failed = page is None and not query

        if failed:
            await interaction.followup.send(
                view=ErrorUI("**Melvin couldn't reach Wikipedia, try again later.**"),
                ephemeral=True,
            )
            return

        if page is None or page.get("type") == "mainpage":
            await interaction.followup.send(
                view=ErrorUI(
                    f"**No Wikipedia article found for `{query.replace('`', '')}`.**",
                ),
                ephemeral=True,
            )
            return

        if page.get("type") == "disambiguation":
            await interaction.followup.send(
                view=ErrorUI(
                    f"**`{page['title'].replace('`', '')}` could mean a few "
                    "different things, try something more specific or pick one "
                    "of the suggestions.**",
                ),
                ephemeral=True,
            )
            return

        view = WikiView(page, random_mode=not query)
        view.message = await interaction.followup.send(
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
            wait=True,
        )

    @app_commands.command(name="8ball", description="game of fate")
    @app_commands.describe(prompt="the prompt for the 8ball")
    async def eightball(self, interaction: discord.Interaction, prompt: str) -> None:
        await interaction.response.defer(ephemeral=False)
        answer = random.choice(EIGHTBALL)
        view = ResponseUI(f"**{prompt}**\n<:8ball:1548098650482413608>**{answer}**")
        await interaction.followup.send(
            view=view,
            allowed_mentions=discord.AllowedMentions(everyone=False),
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ToolCog(bot))
