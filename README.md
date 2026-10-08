<img width="5943" height="3967" alt="amanda-frank-e4ING8JYKgI-unsplash" src="https://github.com/user-attachments/assets/3bf10ab4-1206-456f-8837-1511bbce186d" />

# Melvin
Melvin is a Discord app written with **discord.py**. It's a demonstration of community driven consistency towards the Discord bot space, and it's open to [contributions](https://github.com/saltgranule/Melvin).
It has moderation, audit logging, welcome messages, server stats, timezones, thanks, and a set of user utilities. Servers can turn each module on or off and change its settings, either with commands in Discord or from the dashboard on the website.

## Requirements
- Python 3.14 or newer (specific syntax)
- The packages in `requirements.txt`

## Setup
clone the repo, set up a venv, run a quick pip install -r requirements.txt in root, and fill out any environment variables.

| Variable | What it's for |
|----------|---------------|
| `TOKEN` | The bot token, this is obviously a requirement |
| `SECRET_KEY` | Signs the website's session cookies. Without it, dashboard logins reset every restart. |
| `DISCORD_CLIENT_SECRET` | The application's OAuth2 secret, for dashboard logins. |
| `DASHBOARD_REDIRECT_URI` | The OAuth2 redirect, ending in `/dashboard/callback`. Dashboard logins need this and the secret. |
| `DISCORD_CLIENT_ID` | The application id. Defaults to Melvin's own. |
| `GITHUB_TOKEN` | Optional. Raises GitHub's rate limit for the contributors shown on the home page. |
| `GROQ` | The Groq API key for the AI commands. |
| `HOST`, `PORT` | Where the website listens. Defaults to `0.0.0.0` and `3005`. |
| `SESSION_COOKIE_SECURE` | Set to `false` to test dashboard logins over plain http. Defaults to `true`. |
| `FLASK_DEBUG` | Set to `true` for Flask's debug mode. |


The bot and the website share their databases and files in the `data/` directory

## Contributing
Every file in `cogs/` is a module, and is loaded unless it lacks a setup function, or begins with an underscore. `cogs/_template.py` is a blank module to start from, and `docs/developers.md` explains how modules, settings, and the dashboard all work. Each module should have a docs page in `docs/` (not required, but helpful if you plan to contrib)
