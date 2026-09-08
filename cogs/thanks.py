import discord
import asyncio
import aiosqlite
from discord import app_commands
from discord.ext import commands
from ui import InfoUI, PositiveUI

rate_int = 1
rate_time = 60.0
# rate_int - how many times a user can trigger the count event, rate_time - the time before the rate_int limit resets, so 1 thank every 60 seconds.

class ThanksCog(
    commands.GroupCog,
    name="Thanks",
    description="Thank you count tracking.",
):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot
        self.db_path = "data/thanks.db"




async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ThanksCog(bot))
