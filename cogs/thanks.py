import re
import time

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

import module_config
import module_settings
from globals import DATA_DIR
from module_registry import Module, Setting
from ui import InfoUI, ThankUI, open_config

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
            group="Behavior",
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
            group="Behavior",
        ),
    ),
)

DEFAULT_COOLDOWN = 60.0

TRIGGERS = (
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
)

NEGATIONS = (
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
)

_TRIGGER_GROUP = "(" + "|".join(map(re.escape, TRIGGERS)) + ")"
TRIGGER_PATTERN = re.compile(rf"\b{_TRIGGER_GROUP}\b", re.IGNORECASE)
NEGATION_PATTERN = re.compile(
    r"\b(" + "|".join(map(re.escape, NEGATIONS)) + rf")\s+{_TRIGGER_GROUP}\b",
    re.IGNORECASE,
)


def _is_thanks(content: str) -> bool:
    return bool(TRIGGER_PATTERN.search(content)) and not NEGATION_PATTERN.search(
        content,
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
        self._last_thanks: dict[int, float] = {}

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

            async with db.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name = 'thanks_settings'",
            ) as cursor:
                if await cursor.fetchone() is None:
                    return

            async with db.execute(
                "SELECT guild_id FROM thanks_settings WHERE disabled = 1",
            ) as cursor:
                disabled_guilds = [row[0] async for row in cursor]
            for guild_id in disabled_guilds:
                await module_settings.set_enabled(guild_id, "thanks", enabled=False)
            await db.execute("DROP TABLE thanks_settings")
            await db.commit()

    def _is_rate_limited(self, user_id: int, window: float) -> bool:
        now = time.monotonic()
        last = self._last_thanks.get(user_id)
        if last is not None and now - last < window:
            return True
        self._last_thanks[user_id] = now
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
            cooldown = float(settings["cooldown"] or DEFAULT_COOLDOWN)
            announce = settings["announce"] != "off"
        else:
            cooldown, announce = DEFAULT_COOLDOWN, True

        if self._is_rate_limited(thanker.id, cooldown):
            return

        new_total = await self._add_thanks(thanked.id)
        if not announce:
            return

        await message.channel.send(
            view=ThankUI(
                title=f"Thanks {thanked.mention}!",
                subtitle=f"**{thanker.mention} thanked you, you now have {new_total} thanks.**",
            ),
            allowed_mentions=discord.AllowedMentions(everyone=False, users=False),
        )

    async def _replied_author(
        self,
        message: discord.Message,
    ) -> discord.abc.User | None:
        reference = message.reference
        if reference is None or reference.message_id is None:
            return None
        replied = reference.resolved
        if replied is None:
            try:
                replied = await message.channel.fetch_message(reference.message_id)
            except discord.HTTPException:
                return None
        return replied.author if isinstance(replied, discord.Message) else None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if (
            message.author.bot
            or (message.reference is None and not message.mentions)
            or not _is_thanks(message.content)
        ):
            return
        if message.guild is not None and not await module_settings.is_enabled(
            message.guild.id,
            "thanks",
        ):
            return

        replied_author = await self._replied_author(message)
        if replied_author is not None:
            await self._credit_thanks(message, message.author, replied_author)
            return

        for mentioned in message.mentions:
            await self._credit_thanks(message, message.author, mentioned)

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
        await interaction.response.send_message(
            view=InfoUI(
                title=f"{target.display_name}'s thanks",
                subtitle=f"**Thanked {total} times.**",
            ),
        )

    @app_commands.command(
        name="config",
        description="Change thanks settings for this server.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config(self, interaction: discord.Interaction) -> None:
        await open_config(interaction, "thanks")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ThanksCog(bot))
