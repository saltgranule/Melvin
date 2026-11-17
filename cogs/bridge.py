import json

from discord.ext import commands

ACTIONS = {}


def action(name):
    def register(func):
        ACTIONS[name] = func
        return func

    return register


class BridgeCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def handle(self, line: bytes) -> bytes:
        request = json.loads(line)
        data = await ACTIONS[request["action"]](self.bot, request.get("args", {}))
        return json.dumps(data).encode() + b"\n"


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BridgeCog(bot))
