# Contributing to Melvin

Melvin is open source and community managed. When in doubt, refer to Melvin's [support server](https://discord.gg/77XcneC4D)!

## Setup
- **Bot:** Refer to `.env.example` for necessary environment variables. The `GROQ` and `GITHUB_TOKEN` variables are not required, except for when testing the relevant cogs, in which an error will be raised. Entrance file is `main.py`.
- **Website:** Entrance file is `app.py`. Note that this also starts the bot.

## Layout
- **`/cogs`:** Each module has its own file under this directory. Refer to `template.py` if you are unsure on where to start when creating a module. Helpers should go into the respective cog file rather than a shared file. There is also a `/helpers` directory, if you think the helper should be shared.
- **`/ui`:** UI classes for Melvin.
- **`/docs`:**  Documentation for modules. Open to contributions. `developers.md` addresses some common questions if you are stuck.

## Formatting & Code Style
- Do your best to match the style of the rest of the codebase.
- Code is ruff-checked and ruff-formatted. You are free to silence as an absolute last resort.
- Minimize dependencies; discuss before adding any if you deem a new dependency necessary.

## AI Usage
While AI is a truly groundbreaking piece of technology for coding, we prefer that you do **not** make contributions with the usage of LLMs/agents.

## Bugs and Suggestions
You can open an issue/feature request directly on the repository. It's preferable you join the support server for issues regarding security/exploitations.

## License and Policies
By contributing, you agree that your work is released under the same terms as the rest of the project. See [legal/](legal/) for Melvin's terms and privacy policy, which changes that handle user data have to follow.
