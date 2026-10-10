# Melvin Core Documentation
Commands that aren't part of a cog group, and the status page.

## /latency
View the bot's latency.

**Parameters**
None.

**Behavior**
The command defers its response, then replies with each shard's gateway latency and the time taken by a request to Discord's API, in milliseconds rounded to the nearest whole number.
If a shard isn't connected yet, its latency shows as N/A. If the API request fails, the API line says it's unavailable.

**Example**
Input: `/latency`
Output: `**Latency**`, followed by `Shard 0, 42ms` and `API, 120ms`.

## /help
Take a peek at Melvin's commands.

**Parameters**
None.

**Behavior**
The command defers its response, then replies with a page of commands, starting with the Melvin page for `/help`, `/latency`, and `/melvin`. Each command is listed with its description, and links to its section of the docs on the website. A Docs button next to the page's title links to the whole docs page.
A select menu underneath switches between pages. The other pages are one per command group, in alphabetical order, titled with the module's label where there is one. Only groups that have commands are listed, the private commands are left out, and in a guild, groups from modules turned off with `/modules` are left out too.

## /melvin
Here's Melvin.

**Parameters**
None.

**Behavior**
The command defers its response, then replies with a short description of the bot and a short clip of it.
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
The Server Stats section shows the server's messages, voice minutes, and members over the last 24 hours, 7 days, or 30 days. See the server stats documentation for how they're counted.
Before saving a change, the dashboard checks with Discord that you still have Manage Server in that server. If you've lost it, or Discord can't be reached, nothing is saved and the page says why.
Your server list is refreshed from Discord every couple of minutes, so losing Manage Server in a server removes it from your list shortly after.
