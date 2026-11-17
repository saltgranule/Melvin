---
title: Changelog 16/11/26
author: saltgranule
date: 2026-11-16 15:45
summary: Changelog for Melvin as of 16/11/2026
thumbnail: media/bot/boosted1.png
contributors: Fantastic-Fanta, ImKajii, Saltgranule
---

## boosts and the dashboard
### boost

Melvin can now thank your boosters, it's literally just the welcome module but for boosts, with the bot stuff dropped

- new boost module, set it up with /boost config or the dashboard, and check how it looks with /boost preview
- same options as welcome, a channel, the message, an image and two link buttons, just without the bot toggle since bots can't boost anyway
- every welcome placeholder works here too, with the {date_...} ones using the time they started boosting instead of when they joined
- discord only tells us about a members first boost, so stacking a second boost on top won't send another message

### welcome

- welcome and boost now share code, read _greeting.py for more info on that in our github repo
- the giant wall of placeholders in the message description has moved into its own panel beside the settings, more on that below

### info

- /info server now shows the server description, and how many boosters the server has next to the boost count, thanks to Kajii for this

## the dashboard

The config pages were getting quite long and cluttered, so i've spent some time tidying them up.

- settings that belong together now sit side by side instead of stacking, like the link button labels and links on welcome and boost
  - this also applies to Audit Logs, Auto-Publish, Moderation, Starboard, Style and Thanks, audit logs especially went from six rows of channels down to three
- welcome and boost have a new side panel listing every placeholder and what it does, rather than one massive paragraph - i'll likely append other config pages with this later down the line if need be
- the image setting is now one block, with the preview on top and the upload and a remove button along the bottom, rather than a checkbox underneath, removing visual clutter by the stacked elements
  - hitting remove dims the image and turns into an undo button, nothing actually gets removed until you save

## articles

- new articles are now posted to the articles channel in the support server automatically, so you don't have to keep checking the site, it's also an announcement channel, so you can follow it into your own server
- the [what's melvin?](/articles/melvin) article is up, a bit of history on how melvin came to be (this was because we realized there actually isn't anything currently that described melvin in great detail.)
- the commit activity chart got a re-render and will probably get a few more

## smaller changes

- servers that drop out during a discord outage no longer show up as melvin being removed from them in our logs (private.py), thanks to Fanta for tracking that one down
- the website no longer has a chance of reading the bots stats while they're halfway through being written
