from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from module_registry import Module
from ui import ErrorUI, GalleryWithItem, Paginator, SmallSeparator

if TYPE_CHECKING:
    from datetime import datetime

MODULE = Module(
    "info",
    "Info",
    "View avatars, banners, roles, and servers.",
)

TYPE_CHOICES = [
    app_commands.Choice(name="Global", value="global"),
    app_commands.Choice(name="Server", value="server"),
]

VERIFICATION_LEVELS = {
    discord.VerificationLevel.none: ("None", "Unrestricted"),
    discord.VerificationLevel.low: ("Low", "Must have a verified email"),
    discord.VerificationLevel.medium: (
        "Medium",
        "Registered on Discord for 5+ minutes",
    ),
    discord.VerificationLevel.high: ("High", "Member of the server for 10+ minutes"),
    discord.VerificationLevel.highest: ("Highest", "Must have a verified phone number"),
}

SERVER_TYPES = (
    ("PARTNERED", "Partnered"),
    ("VERIFIED", "Verified"),
    ("DISCOVERABLE", "Discoverable"),
    ("COMMUNITY", "Community"),
)

NO_MENTIONS = discord.AllowedMentions.none()


def _possessive(
    interaction: discord.Interaction,
    target: discord.User | discord.Member,
) -> str:
    if target == interaction.client.user:
        return "My"
    if target == interaction.user:
        return "Your"
    return f"{target.mention}'s"


def _subject(
    interaction: discord.Interaction,
    target: discord.User | discord.Member,
) -> str:
    if target == interaction.client.user:
        return "I do"
    if target == interaction.user:
        return "You do"
    return f"{target.mention} does"


def _created(when: datetime) -> str:
    return (
        f"**Created at:** {discord.utils.format_dt(when, 'F')} | "
        f"{discord.utils.format_dt(when, 'R')}"
    )


def _details(text: str, icon: discord.Asset | None) -> discord.ui.Item:
    if icon is None:
        return discord.ui.TextDisplay(text)
    return discord.ui.Section(text, accessory=discord.ui.Thumbnail(icon.url))


async def _fetch_member(
    interaction: discord.Interaction,
    target: discord.User | discord.Member,
) -> discord.Member | None:
    if interaction.guild is None:
        return None
    try:
        return await interaction.guild.fetch_member(target.id)
    except discord.NotFound:
        return None


class AssetView(discord.ui.LayoutView):
    def __init__(self, title: str, asset: discord.Asset, *, custom: bool) -> None:
        super().__init__()

        if custom:
            formats = (
                ("png", "jpg", "webp", "gif")
                if asset.is_animated()
                else ("png", "jpg", "webp")
            )
            links = [(fmt, asset.with_format(fmt).url) for fmt in formats]
        else:
            links = [("Web", asset.url)]

        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"**{title}**"),
                SmallSeparator(),
                GalleryWithItem(asset.url),
                discord.ui.ActionRow(
                    *(
                        discord.ui.Button(
                            label=label,
                            style=discord.ButtonStyle.link,
                            url=url,
                        )
                        for label, url in links
                    ),
                ),
            ),
        )


def _role_mention(role: discord.Role) -> str:
    return "@everyone" if role.is_default() else role.mention


def _role_color(role: discord.Role, *, enhanced: bool) -> str:
    if enhanced and role.tertiary_color is not None:
        return (
            f"{role.color}-{role.secondary_color}-{role.tertiary_color} | Holographic"
        )
    if enhanced and role.secondary_color is not None:
        return f"{role.color}-{role.secondary_color} | Gradient"
    return f"{role.color} | Solid"


def _role_hierarchy(role: discord.Role, roles: list[discord.Role]) -> str:
    index = roles.index(role)
    total = len(roles)
    return "\n".join(
        f"{total - i:>4}.   {'>' if i == index else ' '} {roles[i].name.replace('`', '')}"
        for i in range(min(index + 3, total - 1), max(index - 4, -1), -1)
    )


