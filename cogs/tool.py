import base64
import binascii

import discord
from discord import app_commands
from discord.ext import commands

from ui import ErrorUI, GatedUI, ResponseUI


class ToolCog(
    commands.GroupCog,
    name="tool",
    description="Utility tools and helper commands.",
):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot

    base64 = app_commands.Group(name="base64", description="Utility encoding/decoding commands.")
    binary = app_commands.Group(name="binary", description="Utility encoding/decoding commands.")

    @base64.command(
        name="decode",
        description="Decode a Base64-encoded string.",
    )
    @app_commands.describe(text="The Base64 string to decode.")
    async def base64decode(self, interaction: discord.Interaction, text: str) -> None:
        await interaction.response.defer()

        try:
            decodedbyte = base64.b64decode(text, validate=True)
            decodedstr = decodedbyte.decode("utf-8")
        except binascii.Error as e:
            await interaction.edit_original_response(
                view=ErrorUI(f"Not a valid Base64 string: **{e}**."),
            )
            return
        except UnicodeDecodeError as e:
            await interaction.edit_original_response(
                view=ErrorUI(
                    f"Decoded successfully, but the result is not valid text: **{e}**.",
                ),
            )
            return

        view = ResponseUI(f"**{decodedstr}** was the decoded result.")
        await interaction.edit_original_response(view=view)

    @base64.command(
        name="encode",
        description="Encode a string as Base64.",
    )
    @app_commands.describe(text="The string to encode.")
    async def base64encode(self, interaction: discord.Interaction, text: str) -> None:
        await interaction.response.defer(ephemeral=False)

        try:
            encodedbyte = base64.b64encode(text.encode("utf-8"))
            encodedstr = encodedbyte.decode("utf-8")
        except Exception as e:
            await interaction.edit_original_response(
                view=ErrorUI(f"Something went wrong while encoding this: **{e}**."),
            )
            return

        view = ResponseUI(f"**{encodedstr}** was the encoded result.")
        await interaction.edit_original_response(view=view)

    @app_commands.command(name="speak", description="Speak through Melvin.")
    @app_commands.describe(
        text="The message text to send.",
        attachment="Optional attachment to include with the message.",
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def speak(
        self,
        interaction: discord.Interaction,
        text: str,
        attachment: discord.Attachment | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=False)
        view = ResponseUI(text)

        if attachment is not None:
            file = await attachment.to_file()
            view.container.add_item(
                discord.ui.MediaGallery(
                    discord.MediaGalleryItem(
                        media=f"attachment://{file.filename}",
                    ),
                ),
            )
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

    @binary.command(
        name="decode",
        description="Decode a binary string (e.g. 01001000 01101001) to text.",
    )
    @app_commands.describe(text="The binary string to decode, space-separated bytes.")
    async def binarydecode(self, interaction: discord.Interaction, text: str) -> None:
        await interaction.response.defer()

        chunks = text.split()
        if not all(set(chunk) <= {"0", "1"} and len(chunk) == 8 for chunk in chunks):
            await interaction.edit_original_response(
                view=ErrorUI("Not a valid binary string: expected space-separated 8-bit groups of **0**s and **1**s."),
            )
            return

        try:
            decodedbyte = bytes(int(chunk, 2) for chunk in chunks)
            decodedstr = decodedbyte.decode("utf-8")
        except UnicodeDecodeError as e:
            await interaction.edit_original_response(
                view=ErrorUI(
                    f"Decoded successfully, but the result is not valid text: **{e}**.",
                ),
            )
            return

        view = ResponseUI(f"**{decodedstr}** was the decoded result.")
        await interaction.edit_original_response(view=view)

    @binary.command(
        name="encode",
        description="Encode a string as binary.",
    )
    @app_commands.describe(text="The string to encode.")
    async def binaryencode(self, interaction: discord.Interaction, text: str) -> None:
        await interaction.response.defer(ephemeral=False)

        try:
            encodedstr = " ".join(f"{byte:08b}" for byte in text.encode("utf-8"))
        except Exception as e:
            await interaction.edit_original_response(
                view=ErrorUI(f"Something went wrong while encoding this: **{e}**."),
            )
            return

        view = ResponseUI(f"**{encodedstr}** was the encoded result.")
        await interaction.edit_original_response(view=view)

    @speak.error
    async def speak_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            view = GatedUI()

            if interaction.response.is_done():
                await interaction.followup.send(view=view, ephemeral=True)
            else:
                await interaction.response.send_message(view=view, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ToolCog(bot))
