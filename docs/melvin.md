# Melvin Core Documentation
Commands that aren't part of a cog group, and the status page.

## help command
Path: `/help`
Take a peek at Melvin's commands.

**Parameters**
None.

**Behavior**
The command defers its response, then replies with the help banner and the commands of the first command group, each with its description.
A select menu underneath switches between command groups. Only groups that have commands are listed, and in a guild, groups from modules turned off with `/modules` are left out.

## melvin command
Path: `/melvin`
Here's Melvin.

**Parameters**
None.

**Behavior**
The command defers its response, then replies with a short description of the bot and how many guilds it's in, against its current goal of 100.
Link buttons are shown underneath for adding the bot, the support server, the website, the status page, and the GitHub repo.

## Status page
The status page on the website shows each shard's gateway and API latency, the bot's uptime, and the guild and user counts.
Latency is checked every minute, and the guild and user counts every 30 minutes. Each chart shows the 14 most recent checks.
Hovering over or tapping a chart shows the reading at that point. Charts can also be focused with Tab and stepped through with the left and right arrow keys.
The notice at the top of the page states whether everything appears normal, slow, or unresponsive. It's considered slow when gateway latency is over 400ms or API latency is over 800ms, and unresponsive when there hasn't been a check in the last 5 minutes.

## Dashboard
The dashboard on the website lets you manage Melvin in your servers after logging in with Discord.
Logging in only asks Discord for your name, avatar, and server list. Your Discord login is kept on Melvin's server, and your browser only holds a random session id. Logging out ends the session straight away, and sessions end on their own after 7 days.
After logging in, the dashboard lists every server where you're the owner, an Administrator, or have Manage Server. Servers that already have Melvin come first and open that server's page. The rest link to adding Melvin.
A server's page has a sidebar for its settings. The Modules section has a switch for each module, which turns it on or off for that server. Changes save straight away and apply in Discord within a few seconds.
Before saving a change, the dashboard checks with Discord that you still have Manage Server in that server. If you've lost it, or Discord can't be reached, nothing is saved and the page says why.
Your server list is refreshed from Discord every couple of minutes, so losing Manage Server in a server removes it from your list shortly after.
