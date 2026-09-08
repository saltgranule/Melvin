import re
import time

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

from ui import InfoUI, PositiveUI

rate_int = 1
rate_time = 60.0
# rate_int - how many times a user can trigger the count event, rate_time - the time before the rate_int limit resets, so 1 thank every 60 seconds.

trigger = [
    "thanks",
    "thx",
    "thank you",
    "ty",
    "ta",
    "cheers",
    "tysm",
    "tyvm",
    "thanks a lot",
    "thanks so much",
    "thank you so much",
    "thanks a ton",
    "thanks a million",
    "much appreciated",
    "appreciate it",
    "many thanks",
    "well done",
    "good job",
    "great job",
    "nice job",
    "kudos",
    "props",
]
# trigger phrases, pretty self-explanitory

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
# words that, if immediately preceding a trigger, cancel it out (e.g. "no thanks")

# avoid false flags with regex
TRIGGER_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in trigger) + r")\b",
    re.IGNORECASE,
)

# matches a negation word immediately followed by a trigger word/phrase
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
        self.db_path = "data/thanks.db"
        self._cooldowns: dict[int, list[float]] = {}

    # db setup
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

    def _is_rate_limited(self, user_id: int) -> bool:
        now = time.monotonic()
        timestamps = self._cooldowns.setdefault(user_id, [])
        # drop timestamps outside the rate_time window
        timestamps[:] = [t for t in timestamps if now - t < rate_time]
        if len(timestamps) >= rate_int:
            return True
        timestamps.append(now)
        return False

    async def _add_thanks(self, user_id: int) -> int:
        async with aiosqlite.connect(self.db_path) as db, db.execute(
            "SELECT count FROM thanks WHERE user_id = ?", (user_id,),
        ) as cursor:
            await db.execute(
                """
                INSERT INTO thanks (user_id, count)
                VALUES (?, 1)
                ON CONFLICT(user_id) DO UPDATE SET count = count + 1
                """,
                (user_id,),
            )
            await db.commit()
            row = await cursor.fetchone()
            return row[0] if row else 1

    async def _get_thanks(self, user_id: int) -> int:
        async with aiosqlite.connect(self.db_path) as db, db.execute(
            "SELECT count FROM thanks WHERE user_id = ?", (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def _credit_thanks(
        self, message: discord.Message, thanker: discord.abc.User, thanked: discord.abc.User,
    ) -> None:
        if thanked.bot or thanked.id == thanker.id:
            return

        if self._is_rate_limited(thanker.id):
            return

        new_total = await self._add_thanks(thanked.id)

        view = PositiveUI(
            title=f"Thanks {thanked.mention}!",
            subtitle=f"**{thanker.mention} thanked you, you now have {new_total} thanks.**",
        )
        await message.reply(
            view=view, allowed_mentions=discord.AllowedMentions(everyone=False),
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        content = message.content

        # skip if it's a negated trigger
        if NEGATION_PATTERN.search(content):
            return

        if not TRIGGER_PATTERN.search(content):
            return

        thanker = message.author

        # reply based handling
        if message.reference is not None and message.reference.message_id is not None:
            replied_message = message.reference.resolved
            if replied_message is None:
                try:
                    replied_message = await message.channel.fetch_message(
                        message.reference.message_id,
                    )
                except (discord.NotFound, discord.HTTPException):
                    replied_message = None

            if replied_message is not None:
                await self._credit_thanks(message, thanker, replied_message.author)
                return  # don't also process mentions in the same message

        # mention based handling
        if message.mentions:
            for mentioned in message.mentions:
                await self._credit_thanks(message, thanker, mentioned)

    @app_commands.command(name="count", description="Check how many times a user has been thanked.")
    async def count(
        self, interaction: discord.Interaction, user: discord.User | None = None,
    ) -> None:
        target = user or interaction.user
        total = await self._get_thanks(target.id)

        view = InfoUI(
            title=f"{target.display_name}'s thanks",
            subtitle=f"**Thanked {total} times.**",
        )
        await interaction.response.send_message(view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ThanksCog(bot))
