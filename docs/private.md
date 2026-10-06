# Private Cog Documentation
Administrative and developer utilities. These are for the bot's developers and don't change anything in your guild.
Command group name: `private`

## sync command
Path: `/private sync`
Sync the application command tree.

**Parameters**
None.

**Permissions**
Only the bot's owner can run this. Anyone else gets a "Gated" reply pointing them to the support server.

**Behavior**
The command re-registers all of the bot's slash commands with Discord, then replies with how many were synced. All replies are ephemeral.

**Error handling**
If Discord rejects the sync, the command replies with the error.

## Developer logs
The bot posts some events to a private log channel in its own development server, to help spot problems.
When a command is used, the log message includes the user who ran it, the command, the guild it was run in (or "in DMs" when used as a user app), and the options it was given. Option values are cut to 100 characters, and mentions and markdown in them are escaped.
When the bot is added to or removed from a guild, the log message includes the guild's name and the bot's new guild count.
These log messages never ping anyone.
