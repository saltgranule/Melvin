# Contributing to Melvin

Melvin is open source and community managed. Anything you are not sure on please refer to the [support server](https://discord.gg/77XcneC4D).

## Setup
Bot side: Refer to `.env.example` on necessary secrets, `GROQ` and `GITHUB_TOKEN` are not necessary except for testing relevant cogs where you will get an error thrown in your face anyway > entrance `main.py`
Site side: entrance `app.py`, note this would also start the bot

## Layout
Cogs: Each module in its own file and in the cogs directory, there's a `template.py` if you are unsure on how to start, helpers should go into the cog file rather than a shared file, there's also a helpers directory for if you think the helper really should be shared.
UI: Shared UI module for Discord
Docs: Would be very nice if you can do your own documentation, even if you vibedocument it it would be great, `developers.md` explains some common queries if you are stuck

## Code style
- Please match code around you
- Code's ruffed and cleaned, try not to shit the formatting, silence if needed
- Discussion is preferred before adding new dependencies, if you really think you need it

## AI Usage
AI is an amazing and groundbreaking piece of technology for coding and it would be absolute stupidity not to embrace such technology. However we are stupid people.

## Bugs and suggestions
You can open an issue/feature request directly on the repository, we would prefer if you join the support server for issues regarding security or general exploitabilities 

## License and policies
By contributing, you agree that your work is released under the same terms as the rest of the project. See [legal/](legal/) for Melvin's terms and privacy policy, which changes that handle user data have to follow.
