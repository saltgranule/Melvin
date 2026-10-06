# Module Development Documentation
How to make a cog show up on the dashboard as a module, and how to give it settings. This page is for contributors. The examples come from Melvin's own cogs, mostly the thanks cog, since it uses every part of this.

## How it fits together
Modules are handled by three shared files. Cogs only need small additions to plug into them.

| File | What it does |
|------|--------------|
| `module_settings.py` | Lists the modules, and stores whether each one is on or off per guild. |
| `module_config.py` | Lists each module's settings with their defaults, checks values, and stores them per guild. |
| `ui/config.py` | The settings card every `/<module> config` command replies with. |
| `dashboard.py` | The website dashboard, built from the files above. |

The bot and the website both read and write the same database at `data/modules.db`. The bot caches it and re-reads it every 10 seconds, so a change made on the dashboard reaches the bot within that time.

## Making a cog a module
A module is a cog that can be turned on or off per guild, from `/modules` or the dashboard.

**1. Use a GroupCog**
The module's key is the cog's command group name, so the cog has to be a `commands.GroupCog`.

```python
class ThanksCog(
    commands.GroupCog,
    name="thanks",
    description="'Thank you' count tracking.",
):
```

**2. Add it to MODULES**
In `module_settings.py`, add an entry with the group name as the key, then a label and a short description. These show on `/modules` and on the dashboard card.

```python
MODULES = {
    ...
    "thanks": ("Thanks", "Counts thanks between members."),
}
```

That's all it takes for the module to get a switch on `/modules` and the dashboard. When it's turned off, the bot automatically blocks every command in the group, including subcommands and any message options the cog adds, and leaves the group out of `/help` in that guild.

**3. Check it in listeners**
Listeners aren't commands, so they aren't blocked automatically. Every listener that does something in a guild should check the module first, like the thanks cog does before counting a thank.

```python
@commands.Cog.listener()
async def on_message(self, message: discord.Message) -> None:
    if message.author.bot:
        return

    if message.guild is not None and not await module_settings.is_enabled(
        message.guild.id,
        "thanks",
    ):
        return
```

If every listener goes through the same lookup, put the check there once instead. The audit cog checks inside `get_log_channel`, since all 15 of its listeners call it.

Listeners that clean up after the bot leaves a guild, like `on_guild_remove`, should run whether the module is on or not.

**What isn't a module**
Commands outside a group, like `/help`, `/latency`, and `/melvin`, can't be turned off. Neither can the stats, private, and debug cogs, since they aren't listed in `MODULES`.

## Making a module configurable
A configurable module gets a `/<module> config` command and a Config button on its dashboard card. Both are built from the same list of settings, so each setting is only defined once.

**1. Add its settings to CONFIG**
In `module_config.py`, add the module's settings to `CONFIG`, in the order they should appear.

```python
CONFIG = {
    ...
    "thanks": (
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
}
```

A setting that needs more than Manage Server says so with `permission`, like the moderation auto-role.

```python
(
    Setting(
        "auto_role",
        "Auto-role",
        "Given to members when they join. Leave empty for none.",
        "role",
        permission="manage_roles",
    ),
)
```

These are the fields a setting can have.

| Field | Description |
|------|--------------|
| `key` | The name it's stored under. Keep it short and never rename it, since saved values use it. |
| `label` | The name shown on the card and the dashboard. |
| `description` | One or two sentences explaining what it does. |
| `kind` | What type of value it is, see the table below. |
| `default` | The value used until a guild changes it. Leave it out for no value. |
| `choices` | For choice settings, pairs of the stored value and the label shown. |
| `max_length` | For text settings, the longest value allowed. Over 100 gets a larger text box. |
| `placeholder` | Example text shown in empty boxes. |
| `permission` | A Discord permission needed on top of Manage Server, like `"manage_roles"`. |

Each kind of setting gets its own controls on both sides, and is stored as text.

| Kind | In Discord | On the dashboard | Stored as |
|------|------|------|------|
| `channel` | Channel select menu | Dropdown of text channels | The channel id |
| `role` | Role select menu | Dropdown of roles Melvin and the user can give out | The role id |
| `choice` | Select menu | Dropdown | The chosen value |
| `text` | Edit button and form | Text box | The text |
| `url` | Edit button and form | Link box | The link, which must start with `http://` or `https://` |
| `color` | Edit button and form | Text box with color swatches | Hex codes joined by a dash, like `F4A261-FFFFFF` |
| `image` | Edit button and form with an upload and a remove checkbox | File upload with a preview | The file's path in `data/config_images` |

Values are checked the same way on both sides by `clean_value`, so a value that's rejected in Discord is also rejected on the dashboard. If a setting needs a kind that isn't listed, add it to `clean_value`, `ui/config.py`, and the field markup in `templates/dashboard_config.html`.

**2. Add the config command**
Every config command looks the same. Keep the name `config`, keep the Manage Server check, and reply through `open_config`.

```python
from ui import open_config


@app_commands.command(
    name="config",
    description="Change thanks settings for this server.",
)
@app_commands.checks.has_permissions(manage_guild=True)
async def config(self, interaction: discord.Interaction) -> None:
    await open_config(interaction, "thanks")
```

