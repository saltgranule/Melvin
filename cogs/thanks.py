import re
import time

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

import module_config
import module_settings
from globals import DATA_DIR, ERROR_MESSAGE
from module_registry import Module, Setting
from ui import ErrorUI, InfoUI, ThankUI, open_config

MODULE = Module(
    "thanks",
    "Thanks",
    "Counts thanks between members.",
    settings=(
        Setting(
            "announce",
            "Thank messages",
            "Whether Melvin posts a message when someone is thanked. Thanks are counted either way.",
            "choice",
            default="on",
            choices=(("on", "On"), ("off", "Off")),
        ),
        Setting(
            "cooldown",
            "Cooldown",
            "How long each member waits between giving thanks.",
            "choice",
            default="60",
            choices=(
                ("30", "30 seconds"),
                ("60", "1 minute"),
                ("300", "5 minutes"),
                ("600", "10 minutes"),
            ),
        ),
    ),
)

# a user can give rate_int thanks per rate_time seconds. rate_time is only used when a
# server hasn't set a cooldown in /thanks config
rate_int = 1
rate_time = 60.0

trigger = [
    "thanks",
    "thx",
    "thank you",
    "ty",
    "cheers",
    "tysm",
    "tyvm",
    "much appreciated",
    "appreciate it",
    "kudos",
    "props",
]

negations = [
    "no",
    "not",
    "dont",
    "don't",
    "never",
    "no thanks to",
    "not thanks to",
    "hardly a",
    "barely a",
    "without any",
    "zero",
    "0",
    "instead of",
    "far from",
    "definitely not",
    "certainly not",
]

# word boundaries, so "ty" doesn't match inside "pretty"
TRIGGER_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in trigger) + r")\b",
    re.IGNORECASE,
)

# a negation right before a trigger cancels it, like "no thanks"
NEGATION_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(n) for n in negations) + r")\s+"
    r"(" + "|".join(re.escape(t) for t in trigger) + r")\b",
    re.IGNORECASE,
)


class ThanksCog(
    commands.GroupCog,
    name="thanks",
    description="'Thank you' count tracking.",
):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot
        self.db_path = DATA_DIR / "thanks.db"
        self._cooldowns: dict[int, list[float]] = {}

    async def cog_load(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS thanks (
                    user_id INTEGER PRIMARY KEY,
                    count INTEGER NOT NULL DEFAULT 0
                )
                """,
            )
            await db.commit()

            # thanks used to have its own on/off setting, move it over to the
            # shared module settings once, then drop the old table
            async with db.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name = 'thanks_settings'",
            ) as cursor:
                has_old_settings = await cursor.fetchone() is not None

            if has_old_settings:
                async with db.execute(
                    "SELECT guild_id FROM thanks_settings WHERE disabled = 1",
                ) as cursor:
                    disabled_guilds = [row[0] async for row in cursor]
                for guild_id in disabled_guilds:
                    await module_settings.set_enabled(guild_id, "thanks", enabled=False)
                await db.execute("DROP TABLE thanks_settings")
                await db.commit()

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            msg = "**You do not have permission to do this.**"
        elif isinstance(error, app_commands.NoPrivateMessage):
            msg = "**This command can only be used in a server.**"
        else:
            msg = ERROR_MESSAGE

        view = ErrorUI(msg)
        if interaction.response.is_done():
            await interaction.edit_original_response(view=view)
        else:
            await interaction.response.send_message(view=view, ephemeral=False)

    def _is_rate_limited(self, user_id: int, window: float) -> bool:
        now = time.monotonic()
        timestamps = self._cooldowns.setdefault(user_id, [])
        timestamps[:] = [t for t in timestamps if now - t < window]
        if len(timestamps) >= rate_int:
            return True
        timestamps.append(now)
        return False

    async def _add_thanks(self, user_id: int) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO thanks (user_id, count)
                VALUES (?, 1)
                ON CONFLICT(user_id) DO UPDATE SET count = count + 1
                RETURNING count
                """,
                (user_id,),
            )
            row = await cursor.fetchone()
            await db.commit()
            return row[0] if row else 1

    async def _get_thanks(self, user_id: int) -> int:
        async with (
            aiosqlite.connect(self.db_path) as db,
            db.execute(
                "SELECT count FROM thanks WHERE user_id = ?",
                (user_id,),
            ) as cursor,
        ):
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def _credit_thanks(
        self,
        message: discord.Message,
        thanker: discord.abc.User,
        thanked: discord.abc.User,
    ) -> None:
        if thanked.bot or thanked.id == thanker.id:
            return

        if message.guild is not None:
            settings = await module_config.get_all(message.guild.id, "thanks")
            cooldown = float(settings["cooldown"] or rate_time)
            announce = settings["announce"] != "off"
        else:
            cooldown, announce = rate_time, True

        if self._is_rate_limited(thanker.id, cooldown):
            return

        new_total = await self._add_thanks(thanked.id)
        if not announce:
            return

        view = ThankUI(
            title=f"Thanks {thanked.mention}!",
            subtitle=f"**{thanker.mention} thanked you, you now have {new_total} thanks.**",
        )
        await message.channel.send(
            view=view,
            allowed_mentions=discord.AllowedMentions(everyone=False, users=False),
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        if message.guild is not None and not await module_settings.is_enabled(
            message.guild.id,
            "thanks",
        ):
            return

        content = message.content

        if NEGATION_PATTERN.search(content):
            return

        if not TRIGGER_PATTERN.search(content):
            return

        thanker = message.author

        # a reply thanks whoever was replied to
        if message.reference is not None and message.reference.message_id is not None:
            replied_message = message.reference.resolved
            if replied_message is None:
                try:
                    replied_message = await message.channel.fetch_message(
                        message.reference.message_id,
                    )
                except discord.NotFound, discord.HTTPException:
                    replied_message = None

            if replied_message is not None and isinstance(
                replied_message,
                discord.Message,
            ):
                await self._credit_thanks(message, thanker, replied_message.author)
                return  # mentions in a reply aren't credited as well

        # otherwise, everyone mentioned is credited
        if message.mentions:
            for mentioned in message.mentions:
                await self._credit_thanks(message, thanker, mentioned)

    @app_commands.command(
        name="count",
        description="Check how many times a user has been thanked.",
    )
    async def count(
        self,
        interaction: discord.Interaction,
        user: discord.User | None = None,
    ) -> None:
        target = user or interaction.user
        total = await self._get_thanks(target.id)

        view = InfoUI(
            title=f"{target.display_name}'s thanks",
            subtitle=f"**Thanked {total} times.**",
        )
        await interaction.response.send_message(view=view)

    @app_commands.command(
        name="config",
        description="Change thanks settings for this server.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config(self, interaction: discord.Interaction) -> None:
        await open_config(interaction, "thanks")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ThanksCog(bot))
