from collections.abc import Awaitable, Callable

import discord

import module_config
import module_settings
from globals import ERROR_MESSAGE, MELVIN_MISC_EMOJI

from .views import ErrorUI, SmallSeparator

# called after a setting changes, for modules that need to act on it straight away
OnChange = Callable[[discord.Guild], Awaitable[None]]

CHANNEL_TYPES = {
    "text": [discord.ChannelType.text],
    "any": [discord.ChannelType.text, discord.ChannelType.news],
}


def _display(setting: module_config.Setting, value: str | None) -> str:
    if value is None:
        return "Not set"

    is_default = value == setting.default
    if setting.kind == "channel":
        shown = f"<#{value}>"
    elif setting.kind == "channels":
        shown = ", ".join(f"<#{part}>" for part in value.split(","))
    elif setting.kind == "role":
        shown = f"<@&{value}>"
    elif setting.kind == "choice":
        shown = module_config.choice_label(setting, value) or value
    elif setting.kind == "color":
        shown = " and ".join(f"#{part}" for part in value.split("-"))
    elif setting.kind == "image":
        shown = "an image"
    else:
        text = value if len(value) <= 200 else value[:197] + "..."
        shown = discord.utils.escape_markdown(text)

    return f"Set to {shown}" + (" (default)" if is_default else "")


async def _reply_error(interaction: discord.Interaction, message: str) -> None:
    view = ErrorUI(f"**{message}**")
    if interaction.response.is_done():
        await interaction.followup.send(view=view, ephemeral=True)
    else:
        await interaction.response.send_message(view=view, ephemeral=True)


