import itertools
import json

_ids = itertools.count(1)


class BridgeError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def encode_request(method: str, params: dict | None = None) -> bytes:
    request = {"jsonrpc": "2.0", "method": method, "params": params or {}, "id": next(_ids)}
    return json.dumps(request).encode() + b"\n"


def decode_reply(line: bytes) -> object:
    reply = json.loads(line)
    if "error" in reply:
        raise BridgeError(reply["error"]["code"], reply["error"]["message"])
    return reply["result"]
