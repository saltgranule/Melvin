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
    async def stats_loop(self) -> None:
        app = self.bot.application or await self.bot.application_info()
        user_installs = app.approximate_user_install_count or 0
        guild_installs = len(self.bot.guilds)

        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                "INSERT INTO daily_snapshots (guild_count, user_count) VALUES (?, ?)",
                (guild_installs, user_installs),
            )
            await conn.commit()

    @stats_loop.before_loop
    async def before_daily_task(self) -> None:
        await self.bot.wait_until_ready()

    async def _ensure_db(self) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS command_logs (
                    command_name TEXT,
                    user_id INTEGER,
                    guild_id INTEGER,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_snapshots (
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    guild_count INTEGER,
                    user_count INTEGER
                )
            """)
            await conn.commit()

            async with conn.execute("SELECT COUNT(*) FROM daily_snapshots") as cursor:
                row = await cursor.fetchone()
                if row and row[0] == 0:
                    app = self.bot.application or await self.bot.application_info()
                    await conn.execute(
                        "INSERT INTO daily_snapshots (guild_count, user_count) VALUES (?, ?)",
                        (len(self.bot.guilds), app.approximate_user_install_count or 0),
                    )
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
        daily_installs_delta = 0

        async with aiosqlite.connect(self.db_path) as conn:
            async with conn.execute("SELECT COUNT(*) FROM command_logs") as cursor:
                row = await cursor.fetchone()
                total_commands = row[0] if row else 0

            async with conn.execute(
                "SELECT COUNT(*) FROM command_logs WHERE timestamp >= datetime('now', '-1 day')",
            ) as cursor:
                row = await cursor.fetchone()
                daily_commands = row[0] if row else 0

            async with conn.execute(
                """SELECT guild_count, user_count FROM daily_snapshots
                   ORDER BY abs(strftime('%s', timestamp) - strftime('%s', datetime('now', '-1 day'))) ASC
                   LIMIT 1""",
            ) as cursor:
                snapshot = await cursor.fetchone()
                if snapshot:
                    past_guilds, past_users = snapshot[0], snapshot[1]
                    guild_growth = guild_installs - past_guilds
                    user_growth = user_installs - past_users
                    daily_installs_delta = guild_growth + user_growth

        view = InfoUI(
            title="Melvin Stats",
            subtitle=(
                f"**Guild Installs:** {guild_installs}\n"
                f"**User Installs:** {user_installs}\n"
                f"**Total Installs (Last 24h):** {daily_installs_delta}\n\n"
                f"**Total Installs (All-Time):** {guild_installs + user_installs}\n\n"
                f"**Commands Run (Last 24h):** {daily_commands}\n"
                f"**Commands Run (All-Time):** {total_commands}\n"
            ),
        )
        await interaction.response.send_message(view=view)

    @commands.Cog.listener()
    async def on_app_command_completion(
        self,
        interaction: discord.Interaction,
        command: app_commands.Command | app_commands.ContextMenu,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                "INSERT INTO command_logs (command_name, user_id, guild_id) VALUES (?, ?, ?)",
                (command.name, interaction.user.id, interaction.guild_id),
            )
            await conn.commit()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StatsCog(bot))