class RoleMembersRow(discord.ui.ActionRow["RoleInfoView"]):
    def __init__(self, role: discord.Role) -> None:
        super().__init__()
        self.role = role

    @discord.ui.button(label="View Members")
    async def view_members(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[RoleInfoView],
    ) -> None:
        view = Paginator(
            f"### {_role_mention(self.role)} Members",
            [f"{m.mention} | {m.name}" for m in self.role.members],
            data_name="Members",
            per_page=10,
            container=True,
        )
        await interaction.response.send_message(
            view=view,
            ephemeral=True,
            allowed_mentions=NO_MENTIONS,
        )
        view.message = await interaction.original_response()


class RoleInfoView(discord.ui.LayoutView):
    def __init__(self, interaction: discord.Interaction, role: discord.Role) -> None:
        super().__init__(timeout=300)
        self.message: discord.Message | None = None

        guild = role.guild
        details = "\n".join(
            (
                f"**Appearance:** {_role_color(role, enhanced='ENHANCED_ROLE_COLORS' in guild.features)}",
                f"**Hoisted:** {'Yes' if role.hoist else 'No'}",
                f"**Mentionable:** {'Yes' if role.mentionable else 'No'}",
                f"**Number of Members:** {len(role.members)}",
                _created(role.created_at),
            ),
        )
        icon = (
            role.display_icon if isinstance(role.display_icon, discord.Asset) else None
        )

        container = discord.ui.Container(
            discord.ui.TextDisplay(f"### {_role_mention(role)} | {role.id}"),
            SmallSeparator(),
            _details(details, icon),
            accent_color=role.color if role.color.value else None,
        )

        user = interaction.user
        if isinstance(user, discord.Member) and not user.top_role.is_default():
            top = user.top_role
            if role == top:
                diff = "This is your highest role."
            elif role > top:
                diff = "This role is above your highest role."
            else:
                diff = "This role is below your highest role."
            container.add_item(discord.ui.TextDisplay(diff))

        container.add_item(
            discord.ui.TextDisplay(
                f"**Relative Hierarchy**\n```\n{_role_hierarchy(role, guild.roles)}\n```",
            ),
        )
        container.add_item(RoleMembersRow(role))
        self.add_item(container)

    async def on_timeout(self) -> None:
        for item in self.walk_children():
            if isinstance(item, discord.ui.Button):
                item.disabled = True

        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class ServerInfoView(discord.ui.LayoutView):
    def __init__(self, guild: discord.Guild, owner: discord.Member) -> None:
        super().__init__()

        member_total = guild.member_count or 0
        bots = sum(member.bot for member in guild.members)
        level, requirement = VERIFICATION_LEVELS.get(
            guild.verification_level,
            ("Unknown", "Unknown"),
        )

        details = "\n".join(
            (
                f"**Owner:** {owner.mention} | {owner.id}",
                f"**Server Description**: {guild.description or "None"}",
                f"**Icon:** [Icon Link]({guild.icon.url})"
                if guild.icon else "**Icon:** None",
                f"**Verification:** {level} | {requirement}",
                f"**2FA:** {'Enabled' if guild.mfa_level else 'Disabled'}",
                f"**Roles:** {len(guild.roles)}",
                f"**Members:** {member_total - bots} humans, {bots} bots | {member_total} total",
                (
                    f"**Channels:** {len(guild.text_channels)} text, "
                    f"{len(guild.voice_channels)} voice, "
                    f"{len(guild.categories)} categories, "
                    f"{len(guild.stage_channels)} stage, "
                    f"{len(guild.forums)} forums | "
                    f"{len(guild.channels)} total"
                ),
                (
                    f"**Server Boosts:** Level {guild.premium_tier} | "
                    f"{guild.premium_subscription_count or 0} boosts total | "
                    f"{len(guild.premium_subscribers or [])} boosters"
                ),
                f"**Vanity Link:** {guild.vanity_url or 'None'}",
                _created(guild.created_at),
            ),
        )

        server_type = next(
            (label for feature, label in SERVER_TYPES if feature in guild.features),
            None,
        )
        title = " | ".join(
            str(part) for part in (guild.name, server_type, guild.id) if part
        )

        container = discord.ui.Container(
            discord.ui.TextDisplay(f"### {title}"),
            SmallSeparator(),
            _details(details, guild.icon),
            accent_color=owner.color if owner.color.value else None,
        )
        if guild.banner:
            container.add_item(GalleryWithItem(guild.banner.url))
        self.add_item(container)


