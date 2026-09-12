import discord
from discord import app_commands
from discord.ext import commands

from ui import ExceptionUI, ResponseUI, ThinkingText


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


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DebugCog(bot))
