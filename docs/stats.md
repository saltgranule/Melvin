# Stats Cog Documentation
Install and usage statistics for the bot.

## Storage
Stats are stored in a SQLite database at `data/stats.db`, in two tables. The `command_logs` table holds one row per completed command, with the command name, user id, guild id, and timestamp. The `daily_snapshots` table holds the guild and user install counts, recorded once a day. Both tables are created automatically when the cog loads, if they do not already exist.

## /stats
Display statistics about Melvin.

**Parameters**
None.

**Behavior**
The command replies with the following stats.

| Stat | Meaning |
|------|------|
| Guild Installs | How many guilds the bot is in. |
| User Installs | Discord's approximate count of users who added the bot as a user app. |
| Total Installs (Last 24h) | The change in guild and user installs combined, compared to roughly 24 hours ago. This can be negative. |
| Total Installs (All-Time) | Guild installs and user installs added together. |
| Commands Run (Last 24h) | Commands completed in the last 24 hours. |
| Commands Run (All-Time) | Commands completed since tracking started. |

**Example**
Input: `/stats`
Output: `**Melvin Stats**`, followed by the stats above.

## How stats are collected
Every successfully completed slash command is recorded. Commands that fail are not counted.
A snapshot of the install counts is taken every day at midnight UTC. The 24 hour install change compares against the snapshot closest to 24 hours ago. If no snapshots exist yet, one is taken when the bot starts.
