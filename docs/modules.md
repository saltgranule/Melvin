# Modules Documentation
Turn Melvin's features on or off for a guild, with `/modules` in Discord or from the dashboard on the website. Every module is on by default.

## Storage
Module settings are stored in a SQLite database at `data/modules.db`, in a table called `guild_modules`. Each row holds a guild id, a module name, and whether it's enabled. A guild only has rows for modules it has changed. The table is created automatically when the bot starts, if it does not already exist.
The bot keeps the settings cached and re-reads them every 10 seconds, so changes made outside of Discord still apply shortly after.

## modules command
Path: `/modules`
Turn Melvin's features on or off for this server.

**Parameters**
None.

**Permissions**
Requires Manage Server. Guild only.

**Behavior**
The command replies with a list of modules, each with its name, a short description, and a button showing whether it's on or off.
Pressing a button turns that module on or off for the guild, and the list updates in place. Only members with Manage Server can press the buttons. The buttons stop responding after 5 minutes, and running the command again shows a new list.

**Error handling**
If the command user lacks Manage Server, or the command is used outside a guild, the command replies with an ephemeral error message.

## Modules

| Module | Covers |
|------|------|
| Moderation | The `/mod` commands, and giving the auto-role to new members. |
| Audit Logs | The `/audit` commands, and every logged event. |
| Welcome | The `/welcome` commands, and welcome messages for new members. |
| Thanks | The `/thanks` commands, and counting thanks in messages. |
| AI | The `/ai` commands. |
| Tools | The `/tool` commands, and the Decode message option. |
| Timezones | The `/timezone` commands. |
| Info | The `/info` commands. |
| Style | The `/style` commands, and applying Melvin's default style when it joins. |
| Server Stats | Counting messages, voice minutes, and members for the dashboard's Server Stats page. |

`/help`, `/latency`, `/melvin`, `/stats`, and `/modules` itself can't be turned off.

## Settings
Modules with settings have a `config` command, `/audit config`, `/mod config`, `/style config`, `/thanks config`, and `/welcome config`. They all work the same way, and the same settings can be changed from the dashboard under Config on the module's card.
Settings are stored in the same database, in a table called `guild_settings`. Each row holds a guild id, module, setting, value, and when it was last changed. A guild only has rows for settings it has changed, everything else uses its default.

## When a module is off
Its commands reply with an ephemeral error message saying the module is turned off, and that someone with Manage Server can turn it back on with `/modules`.
Its commands are also left out of `/help` in that guild.
Its background features stop as well, for example audit logs aren't posted and welcome messages aren't sent.
Settings for the module, such as the audit log channel or welcome message, are kept, so turning the module back on picks up where it left off.
Modules only apply in guilds. Commands used in DMs or as a user app are never blocked.
