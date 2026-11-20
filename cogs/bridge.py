import json
import logging

from discord.ext import commands

log = logging.getLogger(__name__)

ACTIONS = {}


def action(name):
    def register(func):
        ACTIONS[name] = func
        return func

    return register


def _reply(request_id, *, result=None, error=None):
    reply = {"jsonrpc": "2.0", "id": request_id}
    if error:
        reply["error"] = {"code": error[0], "message": error[1]}
    else:
        reply["result"] = result
    return json.dumps(reply).encode() + b"\n"


class BridgeCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def handle(self, line: bytes) -> bytes:
        # json-rpc 2.0
        try:
            request = json.loads(line)
        except ValueError:
            return _reply(None, error=(-32700, "Parse error"))
        if (
            not isinstance(request, dict)
            or request.get("jsonrpc") != "2.0"
            or not isinstance(request.get("method"), str)
        ):
            return _reply(None, error=(-32600, "Invalid Request"))

        request_id = request.get("id")
        params = request.get("params", {})
        func = ACTIONS.get(request["method"])
        if func is None:
            reply = _reply(request_id, error=(-32601, "Method not found"))
        elif not isinstance(params, dict):
            reply = _reply(request_id, error=(-32602, "Invalid params"))
        else:
            try:
                reply = _reply(request_id, result=await func(self.bot, params))
            except Exception:
                log.exception("Bridge method %s failed", request["method"])
                reply = _reply(request_id, error=(-32603, "Internal error"))
        return reply if "id" in request else b""


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BridgeCog(bot))
