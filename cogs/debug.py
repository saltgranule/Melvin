import discord
from discord import app_commands
from discord.ext import commands

from globals import INVITE_URL, MELVIN_BANNER, MELVIN_EMOJI
from ui import ExceptionUI, ResponseUI, SmallSeparator, ThinkingText


# AdUI
class AdUI(discord.ui.LayoutView):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot
        self.text_display = discord.ui.TextDisplay(
            f"# {MELVIN_EMOJI} Melvin\nYAGPDB written in Python under the discord.py framework, built by a small group, still learning Python. Features user and guild install commands, welcoming configuration, CV2 messages over legacy embeds, and more bleeding edge features. Melvin is open source, and open to contributions, so if you want to contribute, feel free. **[GitHub](https://github.com/saltgranule/Melvin)**\n\n**Currently in {len(self.bot.guilds)} guilds.**",
        )
        media_gallery = discord.ui.MediaGallery(
            discord.MediaGalleryItem(media=f"{MELVIN_BANNER}"),
        )
        banner_container = discord.ui.Container(media_gallery)
        adbutton = discord.ui.Button(
            label="Support Server",
            style=discord.ButtonStyle.link,
            url=f"{INVITE_URL}",
        )
        addbutton = discord.ui.Button(
            label="Add Melvin",
            style=discord.ButtonStyle.link,
            url="https://discord.com/oauth2/authorize?client_id=1468362201197973756",
        )
        gitbutton = discord.ui.Button(
            label="GitHub",
            style=discord.ButtonStyle.link,
            url="https://github.com/saltgranule/Melvin",
        )
        action_row = discord.ui.ActionRow(adbutton, addbutton, gitbutton)
        content_container = discord.ui.Container(
            self.text_display,
            SmallSeparator(),
            action_row,
        )
        self.container = content_container
        self.add_item(banner_container)
        self.add_item(content_container)


class DebugCog(
    commands.GroupCog,
    name="debug",
    description="Commands for debugging purposes.",
):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot

    @app_commands.command(name="think", description="Send raw ResponseUI class.")
    async def think(self, interaction: discord.Interaction) -> None:
        view = ResponseUI(ThinkingText().content)
        await interaction.response.send_message(view=view)

    @app_commands.command(name="error", description="Send raw ErrorUI class.")
    async def error(self, interaction: discord.Interaction) -> None:
        view = ExceptionUI()
        await interaction.response.send_message(view=view)

    @app_commands.command(name="ad", description="Send advertisement.")
    async def ad(self, interaction: discord.Interaction) -> None:
        view = AdUI(self.bot)
        await interaction.response.send_message(view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DebugCog(bot))
