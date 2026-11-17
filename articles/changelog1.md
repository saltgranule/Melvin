---
title: Changelog 15/11/26
author: saltgranule
date: 2026-11-15 21:15
summary: Changelog for Melvin as of 15/11/2026
thumbnail: media/thumbnail/fox-walking-wide.png
contributors: Fantastic-Fanta, ImKajii, FinestPerfectionism, Saltgranule
---

## welcome placeholders and branding
### welcome messages

Welcome messages have a lot more to work with now.

- {member_name}, {member_username}, {member_no_ping}, {member_created} and {server_name} placeholders, thanks to Fantastic Fanta
- join messages only ping the member if the message actually uses {member}
- placeholders are filled in a single pass, so a display name containing a placeholder no longer gets expanded twice, also Fanta
- {date_t} through {date_R} placeholders, one for every [discord timestamp style](https://discord.com/developers/docs/reference#message-formatting-timestamp-styles) (f, F, d, D, t, T, s, S, R), thanks to Kajii, with the timestamp idea suggested by FinestPerfectionism

### moderation

The mod module can now gate accounts from joining based on their account age.

- account age gate, turn it on in /mod config or the dashboard and pick a minimum age from 1 hour up to 30 days.
  - accounts younger than that are DMed when they can rejoin, then kicked, and the kick is logged as a case in the moderation log
  - bots are never gated, Kicking requires permissions, please ensure Melvin has them to use this feature...
- joining now has two stages, a member is only admitted once they pass the gate, so the welcome message and auto-role wait for that and gated accounts never get a welcome event or a role event, thanks to Fanta  for pointing this out
- Removed discord.JS is.kickable, & is.bannable from Dino's commit > should fix failing kick & ban commands.

### branding

- new link previews for the home page, docs and status, each a riso print of a different fox
  - link previews now use discords component embeds, so shared links look like the rest of melvin
- melvins emoji is now the wobbling fox
- style now defaults to Tempo, Solid, in melvins orange (F4A261)
- /melvin has been trimmed down to Add Me, Support and Website becuase and i quote 'this is pmoism' - Fanta

### smaller changes

- articles are live, this page and the [commit activity](/articles/commit-activity) article included
- the dashboard now only saves config images once the whole form is valid, so a failed save no longer replaces your image while dropping everything else (fixed with Fable 5.2, more on that in the [claude docs](/docs/claude))

## the redesign

The home page is now a login panel similar to my older projects, this is just an experiment to see if it has any sort of impact on user churn or growth. i do have to credit Anthropic and Claude's design team here, i took major inspiration from their UX flow specifically from Claude.ai's login panel. The navbar's been rebuilt with a resources menu for docs, status, help and donations, and the footer's been redesigned to match, with a few animated branding bits scattered throughout both.

Sitewide there's new fonts, Geist from vercel, with Geist Serif for headers, and buttons are flatter with softer corners that square off when you hover them (experimented with newer squircles here). The docs also include a short note on how claude was used for the module documentation, and there's a temporary [donations](/donations) page with more on the page itself.
