# Privacy Policy
Last updated October 7, 2026.

This covers Melvin, the Discord bot, and its website, including the dashboard. It says what Melvin keeps, why, for how long, and who else sees any of it.

## What Melvin reads
Melvin sees what Discord shows a bot in the servers it's in, messages included. A few features use them as they come in.

- **Thanks** looks for words like "thanks", to credit whoever was thanked.
- **Server Stats** counts messages and time spent in voice, per server and per hour.
- **Audit Logs** posts edits, deletions, and member changes to a channel the server picks. Those posts live in that server's Discord channel.

## What Melvin keeps
Everything below is stored on the machine Melvin runs on.

| What | Why | How long |
|------|------|------|
| Server settings, like which modules are on, the welcome message, and uploaded welcome images | So each server works the way it was set up | Until they're changed. Welcome settings and images are deleted when Melvin leaves a server, other settings stay until someone asks for them to be removed |
| Moderation cases, with the member, the moderator, the action, and the reason | So moderators can look back at a member's history with `/case` | Until a moderator removes them |
| Your timezone, if you set one | So `/timezone` can show it | Until you run `/timezone reset` |
| How many times you've been thanked | For the thanks count | Until you ask for it to be removed |
| Hourly message, voice, and member totals for each server | For the dashboard's Server Stats page | 31 days |
| Which command was used, by whom, and in which server | To see which features get used | Until you ask for it to be removed |
| When you last asked the AI something | For the AI's hourly limit | One hour |
| Your dashboard login, see below | To keep you logged in | Until you log out, or 7 days |

Each time a command is used, Melvin also posts a note to its developer's private Discord channel, with who used it, where, and what they typed into it, cut short past 100 characters. It's how errors and abuse get caught.

## The dashboard
Logging in to the dashboard goes through Discord, which shares your basic account details and the list of servers you're in.

While you're logged in, Melvin keeps your user ID, display name, avatar, the token Discord gives it, and the servers you can manage. Your browser keeps a cookie with a random ID that points to all of that. Logging out deletes it straight away.

## Who else sees it
Melvin runs on Discord, so everything it does goes through Discord and follows [Discord's privacy policy](https://discord.com/privacy).

Some features send things to other services.

| Service | What it gets | When |
|------|------|------|
| [Groq](https://groq.com/privacy-policy/) | Your question | When you use the AI module |
| DuckDuckGo | Your question, as a web search | When you ask the AI to search the web |
| [cdnfonts](https://www.cdnfonts.com/) | Your IP address, like any site you load something from | When you open the website, for its font |

## What Melvin doesn't do
- Keep the messages it reads. Thanks and Server Stats only hold on to counts.
- Keep copies of audit logs. They exist in the server's own channel and nowhere else.
- Read your messages or act as you through the dashboard. The login only covers your account details and server list.
- Sell anything, share it for ads, or track you around the web.
- Run analytics on the website.

## Your choices
- A server can turn any module off, from `/modules` or the dashboard. Nothing new is collected for a module while it's off.
- Removing Melvin from a server stops it reading anything there.
- To see what Melvin has about you, or have it removed, ask in the [support server](https://discord.gg/PfyKM7dyx4).

## Changes
This policy is a work in progress and will be improved on. When it changes, the date at the top changes with it. Big changes get announced in the support server.