The cog should also have the same `cog_app_command_error` as the other cogs, so a missing permission replies with `You do not have permission to do this.`

**3. Read the settings**
Read settings wherever the cog needs them. Values come back as text, or None when a setting has no value and no default, so turn ids and numbers into the right type first. The thanks cog reads both of its settings before crediting a thank.

```python
if message.guild is not None:
    settings = await module_config.get_all(message.guild.id, "thanks")
    cooldown = float(settings["cooldown"] or rate_time)
    announce = settings["announce"] != "off"
else:
    cooldown, announce = rate_time, True
```

Use `module_config.get(guild_id, module, key)` to read a single setting, like the audit cog does for its log channel.

```python
channel_id = await module_config.get(guild_id, "audit", "log_channel")
return self.bot.get_channel(int(channel_id)) if channel_id else None
``` Reads are cached, so it's fine to read settings in busy listeners like `on_message`.

**4. Document it**
Add a `## config command` section to the cog's docs page with a table of its settings, following `docs/thanks.md`.

## Reacting to changes
Most cogs just read their settings when they need them, so changes apply on their own. Some settings have to change something on Discord the moment they're saved, like the style cog setting Melvin's name.

For changes made in Discord, pass a function to `open_config`. It's called with the guild after every change.

```python
await open_config(interaction, "style", on_change=self.apply_style)
```

The dashboard can't reach the bot directly, so for changes made there, check for recently changed guilds in a loop. `changed_since` returns the guilds with a setting changed after a `time.time()` timestamp. The style cog does this every 15 seconds in `sync_styles`, and remembers what it last sent so unchanged styles aren't sent again.

## Moving old settings
If a cog already stored settings in its own table, move them over once in `cog_load` with `migrate_legacy`. It copies each row into the shared settings, then renames the old table to `<table>_migrated` instead of deleting it. The audit cog used to keep its log channels in a `log_channels` table.

```python
async def cog_load(self) -> None:
    await module_config.migrate_legacy(
        self.db_path,
        "log_channels",
        "audit",
        lambda row: (int(row[0]), {"log_channel": row[1]}),
    )
```

The welcome cog does the same with its `welcome_channels` table, mapping each column to one of its settings.

The function receives each row of the old table, and returns the guild id with a dictionary of setting keys and values. Empty values are skipped.

## Adding a dashboard section
Server pages have a sidebar of sections, which only has Modules for now. To add one:

1. Add the page's endpoint and label to `GUILD_SECTIONS` in `dashboard.py`. Modules is listed as `("dashboard.modules", "Modules")`.
2. Add a route under `/<int:guild_id>/`. Load the user's servers with `manageable_guilds()`, find the server with `_find_guild`, and reply with a 404 if it isn't there, so the page never reveals servers the user can't manage.
3. Pass `sections=_sidebar(guild_id, ...)` with the page's endpoint to the template, and include `_dashboard_sidebar.html` in it, like `dashboard_guild.html` does.

Anything that saves must check the CSRF token with `_check_csrf()`, and re-check the user's permissions with `manageable_guilds(max_age=WRITE_CHECK_SECONDS, strict=True)` before saving. That way someone who has lost Manage Server can't keep changing settings with an old page.

**Saving**
The dashboard saves in one of two ways, depending on what's being changed.
A single on or off choice saves the moment it's clicked, like the switches on the Modules page. Each switch is its own small form, and the page's script sends it in the background, so it still works without the script. The server replies with JSON when the request has an `X-Requested-With: fetch` header, and redirects back to the page otherwise.
Anything else is a form with a Save changes button, like the config pages. Every field is checked before anything is saved, and if any of them are wrong, nothing is saved and each problem is shown under its field.

**Banners**
Status messages use the banner macro in `templates/_banner.html`, so they look the same everywhere. Import it at the top of the template, then call it with a kind and a message.

```jinja
{% from "_banner.html" import banner %}

{{ banner("success", "Saved. Changes apply in Discord within a few seconds.") }}
```

| Kind | Color | Use it for |
|------|------|--------------|
| `success` | Secondary, the green in `globals.py` | Something worked, like a save. |
| `error` | Tertiary, the red in `globals.py` | Something failed or needs fixing. |
| `misc` | Primary, the orange in `globals.py` | Anything else worth pointing out, like a module being turned off. |

Banners are only for what just happened or needs attention. Descriptions of how a page works use the plain `dashboard-notice` style instead.
To fill in a banner from a script, render it hidden with an id, like `banner("error", "", id="dashboard-error", hidden=True)`, then set its text and unhide it.

## Checklist
- The cog is a GroupCog, and its group name is in `MODULES`.
- Every listener that acts in a guild checks `module_settings.is_enabled`.
- Its settings are in `CONFIG`, with a description and default for each.
- It has a `config` command that replies through `open_config`, with the Manage Server check and the shared error handler.
- It reads settings with `module_config`, never from its own table.
- Old settings are moved with `migrate_legacy`, if there were any.
- Its docs page has a `config command` section.
