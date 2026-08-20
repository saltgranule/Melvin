import discord
from discord import app_commands
from discord.ext import commands

from ui import ErrorUI, GalleryWithItem, InfoUI, SmallSeparator


# UI Classes
class AvatarView(discord.ui.LayoutView):
    def __init__(self, interaction: discord.Interaction, target: discord.User | discord.Member) -> None:
        super().__init__()

        if target == interaction.client.user:
            mention = "My"
        elif target == interaction.user:
            mention = "Your"
        else:
            mention = f"{target.mention}'s"

        text_display = discord.ui.TextDisplay(f"**{mention} Avatar**")
        media_gallery = GalleryWithItem(target.display_avatar.url)

        if target.avatar is not None:
            formats = (
                ("png", "jpg", "webp", "gif")
                if target.avatar.is_animated()
                else ("png", "jpg", "webp")
            )
            buttons = [
                discord.ui.Button(
                    label=fmt,
                    style=discord.ButtonStyle.link,
                    url=target.avatar.with_format(fmt).url,
                )
                for fmt in formats
            ]
        else:
            buttons = [
                discord.ui.Button(
                    label="Web",
                    style=discord.ButtonStyle.link,
                    url=target.display_avatar.url,
                ),
            ]

        action_row = discord.ui.ActionRow(*buttons)
        container = discord.ui.Container(
            text_display,
            SmallSeparator(),
            media_gallery,
            action_row,
        )
        self.add_item(container)


class BannerView(discord.ui.LayoutView):
    def __init__(
        self,
        interaction: discord.Interaction,
        target: discord.User | discord.Member,
        fetched_user: discord.User,
    ) -> None:
        super().__init__()

        if target == interaction.client.user:
            mention = "My"
        elif target == interaction.user:
            mention = "Your"
        else:
            mention = f"{target.mention}'s"

        text_display = discord.ui.TextDisplay(f"**{mention} Banner**")

        banner_url = fetched_user.banner.url if fetched_user.banner else ""

        media_gallery = GalleryWithItem(banner_url)

        if fetched_user.banner:
            formats = (
                ("png", "jpg", "webp", "gif")
                if fetched_user.banner.is_animated() else
                ("png", "jpg", "webp")
            )
            buttons = [
                discord.ui.Button(
                    label=fmt,
                    style=discord.ButtonStyle.link,
                    url=fetched_user.banner.with_format(fmt).url,
                )
                for fmt in formats
            ]
        else:
            buttons = [
                discord.ui.Button(
                    label="No Banner",
                    style=discord.ButtonStyle.link,
                    disabled=True,
                    url="https://discord.com",
                ),
            ]

        action_row = discord.ui.ActionRow(*buttons)
        container = discord.ui.Container(
            text_display,
            SmallSeparator(),
            media_gallery,
            action_row,
        )
        self.add_item(container)


class InfoCog(
    commands.GroupCog,
    name="info",
    description="Commands for viewing user information and bot stats.",
):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot

    @app_commands.command(name="latency", description="View the bot's latency.")
    async def latency(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        latency = round(self.bot.latency * 1000)
        view = InfoUI(title="Latency", subtitle=f"The bot's latency is **{latency}**ms.")
        await interaction.followup.send(view=view)

    @app_commands.command(name="avatar", description="View a user's avatar.")
    @app_commands.describe(user="The user whose avatar you want to view.")
    async def avatar(
        self,
        interaction: discord.Interaction,
        user: discord.User | None = None,
    ) -> None:
        await interaction.response.defer()
        target = user or interaction.user
        view = AvatarView(interaction, target)
        await interaction.followup.send(
            view=view, allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name="banner", description="View a user's banner.")
    @app_commands.describe(user="The user whose banner you want to view.")
    async def banner(
        self,
        interaction: discord.Interaction,
        user: discord.User | None = None,
    ) -> None:
        await interaction.response.defer()

        target = user or interaction.user
        fetched_user = await self.bot.fetch_user(target.id)

        if target == interaction.client.user:
            mention = "I do"
        elif target == interaction.user:
            mention = "You do"
        else:
            mention = f"{target.mention} does"

        if fetched_user.banner is None:
            await interaction.followup.send(
                view=ErrorUI(f"{mention} not have a profile banner."),
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return
        view = BannerView(interaction, target, fetched_user)
        await interaction.followup.send(
            view=view, allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(InfoCog(bot))
