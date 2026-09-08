import asyncio
import logging
import os
import time
import warnings
from datetime import UTC, datetime

import aiosqlite
import discord
from ddgs import DDGS
from discord import app_commands
from discord.ext import commands
from groq import AsyncGroq

from globals import MELVIN_EMOJI
from ui import ErrorUI, SmallSeparator

warnings.filterwarnings("ignore", category=DeprecationWarning)

log = logging.getLogger(__name__)

RATE_LIMIT = 10
RATE_PERIOD = 60 * 60  # 1 hour, in seconds
GROQ_MODEL = "openai/gpt-oss-20b"


class AgentCog(
    commands.GroupCog,
    name="ai",
    description="Self explanatory, ask a free AI model some stupid shit.",
):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot
        self.api_key = os.getenv("GROQ")
        self.client = AsyncGroq(api_key=self.api_key)
        self.db_path = "data/ai_usage.db"

    # db setup
    async def cog_load(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_requests (
                    user_id INTEGER NOT NULL,
                    timestamp INTEGER NOT NULL
                )
                """,
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_ai_requests_user_ts "
                "ON ai_requests (user_id, timestamp)",
            )
            await db.commit()

    def truncate(self, text: str, length: int = 1500) -> str:
        return (text)[: length - 3] + "..." if len(text) > length else text

    def _get_web_context(self, query: str, max_results: int = 5) -> str:
        try:
            ddgs = DDGS()
            results = list(ddgs.text(query, max_results=max_results))
            if not results:
                return "No search context available."

            formatted_results = []
            for i, r in enumerate(results, 1):
                formatted_results.append(
                    f"Source {i}:\nTitle: {r.get('title')}\nURL: {r.get('href')}\nSnippet: {r.get('body')}\n",
                )
            return "\n---\n".join(formatted_results)
        except Exception:
            return "Could not fetch search context."

    async def _check_rate_limit(self, user_id: int) -> tuple[bool, int, int]:
        now = int(time.time())
        window_start = now - RATE_PERIOD
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM ai_requests WHERE user_id = ? AND timestamp > ?",
                (user_id, window_start),
            ) as cursor:
                row = await cursor.fetchone()
                count = row[0] if row else 0

            if count < RATE_LIMIT:
                return True, count, 0
            async with db.execute(
                "SELECT MIN(timestamp) FROM ai_requests WHERE user_id = ? AND timestamp > ?",
                (user_id, window_start),
            ) as cursor:
                row = await cursor.fetchone()
                oldest = row[0] if row and row[0] is not None else now

        retry_after = max(0, (oldest + RATE_PERIOD) - now)
        return False, count, retry_after

    async def _record_request(self, user_id: int) -> None:
        now = int(time.time())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO ai_requests (user_id, timestamp) VALUES (?, ?)",
                (user_id, now),
            )
            await db.execute(
                "DELETE FROM ai_requests WHERE timestamp <= ?",
                (now - RATE_PERIOD,),
            )
            await db.commit()

    # cogwide error logging
    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.CommandOnCooldown):
            msg = "**You are being rate limited.**"
        else:
            msg = f"**Something went wrong.**"
        error_ui = ErrorUI(msg)
        if interaction.response.is_done():
            await interaction.followup.send(view=error_ui, ephemeral=True)
        else:
            await interaction.response.send_message(view=error_ui, ephemeral=True)

    async def query_groq(self, prompt: str, *, use_search: bool = False) -> str:
        current_date_str = datetime.now(UTC).strftime("%B %d, %Y")

        system_instruction = (
            f"Today's date is {current_date_str}. "
            "Try to keep responses tidy, brief, and minimal to stay within Discord's 4000 character limit. "
            "Contain responses in short, yet informative paragraphs, rather than graphs or tables or bulletpoints. "
            "Refrain from using emojis unless told to. "
        )

        if use_search:
            search_context = await asyncio.to_thread(self._get_web_context, prompt)
            system_instruction += "Use the provided search context to ground your answer relative to today's date. "
            full_prompt = (
                f"--- CURRENT DATE: {current_date_str} ---\n"
                f"--- SEARCH CONTEXT ---\n"
                f"{search_context}\n"
                f"--- END CONTEXT ---\n\n"
                f"User Question: {prompt}"
            )
        else:
            full_prompt = (
                f"--- CURRENT DATE: {current_date_str} ---\n\nUser Question: {prompt}"
            )

        try:
            response = await self.client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": full_prompt},
                ],
                temperature=0.7,
            )
            text = response.choices[0].message.content
            if text:
                return text
            raise RuntimeError("**Groq returned an empty response.**")
        except Exception as e:
            raise RuntimeError(f"**Groq API Error: {e!s}.**")

    @app_commands.command(
        name="ask",
        description="Ask a free AI model some stupid shit.",
    )
    @app_commands.describe(
        prompt="The question or prompt to ask the AI model.",
        search="Whether to perform a web search for grounding context.",
    )
    @app_commands.checks.cooldown(2, 60)
    async def ask(
        self,
        interaction: discord.Interaction,
        prompt: str,
        *,
        search: bool = False,
    ) -> None:
        await interaction.response.defer()

        allowed, used, retry_after = await self._check_rate_limit(interaction.user.id)
        if not allowed:
            minutes = max(1, retry_after // 60)
            await interaction.edit_original_response(
                view=ErrorUI(
                    f"**You've hit the limit of {RATE_LIMIT} requests per hour, try again in about {minutes} minute(s).",
                ),
            )
            return

        try:
            start = time.time()
            ai_response = self.truncate(
                await self.query_groq(prompt, use_search=search),
            )
            elapsed = time.time() - start

            await self._record_request(interaction.user.id)
            remaining = max(0, RATE_LIMIT - (used + 1))

            model_button = discord.ui.Button(
                label="Model",
                style=discord.ButtonStyle.link,
                url="https://huggingface.co/openai/gpt-oss-20b",
            )
            prompt_section = discord.ui.Section(
                f"# **Prompt:** {discord.utils.escape_markdown(prompt)}",
                accessory=model_button,
            )

            grounding_text = (
                f"-# **Grounded using DDGS web search context with {GROQ_MODEL}**"
                if search else
                f"-# **Generated without web search using {GROQ_MODEL}**"
            )

            response_display = discord.ui.TextDisplay(
                f"{ai_response}\n\n"
                f"-# **{MELVIN_EMOJI} Responses may be shortened due to Discord UI limitations. Took {elapsed:.1f}s. "
                f"{remaining}/{RATE_LIMIT} requests left this hour.**\n"
                f"{grounding_text}",
            )
            view = discord.ui.LayoutView()
            view.add_item(
                discord.ui.Container(
                    prompt_section,
                    SmallSeparator(),
                    response_display,
                ),
            )
            await interaction.edit_original_response(view=view)
        except Exception as e:
            log.exception("Failure in agent command")
            await interaction.edit_original_response(view=ErrorUI("**something went wrong, likely an API error.**"))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AgentCog(bot))