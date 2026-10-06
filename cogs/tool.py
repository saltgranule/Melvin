import base64
import random
import re
import urllib.parse
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from ui import ErrorUI, GalleryWithItem, GatedUI, ResponseUI

if TYPE_CHECKING:
    from collections.abc import Callable

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


class ToolCog(
    commands.GroupCog,
    name="tool",
    description="Utility tools and helper commands.",
):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot
        # context menus can't be in a group, so this one goes on the tree directly
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
    )
    async def speak(
        self,
        interaction: discord.Interaction,
        text: str,
        attachment: discord.Attachment | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=False)
        view = ResponseUI(text)

        if (
            isinstance(interaction.user, discord.Member)
            and not interaction.user.guild_permissions.manage_messages
        ):
            await interaction.followup.send(view=GatedUI(), ephemeral=True)
            return

        if attachment is not None:
            file = await attachment.to_file()
            view.container.add_item(GalleryWithItem(f"attachment://{file.filename}"))
            await interaction.followup.send(
                view=view,
                file=file,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        else:
            await interaction.followup.send(
                view=view,
                allowed_mentions=discord.AllowedMentions.none(),
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
