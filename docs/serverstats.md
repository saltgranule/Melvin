# Server Stats Documentation
Message, voice, and member totals for a guild, shown on the dashboard. The module has no commands.

## What's counted
The bot keeps totals for the whole guild, one row per hour. It never keeps who sent what, what was said, or who was in voice.

| Total | How it's counted |
|------|--------------|
| Messages | Every message sent in the guild, except by bots and apps. Messages are counted in memory and saved once a minute. |
| Voice minutes | Once a minute, every member in a voice or stage channel adds one minute, except bots and anyone in the guild's AFK channel. |
| Members | The guild's member count, saved once a minute so each hour keeps its latest count. |

Counting is part of the Server Stats module. When the module is turned off with `/modules` or the dashboard, nothing new is counted in that guild. Totals that were already saved are kept.

## Storage
Totals are stored in a SQLite database at `data/server_stats.db`, in a table called `guild_stats`. Each row holds a guild id, the hour it covers, the number of messages and voice minutes in that hour, and the latest member count. The table is created automatically when the cog loads, if it does not already exist.
Rows older than 31 days are deleted once an hour, so the longest range always has complete data.

## Dashboard page
The Server Stats page is in the sidebar of a server's dashboard. It has four cards at the top, for total messages, total voice minutes, member count, and net growth, and two charts below them.
The first chart stacks messages and voice minutes, so the height of each point is the two added together. The second chart shows the member count. Hovering over or tapping a point shows how long ago it was and its totals, and the charts can also be focused with Tab and stepped through with the left and right arrow keys.
The time range can be switched between 24 hours, 7 days, and 30 days.
When the module is turned off, the page shows a red banner saying nothing new is being counted, along with the totals saved before then.

| Range | Most points |
|------|------|
| 24 hours | 24 |
| 7 days | 7 |
| 30 days | 30 |

Each point covers an hour, a quarter of a day, or a day, using the shortest one that fits the range into its points. A guild with only a few days of data starts its charts from its first count instead of the start of the range, so it still gets a detailed chart. For example, two days of data in the 30 day range shows quarter day points.
