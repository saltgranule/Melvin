import datetime
import logging

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands, tasks

from ui import InfoUI

log = logging.getLogger(__name__)

midnight = datetime.time(hour=0, minute=0, second=0)


class StatsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot
        self.db_path = "data/stats.db"
        self.stats_loop.start()

    async def cog_unload(self) -> None:
        self.stats_loop.cancel()

    @tasks.loop(time=midnight)
    async def stats_loop(self):
        ...

    @stats_loop.before_loop
    async def before_daily_task(self):
        await self.bot.wait_until_ready()

    async def _ensure_db(self) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS stats (
                    ...
                )
            """)
            await conn.commit()

    async def cog_load(self) -> None:
        await self._ensure_db()

    @app_commands.command(
        name="stats",
        description="Display statistics about Melvin.",
    )
    async def stats(self, interaction: discord.Interaction) -> None:
        app = self.bot.application or await self.bot.application_info()

        user_installs = app.approximate_user_install_count or 0
        guild_installs = len(self.bot.guilds)

        view = InfoUI(
            title="Melvin Stats",
            subtitle=(
                f"**Guild Installs:** {guild_installs}\n"
                f"**User Installs:** {user_installs}\n"
                "..."
            ),
        )
        await interaction.response.send_message(view=view)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        ...

    @commands.Cog.listener()
    async def on_app_command_completion(
        self,
        interaction: discord.Interaction,
        command: app_commands.Command | app_commands.ContextMenu,
    ) -> None:
        ...


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StatsCog(bot))
