import base64
import random
import re
import urllib.parse
from collections.abc import Callable

import discord
from discord import app_commands
from discord.ext import commands

from ui import ErrorUI, GalleryWithItem, GatedUI, ResponseUI

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
    """A decode or encode failure with a message that's safe to show users."""


def _binary_decode(text: str) -> bytes:
    chunks = text.split()
    if not all(set(chunk) <= {"0", "1"} and len(chunk) == 8 for chunk in chunks):
        raise CodecError(
            "expected space-separated 8-bit groups of **0**s and **1**s",
        )
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
        raise CodecError(f"there's no Morse code for **{' '.join(unknown)}**")
    return " / ".join(
        " ".join(MORSE[char] for char in word) for word in upper.split()
    )


def _morse_decode(text: str) -> str:
    words = [word.split() for word in text.split("/")]
    unknown = sorted(
        {code for word in words for code in word if code not in MORSE_REVERSE},
    )
    if unknown:
        raise CodecError(f"**{' '.join(unknown)}** isn't valid Morse code")
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
            raise CodecError(f"**{token}** isn't a valid code point")
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
        lambda text: bytes.fromhex(text),
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
    app_commands.Choice(name=label, value=key)
    for key, (label, _, _) in FORMATS.items()
]


class ToolCog(
    commands.GroupCog,
    name="tool",
    description="Utility tools and helper commands.",
):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot

    async def _send_result(
        self,
        interaction: discord.Interaction,
        result: str,
        action: str,
        label: str,
    ) -> None:
        if not result:
            view = ErrorUI("**That didn't produce any text.**")
        elif len(result) > MAX_RESULT_LENGTH:
            view = ErrorUI(
                f"**The {label} result is too long to send ({len(result):,} characters).**",
            )
        else:
            view = ResponseUI(f"**{result}** was the {label} {action} result.")
        await interaction.edit_original_response(
            view=view,
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
        label, encoder, _ = FORMATS[fmt.value]

        try:
            result = encoder(text)
        except CodecError as e:
            await interaction.edit_original_response(
                view=ErrorUI(f"Couldn't encode that as {label}, {e}."),
            )
            return

        await self._send_result(interaction, result, "encoded", label)

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
        label, _, decoder = FORMATS[fmt.value]

        try:
            decoded = decoder(text)
            result = decoded.decode("utf-8") if isinstance(decoded, bytes) else decoded
        except UnicodeDecodeError:
            await interaction.edit_original_response(
                view=ErrorUI(
                    "**Decoded successfully, but the result is not valid text.**",
                ),
            )
            return
        except CodecError as e:
            await interaction.edit_original_response(
                view=ErrorUI(f"Not valid {label}, {e}."),
            )
            return
        except ValueError:
            # binascii and bytes.fromhex errors are too cryptic to show as-is
            await interaction.edit_original_response(
                view=ErrorUI(f"**That isn't valid {label}.**"),
            )
            return

        await self._send_result(interaction, result, "decoded", label)

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