class InfoCog(
    commands.GroupCog,
    name="info",
    description="Commands for viewing user information.",
):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot

    async def _server_asset(
        self,
        interaction: discord.Interaction,
        target: discord.User | discord.Member,
        scope: app_commands.Choice[str] | None,
        kind: str,
    ) -> bool:
        if scope is None or scope.value != "server":
            return False

        if interaction.guild is None:
            await interaction.followup.send(
                view=ErrorUI(f"Server {kind.lower()}s can only be viewed in a server."),
                ephemeral=True,
            )
            return True

        member = await _fetch_member(interaction, target)
        asset = getattr(member, f"guild_{kind.lower()}", None)
        if asset is None:
            return False

        await interaction.followup.send(
            view=AssetView(
                f"{_possessive(interaction, target)} Server {kind}",
                asset,
                custom=True,
            ),
            allowed_mentions=NO_MENTIONS,
        )
        return True

    @app_commands.command(name="avatar", description="View a user's avatar.")
    @app_commands.rename(scope="type")
    @app_commands.describe(
        user="The user whose avatar you want to view.",
        scope="Show the global avatar or the server avatar. Defaults to global.",
    )
    @app_commands.choices(scope=TYPE_CHOICES)
    async def avatar(
        self,
        interaction: discord.Interaction,
        user: discord.User | None = None,
        scope: app_commands.Choice[str] | None = None,
    ) -> None:
        await interaction.response.defer()
        target = user or interaction.user
        if await self._server_asset(interaction, target, scope, "Avatar"):
            return

        await interaction.followup.send(
            view=AssetView(
                f"{_possessive(interaction, target)} Avatar",
                target.avatar or target.default_avatar,
                custom=target.avatar is not None,
            ),
            allowed_mentions=NO_MENTIONS,
        )

    @app_commands.command(name="banner", description="View a user's banner.")
    @app_commands.rename(scope="type")
    @app_commands.describe(
        user="The user whose banner you want to view.",
        scope="Show the global banner or the server banner. Defaults to global.",
    )
    @app_commands.choices(scope=TYPE_CHOICES)
    async def banner(
        self,
        interaction: discord.Interaction,
        user: discord.User | None = None,
        scope: app_commands.Choice[str] | None = None,
    ) -> None:
        await interaction.response.defer()
        target = user or interaction.user
        if await self._server_asset(interaction, target, scope, "Banner"):
            return

        banner = (await self.bot.fetch_user(target.id)).banner
        if banner is None:
            await interaction.followup.send(
                view=ErrorUI(
                    f"{_subject(interaction, target)} not have a profile banner.",
                ),
                ephemeral=True,
                allowed_mentions=NO_MENTIONS,
            )
            return

        await interaction.followup.send(
            view=AssetView(
                f"{_possessive(interaction, target)} Banner",
                banner,
                custom=True,
            ),
            allowed_mentions=NO_MENTIONS,
        )

    @app_commands.command(name="role", description="View information about a role.")
    @app_commands.describe(role="The role you want to view.")
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def role(self, interaction: discord.Interaction, role: discord.Role) -> None:
        await interaction.response.defer()
        view = RoleInfoView(interaction, role)
        view.message = await interaction.followup.send(
            view=view,
            allowed_mentions=NO_MENTIONS,
            wait=True,
        )

    @app_commands.command(
        name="server",
        description="View information about this server.",
    )
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def server(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()

        guild = interaction.guild
        if guild is None:
            return

        owner = guild.owner
        if owner is None:
            try:
                owner = await guild.fetch_member(guild.owner_id or 0)
            except discord.HTTPException:
                await interaction.followup.send(
                    view=ErrorUI("Fetching the server owner failed."),
                    ephemeral=True,
                )
                return

        await interaction.followup.send(
            view=ServerInfoView(guild, owner),
            allowed_mentions=NO_MENTIONS,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(InfoCog(bot))
