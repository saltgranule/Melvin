import json


def encode_request(action: str, args: dict | None = None) -> bytes:
    return json.dumps({"action": action, "args": args or {}}).encode() + b"\n"


def decode_reply(line: bytes) -> object:
    return json.loads(line)