class ConfigView(discord.ui.LayoutView):
    # the settings card for one module, rebuilt after every change

    def __init__(
        self,
        module: str,
        guild: discord.Guild,
        values: dict[str, str | None],
        on_change: OnChange | None = None,
    ) -> None:
        super().__init__(timeout=300)
        self.module = module
        self.guild = guild
        self.on_change = on_change

        label, description = module_settings.MODULES[module]
        container = discord.ui.Container(
            discord.ui.TextDisplay(
                f"# {MELVIN_MISC_EMOJI} {label} Settings\n-# **{description}**",
            ),
            SmallSeparator(),
        )

        for setting in module_config.CONFIG[module]:
            value = values[setting.key]
            text = (
                f"**{setting.label}**\n-# {setting.description}\n"
                f"{_display(setting, value)}"
            )
            control = self._control(setting, value)
            if isinstance(control, discord.ui.Button):
                container.add_item(discord.ui.Section(text, accessory=control))
            else:
                container.add_item(discord.ui.TextDisplay(text))
                container.add_item(discord.ui.ActionRow(control))

        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        permissions = getattr(interaction.user, "guild_permissions", None)
        if permissions and permissions.manage_guild:
            return True
        await _reply_error(interaction, "You do not have permission to do this.")
        return False

    def _control(
        self,
        setting: module_config.Setting,
        value: str | None,
    ) -> discord.ui.Item:
        if setting.kind in {"channel", "channels"}:
            several = setting.kind == "channels"
            select = discord.ui.ChannelSelect(
                placeholder="Pick channels..." if several else "Pick a channel...",
                channel_types=CHANNEL_TYPES[setting.channel_type],
                min_values=0,
                max_values=module_config.MAX_CHANNELS if several else 1,
                default_values=[
                    discord.Object(int(part))
                    for part in (value or "").split(",")
                    if part
                ],
            )
        elif setting.kind == "role":
            select = discord.ui.RoleSelect(
                placeholder="Pick a role...",
                min_values=0,
                max_values=1,
                default_values=[discord.Object(int(value))] if value else [],
            )
        elif setting.kind == "choice":
            select = discord.ui.Select(
                options=[
                    discord.SelectOption(label=label, value=key, default=key == value)
                    for key, label in setting.choices
                ],
            )
        else:
            button = discord.ui.Button(
                label="Edit",
                style=discord.ButtonStyle.secondary,
            )

            async def _open_modal(interaction: discord.Interaction) -> None:
                await interaction.response.send_modal(
                    SettingModal(self, setting, value),
                )

            button.callback = _open_modal
            return button

        async def _picked(interaction: discord.Interaction) -> None:
            raw = ",".join(
                str(picked.id) if hasattr(picked, "id") else picked
                for picked in select.values
            )
            await self.save(interaction, setting, raw or None)

        select.callback = _picked
        return select

    async def save(
        self,
        interaction: discord.Interaction,
        setting: module_config.Setting,
        raw: str | None,
    ) -> None:
        try:
            value = module_config.clean_value(setting, raw)
            if setting.kind == "role" and value is not None:
                self._check_role(interaction, int(value), setting)
            await module_config.set_values(
                self.guild.id,
                self.module,
                {setting.key: value},
            )
        except module_config.ConfigError as e:
            await _reply_error(interaction, str(e))
            return

        await self.refresh(interaction)

    def _check_role(
        self,
        interaction: discord.Interaction,
        role_id: int,
        setting: module_config.Setting,
    ) -> None:
        user = interaction.user
        role = self.guild.get_role(role_id)
        if setting.permission and not getattr(
            user.guild_permissions,
            setting.permission,
            False,
        ):
            needed = setting.permission.replace("_", " ").title()
            msg = f"You need {needed} to change this."
            raise module_config.ConfigError(msg)
        if role is None or role.is_default() or role.managed:
            msg = "That role can't be given out by Melvin."
            raise module_config.ConfigError(msg)
        if role >= self.guild.me.top_role:
            msg = "That role is equal to or above Melvin's top role."
            raise module_config.ConfigError(msg)
        if user.id != self.guild.owner_id and role >= user.top_role:
            msg = "That role is equal to or above your top role."
            raise module_config.ConfigError(msg)

    async def refresh(self, interaction: discord.Interaction) -> None:
        applied = True
        if self.on_change is not None:
            try:
                await self.on_change(self.guild)
            except discord.HTTPException:
                applied = False

        values = await module_config.get_all(self.guild.id, self.module)
        view = ConfigView(self.module, self.guild, values, self.on_change)
        await interaction.response.edit_message(
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        if not applied:
            await _reply_error(
                interaction,
                "Saved, but Discord didn't accept the change yet. It'll be retried shortly.",
            )


class SettingModal(discord.ui.Modal):
    # edits a text, link, color, or image setting

    def __init__(
        self,
        view: ConfigView,
        setting: module_config.Setting,
        value: str | None,
    ) -> None:
        super().__init__(title=setting.label[:45])
        self.config_view = view
        self.setting = setting
        self.has_value = value is not None and value != setting.default

        if setting.kind == "image":
            self.upload = discord.ui.FileUpload(required=False)
            self.add_item(
                discord.ui.Label(
                    text="New image",
                    description="PNG, JPG, GIF, or WebP, up to 8 MB.",
                    component=self.upload,
                ),
            )
            self.remove = discord.ui.Checkbox()
            if self.has_value:
                self.add_item(
                    discord.ui.Label(
                        text="Remove the current image",
                        component=self.remove,
                    ),
                )
            return

        self.text = discord.ui.TextInput(
            style=(
                discord.TextStyle.paragraph
                if setting.max_length > 100
                else discord.TextStyle.short
            ),
            default=value if self.has_value else None,
            placeholder=setting.placeholder or None,
            max_length=512 if setting.kind == "url" else setting.max_length,
            required=False,
        )
        self.add_item(
            discord.ui.Label(
                text=setting.label[:45],
                description=f"{setting.description} Leave empty to reset."[:100],
                component=self.text,
            ),
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if self.setting.kind != "image":
            await self.config_view.save(interaction, self.setting, str(self.text.value))
            return

        guild_id, module, key = (
            self.config_view.guild.id,
            self.config_view.module,
            self.setting.key,
        )
        if self.upload.values and self.upload.values[0].size > module_config.MAX_IMAGE_BYTES:
            await _reply_error(interaction, "Images must be 8 MB or smaller.")
            return

        try:
            if self.upload.values:
                attachment = self.upload.values[0]
                data = await attachment.read()
                await module_config.replace_image(
                    guild_id,
                    module,
                    key,
                    attachment.filename,
                    data,
                )
            elif self.remove.value:
                await module_config.remove_image(guild_id, module, key)
        except module_config.ConfigError as e:
            await _reply_error(interaction, str(e))
            return
        except discord.HTTPException:
            await _reply_error(
                interaction,
                "Couldn't download that image, please try again.",
            )
            return

        await self.config_view.refresh(interaction)


async def open_config(
    interaction: discord.Interaction,
    module: str,
    *,
    on_change: OnChange | None = None,
) -> None:
    # every /<module> config command replies through here
    if interaction.guild is None:
        await _reply_error(interaction, "This command can only be used in a server.")
        return

    try:
        values = await module_config.get_all(interaction.guild.id, module)
    except Exception:
        await _reply_error(interaction, ERROR_MESSAGE.strip("*"))
        raise

    await interaction.response.send_message(
        view=ConfigView(module, interaction.guild, values, on_change),
        allowed_mentions=discord.AllowedMentions.none(),
    )
