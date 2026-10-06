import logging
from collections import Counter

import discord
from discord.ext import commands, tasks

import module_settings
import server_stats

log = logging.getLogger(__name__)


# a plain cog rather than a GroupCog, since it has no commands, an empty group would
# show up in discord as a command that does nothing. it's still the serverstats module
class ServerStatsCog(
    commands.Cog,
    name="serverstats",
    description="Message, voice, and member totals for this server.",
):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot
        # messages are counted here and written once a minute, not once per message
        self._messages: Counter[int] = Counter()
        self._pruned_hour = 0

    async def cog_load(self) -> None:
        await server_stats.init_db()
        self.collect.start()

    async def cog_unload(self) -> None:
        self.collect.cancel()
        await self._flush()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        self._messages[message.guild.id] += 1

    def _voice_members(self, guild: discord.Guild) -> int:
        # people in voice right now, leaving out bots and the afk channel
        channels = [*guild.voice_channels, *guild.stage_channels]
        return sum(
            1
            for channel in channels
            if channel != guild.afk_channel
            for member in channel.members
            if not member.bot
        )

    async def _flush(self, *, with_voice: bool = False) -> None:
        hour = server_stats.hour_start()
        messages, self._messages = self._messages, Counter()

        rows = []
        for guild in self.bot.guilds:
            # guilds that turned the module off aren't counted, their messages are dropped
            if not await module_settings.is_enabled(guild.id, "serverstats"):
                continue
            rows.append(
                (
                    guild.id,
                    hour,
                    messages.pop(guild.id, 0),
                    self._voice_members(guild) if with_voice else 0,
                    guild.member_count,
                ),
            )
        if rows:
            await server_stats.record(rows)

    # every minute, each person in voice adds a minute and pending messages are saved
    @tasks.loop(minutes=1)
    async def collect(self) -> None:
        try:
            await self._flush(with_voice=True)
        except Exception:
            log.exception("Failed to save server stats")

        hour = server_stats.hour_start()
        if hour != self._pruned_hour:
            self._pruned_hour = hour
            try:
                await server_stats.prune()
            except Exception:
                log.exception("Failed to prune old server stats")

    @collect.before_loop
    async def before_collect(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ServerStatsCog(bot))
