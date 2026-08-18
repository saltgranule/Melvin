import asyncio
import logging
import os
import time
import warnings
from datetime import datetime

import discord
from ddgs import DDGS
from discord import app_commands
from discord.ext import commands
from google import genai
from google.genai import types

from globals import MELVIN_EMOJI
from ui import ErrorUI, SmallSeparator

warnings.filterwarnings("ignore", category=DeprecationWarning)

log = logging.getLogger(__name__)


class AgentCog(
    commands.GroupCog,
    name="ai",
    description="Self explanatory, ask a free AI model some stupid shit.",
):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot
        self.api_key = os.getenv("GAPI")
        self.client = genai.Client(api_key=self.api_key)

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

    # cogwide error logging
    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.CommandOnCooldown):
            msg = "**You are being rate limited.**"
        else:
            msg = f"**Something went wrong: {error}.**"
        error_ui = ErrorUI(msg)
        if interaction.response.is_done():
            await interaction.followup.send(view=error_ui, ephemeral=True)
        else:
            await interaction.response.send_message(view=error_ui, ephemeral=True)

    async def query_gemini(self, prompt: str, *, use_search: bool = False) -> str:
        current_date_str = datetime.now().strftime("%B %d, %Y")

        system_instruction = (
            f"Today's date is {current_date_str}. "
            "Try to keep responses tidy, brief, and minimal to stay within Discord's 4000 character limit. "
            "Contain responses in short, yet informative paragraphs, rather than graphs or tables. "
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

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.7,
        )
        try:
            response = await self.client.aio.models.generate_content(
                model="gemini-3.1-flash-lite",
                contents=full_prompt,
                config=config,
            )
            if response.text:
                return response.text
            raise RuntimeError("**Gemini returned an empty response.**")
        except Exception as e:
            raise RuntimeError(f"**Gemini API Error: {e!s}.**")

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
        try:
            start = time.time()
            ai_response = self.truncate(
                await self.query_gemini(prompt, use_search=search),
            )
            elapsed = time.time() - start
            model_button = discord.ui.Button(
                label="Model",
                style=discord.ButtonStyle.link,
                url="https://aistudio.google.com/",
            )
            prompt_section = discord.ui.Section(
                f"# **Prompt:** `{discord.utils.escape_markdown(prompt)}`",
                accessory=model_button,
            )

            grounding_text = (
                "-# **Grounded using DDGS web search context.**"
                if search else
                "-# **Generated without web search.**"
            )

            response_display = discord.ui.TextDisplay(
                f"{ai_response}\n\n"
                f"-# **{MELVIN_EMOJI} Responses may be shortened due to Discord UI limitations. Took {elapsed:.1f}s.**\n"
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
            await interaction.edit_original_response(view=ErrorUI(str(e)))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AgentCog(bot))
