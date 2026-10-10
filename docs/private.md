# Private Cog Documentation
Administrative and developer utilities. These are only for the bot's developers, and are left out of `/help`.
Command group name: `private`

## /private populate
Fill this server's stats with made up data.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| density | choice | yes | How much activity to make up, Low, Medium, or High. |

**Permissions**
Only the bot's owner can run this. Anyone else gets a "Gated" reply pointing them to the support server. Guild only.

**Behavior**
The command makes up 30 days of hourly messages, voice minutes, and member counts, then replaces the server's stats with them, so the Server Stats page has something to show. Activity follows a daily curve, is a bit higher on weekends, and the member count slowly grows with the odd dip.
Real stats for the server are overwritten, so this is meant for test servers. All replies are ephemeral.

**Example**
Input: `/private populate density: Medium`
Output: `**Server Stats Populated**`, followed by `Replaced this server's stats with 720 hours of medium density data.`

## Developer logs
The bot posts some events to a private log channel in its own development server, to help spot problems.
When a command is used, the log message includes the user who ran it, the command, the guild it was run in (or "in DMs" when used as a user app), and the options it was given. Option values are cut to 100 characters, and mentions and markdown in them are escaped.
When the bot is added to or removed from a guild, the log message includes the guild's name and the bot's new guild count.
These log messages never ping anyone.
