"""The custom command language: parsing, functions, and rendering.

Nothing in here touches the database, so the cog and the dashboard share it.
"""

import ast
import math
import operator
import random
import re
import time
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

import discord

from helpers.commands import CommandError, parse_args, snowflake, split_args
from ui import LargeSeparator, SmallSeparator

MESSAGE_TEXT_LENGTH = 2000
CONTAINER_TEXT_LENGTH = 4000
EMBED_TITLE_LENGTH = 256
EMBED_DESCRIPTION_LENGTH = 4096
EMBED_FIELD_NAME_LENGTH = 256
EMBED_FIELD_VALUE_LENGTH = 1024
EMBED_FOOTER_LENGTH = 2048
EMBED_FIELD_LIMIT = 25
BUTTON_LIMIT = 5
BUTTON_LABEL_LENGTH = 80
EMBED_KEYS = (
    "title",
    "description",
    "url",
    "color",
    "image",
    "thumbnail",
    "footer",
    "field",
)
CONTAINER_KEYS = ("color", "button")
KINDS = {"{embed}": "embed", "{container}": "container"}

FUNCTION_TEXT_LENGTH = 1000
MAX_EFFECTS = 10
MAX_DEPTH = 8
ROLL_MAX_DICE = 20
ROLL_MAX_SIDES = 1000
REPEAT_MAX = 20
MATH_MAX_LENGTH = 100
MAX_SECONDS = 31_536_000
ROUND_MAX_DIGITS = 10
PLAIN_NUMBER_LIMIT = 1e15

CONTROL_START = re.compile(r"\{(if|elif|else|endif)(?=[\s}])")
ASSIGN = re.compile(r"\$(?P<n>[a-z][a-z0-9_]{0,31})\s*=(?!=)\s*(?P<expr>.*)")
COMPARE = re.compile(r"(?P<left>.+?)\s*(?P<op>==|!=|<=|>=|<|>)\s*(?P<right>.+)")
BARE_EQUALS = re.compile(r"(?<![=!<>])=(?!=)")
ARG_REF = re.compile(r"\$(\d+)(\+)?")
NAME_REF = re.compile(r"\$([a-z][a-z0-9_]{0,31})")
TIME_STYLE = re.compile(r":([tTdDfFR])")
ESCAPED_KEY = re.compile(r"\\[A-Za-z]+\s*:")
LEGACY_FUNCTION = re.compile(r"\$(rand|pick|shuffle|roll|upper|lower)\[([^\]\n]*)\]")
LEGACY_MARKER = re.compile(r"^([ \t]*)\[(embed|container)\][ \t]*$", re.MULTILINE | re.IGNORECASE)
LEGACY_SEPARATOR = re.compile(
    r"^([ \t]*)\[separator(:(?:small|large))?\][ \t]*$",
    re.MULTILINE | re.IGNORECASE,
)
HEX_COLOR = re.compile(r"#?([0-9a-fA-F]{6})")
SEPARATOR = re.compile(r"\{separator(?::(?P<size>small|large))?\}", re.IGNORECASE)
ROLL = re.compile(r"(\d{1,2})d(\d{1,4})")
RANGE = re.compile(r"\s*(-?\d+)\s*-\s*(-?\d+)\s*")
STATEMENT_START = re.compile(r"\s*\$(addrole|removerole)\{")

BUILTIN_NAMES = frozenset(
    {"user", "username", "userid", "server", "serverid", "members", "time"},
)
COMPARISONS = {
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    ">": operator.gt,
    "<=": operator.le,
    ">=": operator.ge,
}


@dataclass
class TagBody:
    kind: str = "text"
    text: str = ""
    title: str | None = None
    description: str | None = None
    url: str | None = None
    color: int | None = None
    image: str | None = None
    thumbnail: str | None = None
    footer: str | None = None
    embed_fields: list[tuple[str, str]] = field(default_factory=list)
    items: list[tuple[str, str]] = field(default_factory=list)
    buttons: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class Run:
    """Everything a command knows while it's being filled in."""

    args: list[str]
    now: int
    user: str = "@member"
    user_id: str = "0"
    user_name: str = "member"
    server: str = "Your server"
    server_id: str = "0"
    members: int | None = None
    variables: dict[str, str] = field(default_factory=dict)
    effects: list[tuple[str, str, str]] = field(default_factory=list)


def _cut(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[: max(limit, 0)]
    return text[: limit - 3] + "..."


def _text_or(value: str, fallback: str) -> str:
    return value if value.strip() else fallback


def _join(current: str | None, text: str) -> str:
    return text if not current else f"{current}\n{text}"


def _unescaped(line: str) -> str | None:
    stripped = line.lstrip()
    if stripped.startswith("\\") and ESCAPED_KEY.match(stripped):
        return line.replace("\\", "", 1)
    return None


def _key(line: str, keys: tuple[str, ...]) -> tuple[str, str] | None:
    key, sep, value = line.partition(":")
    key = key.strip().lower()
    if sep and key in keys:
        return key, value.strip()
    return None


def _link(value: str, label: str) -> str:
    if not value.startswith(("http://", "https://")) or " " in value:
        msg = f"`{label}` must be a link starting with http:// or https://."
        raise CommandError(msg)
    return value


def _color(value: str) -> int:
    match = HEX_COLOR.fullmatch(value.strip())
    if match is None:
        msg = "Colors must be a hex code like `#F4A261`."
        raise CommandError(msg)
    return int(match[1], 16)


def _limit(value: str, limit: int, label: str) -> str:
    if len(value) > limit:
        msg = f"`{label}` can be at most {limit} characters."
        raise CommandError(msg)
    return value


def _parse_embed(lines: list[str]) -> TagBody:
    body = TagBody(kind="embed")
    current = None
    for number, line in enumerate(lines, start=2):
        try:
            escaped = _unescaped(line)
            if escaped is not None:
                if current != "description":
                    raise _unknown_embed_line(line)
                body.description = _join(body.description, escaped)
                continue

            found = _key(line, EMBED_KEYS)
            if found is not None:
                current, value = found
                _set_embed_key(body, current, value)
            elif current == "description":
                body.description = _join(body.description, line)
            elif line.strip():
                raise _unknown_embed_line(line)
        except CommandError as error:
            raise CommandError(f"Line {number}: {error}") from None

    if body.description is not None:
        _limit(body.description, EMBED_DESCRIPTION_LENGTH, "description")
    if body.title is None and body.description is None and not body.embed_fields:
        msg = "An embed needs a `title`, `description`, or `field`."
        raise CommandError(msg)
    return body


def _unknown_embed_line(line: str) -> CommandError:
    return CommandError(f"Unknown line in an embed: `{line.strip()[:40]}`.")


def _set_embed_key(body: TagBody, key: str, value: str) -> None:
    if key == "field":
        parts = [part.strip() for part in value.split("|")]
        if len(parts) != 2 or not all(parts):
            msg = "Fields look like `field: name | value`."
            raise CommandError(msg)
        body.embed_fields.append(
            (
                _limit(parts[0], EMBED_FIELD_NAME_LENGTH, "field name"),
                _limit(parts[1], EMBED_FIELD_VALUE_LENGTH, "field value"),
            ),
        )
        if len(body.embed_fields) > EMBED_FIELD_LIMIT:
            msg = f"An embed can have at most {EMBED_FIELD_LIMIT} fields."
            raise CommandError(msg)
    elif key == "description":
        body.description = _limit(value, EMBED_DESCRIPTION_LENGTH, "description")
    elif key == "title":
        body.title = _limit(value, EMBED_TITLE_LENGTH, "title")
    elif key == "footer":
        body.footer = _limit(value, EMBED_FOOTER_LENGTH, "footer")
    elif key == "color":
        body.color = _color(value)
    elif key == "url":
        body.url = _link(value, "url")
    elif key == "image":
        body.image = _link(value, "image")
    elif key == "thumbnail":
        body.thumbnail = _link(value, "thumbnail")


def _parse_container(lines: list[str]) -> TagBody:
    body = TagBody(kind="container")
    block: list[str] = []

    def flush() -> None:
        text = "\n".join(block).strip()
        if text:
            body.items.append(("text", text))
        block.clear()

    for number, line in enumerate(lines, start=2):
        try:
            escaped = _unescaped(line)
            if escaped is not None:
                block.append(escaped)
                continue

            found = _key(line, CONTAINER_KEYS)
            if separator := SEPARATOR.fullmatch(line.strip()):
                flush()
                body.items.append(((separator["size"] or "small").lower(), ""))
            elif found is not None and found[0] == "color":
                body.color = _color(found[1])
            elif found is not None and found[0] == "button":
                _add_button(body, found[1])
            else:
                block.append(line)
        except CommandError as error:
            raise CommandError(f"Line {number}: {error}") from None
    flush()

    texts = [text for kind, text in body.items if kind == "text"]
    if not texts:
        msg = "A container needs some text."
        raise CommandError(msg)
    if sum(len(text) for text in texts) > CONTAINER_TEXT_LENGTH:
        msg = f"A container's text can be at most {CONTAINER_TEXT_LENGTH} characters."
        raise CommandError(msg)
    return body


def _add_button(body: TagBody, value: str) -> None:
    parts = [part.strip() for part in value.split("|")]
    if len(parts) != 2 or not parts[0]:
        msg = "Buttons look like `button: label | link`."
        raise CommandError(msg)
    body.buttons.append((parts[0][:BUTTON_LABEL_LENGTH], _link(parts[1], "button")))
    if len(body.buttons) > BUTTON_LIMIT:
        msg = f"A container can have at most {BUTTON_LIMIT} buttons."
        raise CommandError(msg)


def parse_tag(raw: str) -> TagBody:
    text = raw.strip()
    if not text:
        return TagBody()

    lines = text.splitlines()
    marker = lines[0].strip().lower()
    if marker == "{embed}":
        return _parse_embed(lines[1:])
    if marker == "{container}":
        return _parse_container(lines[1:])
    if len(text) > MESSAGE_TEXT_LENGTH:
        msg = f"A plain text command can be at most {MESSAGE_TEXT_LENGTH} characters."
        raise CommandError(msg)
    return TagBody(text=text)


def tag_kind(raw: str) -> str:
    try:
        lines = flatten_tag(raw).strip().splitlines()
    except CommandError:
        lines = raw.strip().splitlines()
    first = lines[0].strip().lower() if lines else ""
    return KINDS.get(first, "text")


def migrate_brackets(text: str) -> str:
    text = LEGACY_FUNCTION.sub(lambda m: "$" + m[1] + "{" + m[2] + "}", text)
    text = LEGACY_MARKER.sub(lambda m: m[1] + "{" + m[2].lower() + "}", text)
    return LEGACY_SEPARATOR.sub(
        lambda m: m[1] + "{separator" + (m[2] or "").lower() + "}",
        text,
    )


def _matching_brace(text: str, start: int) -> int | None:
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    return None


def _controls(raw: str) -> list[tuple[int, int, str, str]]:
    found = []
    start = raw.find("{")
    while start != -1:
        match = CONTROL_START.match(raw, start)
        if match is None:
            start = raw.find("{", start + 1)
            continue
        close = _matching_brace(raw, start)
        if close is None:
            msg = f"A `{{{match[1]}` tag is missing its closing `}}`."
            raise CommandError(msg)
        found.append((start, close + 1, match[1], raw[match.end() : close].strip()))
        start = raw.find("{", close + 1)
    return found


def _check_name(name: str) -> None:
    if name in BUILTIN_NAMES or name in FUNCTIONS:
        msg = f"`${name}` is built in, so it can't be set. Pick another name."
        raise CommandError(msg)


def _check_blocks(raw: str) -> None:
    open_ifs: list[bool] = []
    for _, _, keyword, condition in _controls(raw):
        if keyword in ("if", "elif"):
            if not condition:
                msg = f"{{{keyword}}} needs a condition, like {{{keyword} $a > $b}}."
                raise CommandError(msg)
            if COMPARE.fullmatch(condition) is None and BARE_EQUALS.search(condition):
                msg = "Use == to compare two values in a condition, not a single =."
                raise CommandError(msg)
        elif condition:
            msg = f"{{{keyword}}} doesn't take a condition."
            raise CommandError(msg)

        if keyword == "if":
            open_ifs.append(False)
        elif keyword == "elif":
            if not open_ifs or open_ifs[-1]:
                msg = "{elif} has to come after an {if}, before any {else}."
                raise CommandError(msg)
        elif keyword == "else":
            if not open_ifs or open_ifs[-1]:
                msg = "{else} has to come after an {if}, and only once."
                raise CommandError(msg)
            open_ifs[-1] = True
        elif not open_ifs:
            msg = "{endif} has no matching {if}."
            raise CommandError(msg)
        else:
            open_ifs.pop()
    if open_ifs:
        msg = "An {if} is missing its {endif}."
        raise CommandError(msg)


def _operand(text: str, run: Run) -> str:
    stripped = text.strip()
    name = NAME_REF.fullmatch(stripped)
    if name is not None and name[1] not in run.variables and name[1] not in BUILTIN_NAMES:
        return ""
    value = expand(stripped, run).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _truth(condition: str, run: Run) -> bool:
    match = COMPARE.fullmatch(condition.strip())
    if match is None:
        return _operand(condition, run) not in ("", "0")
    left = _operand(match["left"], run)
    right = _operand(match["right"], run)
    try:
        a, b = int(left), int(right)
    except ValueError:
        a, b = left, right
    return COMPARISONS[match["op"]](a, b)


def _is_statement(line: str) -> bool:
    stripped = line.strip()
    match = STATEMENT_START.match(stripped)
    return match is not None and _matching_brace(stripped, match.end() - 1) == len(stripped) - 1


def _is_directive(line: str) -> bool:
    stripped = line.strip()
    return ASSIGN.fullmatch(stripped) is not None or _is_statement(stripped)


def _process(text: str, run: Run) -> str:
    kept = []
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if assign := ASSIGN.fullmatch(stripped):
            _check_name(assign["n"])
            run.variables[assign["n"]] = expand(assign["expr"], run).strip()
        elif _is_statement(stripped):
            expand(stripped, run)
        else:
            kept.append(line)
    return "".join(kept)


def flatten_tag(raw: str) -> str:
    kept = []
    position = 0
    for start, end, _, _ in _controls(raw):
        kept.append(raw[position:start])
        position = end
    kept.append(raw[position:])
    lines = ("" if _is_directive(line) else line for line in "".join(kept).splitlines())
    return "\n".join(lines)


def resolve_blocks(raw: str, run: Run) -> str:
    _check_blocks(raw)

    frames: list[dict[str, bool]] = []
    pieces: list[str] = []
    position = 0

    def live() -> bool:
        return not frames or frames[-1]["on"]

    for start, end, keyword, condition in _controls(raw):
        if live():
            pieces.append(_process(raw[position:start], run))
        position = end
        if keyword == "if":
            parent = live()
            taken = parent and _truth(condition, run)
            frames.append({"parent": parent, "taken": taken, "on": taken})
        elif keyword == "elif":
            frame = frames[-1]
            frame["on"] = frame["parent"] and not frame["taken"] and _truth(condition, run)
            frame["taken"] = frame["taken"] or frame["on"]
        elif keyword == "else":
            frame = frames[-1]
            frame["on"] = frame["parent"] and not frame["taken"]
            frame["taken"] = True
        else:
            frames.pop()
    if live():
        pieces.append(_process(raw[position:], run))
    return "".join(pieces)


def build(raw: str, run: Run) -> TagBody:
    """The layout a command produces for one run, with its values filled in."""
    return parse_tag(resolve_blocks(raw, run))


def _split_top(body: str) -> list[str]:
    parts, depth, current = [], 0, []
    for char in body:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        if char == "|" and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return parts


def _arg(run: Run, number: int, rest: bool) -> str:
    if number < 1 or number > len(run.args):
        return ""
    if rest:
        return " ".join(run.args[number - 1 :])
    return run.args[number - 1]


def _builtin(run: Run, name: str) -> str:
    if name == "user":
        return run.user
    if name == "username":
        return run.user_name
    if name == "userid":
        return run.user_id
    if name == "server":
        return run.server
    if name == "serverid":
        return run.server_id
    if name == "members":
        return "?" if run.members is None else str(run.members)
    return ""


def expand(text: str, run: Run, depth: int = 0) -> str:
    if depth > MAX_DEPTH or "$" not in text:
        return text

    out: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        if text[index] != "$":
            out.append(text[index])
            index += 1
            continue

        follow = text[index + 1 : index + 2]
        if follow == "$":
            out.append("$")
            index += 2
            continue
        if follow == "*":
            out.append(" ".join(run.args))
            index += 2
            continue
        if match := ARG_REF.match(text, index):
            out.append(_arg(run, int(match[1]), match[2] is not None))
            index = match.end()
            continue
        if match := NAME_REF.match(text, index):
            name, end = match[1], match.end()
            if name in FUNCTIONS and end < length and text[end] == "{":
                close = _matching_brace(text, end)
                if close is not None:
                    args = [expand(part, run, depth + 1) for part in _split_top(text[end + 1 : close])]
                    out.append(FUNCTIONS[name](run, args))
                    index = close + 1
                    continue
            if name == "time":
                style = TIME_STYLE.match(text, end)
                out.append(f"<t:{run.now}:{style[1] if style else 'f'}>")
                index = style.end() if style else end
                continue
            if name in BUILTIN_NAMES:
                out.append(_builtin(run, name))
                index = end
                continue
            out.append(run.variables.get(name, text[index:end]))
            index = end
            continue

        out.append("$")
        index += 1
    return "".join(out)



def _int(value: str, name: str) -> int:
    try:
        return int(value.strip())
    except ValueError:
        msg = f"${name} needs a whole number, not `{value.strip()[:20]}`."
        raise CommandError(msg) from None


def _number(value: str, name: str) -> float:
    try:
        number = float(value.strip())
    except ValueError:
        number = math.nan
    if not math.isfinite(number):
        msg = f"${name} needs a number, not `{value.strip()[:20]}`."
        raise CommandError(msg)
    return number


def _plain(number: float) -> str:
    if abs(number) >= PLAIN_NUMBER_LIMIT:
        return f"{number:.6g}"
    if float(number).is_integer():
        return str(int(number))
    return format(round(number, 6), "f").rstrip("0").rstrip(".")


def _need(args: list[str], count: int, name: str) -> None:
    if len(args) < count:
        msg = f"${name} needs {count} value{'s' if count != 1 else ''}, separated by |."
        raise CommandError(msg)


_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}


def _evaluate(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _evaluate(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        left, right = _evaluate(node.left), _evaluate(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("power too large")
        return _OPERATORS[type(node.op)](left, right)
    raise ValueError("unsupported")


def _fn_math(run: Run, args: list[str]) -> str:
    _need(args, 1, "math")
    expression = args[0].strip()
    if not expression or len(expression) > MATH_MAX_LENGTH:
        return "error"
    try:
        result = _evaluate(ast.parse(expression, mode="eval"))
    except (ValueError, SyntaxError, ZeroDivisionError, OverflowError, TypeError):
        return "error"
    if abs(result) > PLAIN_NUMBER_LIMIT:
        return "error"
    return _plain(result)


def _min_max(name: str, pick: object) -> object:
    def run_function(run: Run, args: list[str]) -> str:
        numbers = [_number(arg, name) for arg in args if arg.strip()]
        if not numbers:
            return ""
        return _plain(pick(numbers))

    return run_function


def _fn_sum(run: Run, args: list[str]) -> str:
    return _plain(sum(_number(arg, "sum") for arg in args if arg.strip()))


def _fn_round(run: Run, args: list[str]) -> str:
    _need(args, 1, "round")
    number = _number(args[0], "round")
    digits = _int(args[1], "round") if len(args) > 1 and args[1].strip() else 0
    digits = min(max(digits, 0), ROUND_MAX_DIGITS)
    if abs(number) >= PLAIN_NUMBER_LIMIT:
        return _plain(number)
    rounded = Decimal(repr(number)).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)
    return _plain(float(rounded))


def _fn_abs(run: Run, args: list[str]) -> str:
    _need(args, 1, "abs")
    return _plain(abs(_number(args[0], "abs")))


def _fn_rand(run: Run, args: list[str]) -> str:
    _need(args, 1, "rand")
    match = RANGE.fullmatch(args[0])
    if match is None:
        msg = "$rand needs a range like {1-6}."
        raise CommandError(msg)
    low, high = sorted((int(match[1]), int(match[2])))
    return str(random.randint(low, high))


def _fn_pick(run: Run, args: list[str]) -> str:
    options = [arg.strip() for arg in args if arg.strip()]
    return random.choice(options) if options else ""


def _fn_shuffle(run: Run, args: list[str]) -> str:
    options = [arg.strip() for arg in args if arg.strip()]
    random.shuffle(options)
    return ", ".join(options)


def _fn_roll(run: Run, args: list[str]) -> str:
    _need(args, 1, "roll")
    match = ROLL.fullmatch(args[0].strip().lower())
    if match is None:
        msg = "$roll needs dice like {2d6}."
        raise CommandError(msg)
    count = min(max(int(match[1]), 1), ROLL_MAX_DICE)
    sides = min(max(int(match[2]), 2), ROLL_MAX_SIDES)
    return str(sum(random.randint(1, sides) for _ in range(count)))


def _fn_chance(run: Run, args: list[str]) -> str:
    _need(args, 1, "chance")
    percent = min(max(_int(args[0], "chance"), 0), 100)
    return "1" if random.randint(1, 100) <= percent else "0"


def _fn_until(run: Run, args: list[str]) -> str:
    _need(args, 1, "until")
    seconds = min(max(_int(args[0], "until"), 0), MAX_SECONDS)
    return f"<t:{run.now + seconds}:R>"


def _mention(template: str, name: str) -> object:
    def run_function(run: Run, args: list[str]) -> str:
        _need(args, 1, name)
        value = snowflake(args[0])
        if value is None:
            msg = f"${name} needs a mention or an ID."
            raise CommandError(msg)
        return template.format(value)

    return run_function


def _role_change(verb: str) -> object:
    def run_function(run: Run, args: list[str]) -> str:
        _need(args, 2, verb)
        if len(run.effects) >= MAX_EFFECTS:
            msg = f"A command can change at most {MAX_EFFECTS} roles."
            raise CommandError(msg)
        run.effects.append((verb, args[0].strip(), args[1].strip()))
        return ""

    return run_function


def _text_function(transform: object) -> object:
    def run_function(run: Run, args: list[str]) -> str:
        return _cut(transform(args[0] if args else ""), FUNCTION_TEXT_LENGTH)

    return run_function


def _fn_replace(run: Run, args: list[str]) -> str:
    _need(args, 3, "replace")
    text, find, new = args[0], args[1], args[2]
    if not find:
        return text
    return _cut(text.replace(find, new), FUNCTION_TEXT_LENGTH)


def _fn_repeat(run: Run, args: list[str]) -> str:
    _need(args, 2, "repeat")
    count = min(max(_int(args[1], "repeat"), 0), REPEAT_MAX)
    return _cut(args[0] * count, FUNCTION_TEXT_LENGTH)


def _fn_contains(run: Run, args: list[str]) -> str:
    _need(args, 2, "contains")
    return "1" if args[1] and args[1].lower() in args[0].lower() else "0"


def _fn_default(run: Run, args: list[str]) -> str:
    _need(args, 2, "default")
    return args[0] if args[0].strip() else args[1]


def _fn_length(run: Run, args: list[str]) -> str:
    return str(len(args[0]) if args else 0)


def _fn_count(run: Run, args: list[str]) -> str:
    _need(args, 1, "count")
    return str(len([item for item in args[0].split(",") if item.strip()]))


def _fn_index(run: Run, args: list[str]) -> str:
    _need(args, 2, "index")
    items = [item.strip() for item in args[0].split(",") if item.strip()]
    position = _int(args[1], "index")
    if 1 <= position <= len(items):
        return items[position - 1]
    if -len(items) <= position <= -1:
        return items[position]
    return ""


FUNCTIONS = {
    "upper": _text_function(str.upper),
    "lower": _text_function(str.lower),
    "title": _text_function(str.title),
    "trim": _text_function(str.strip),
    "reverse": _text_function(lambda text: text[::-1]),
    "len": _fn_length,
    "count": _fn_count,
    "index": _fn_index,
    "replace": _fn_replace,
    "repeat": _fn_repeat,
    "contains": _fn_contains,
    "default": _fn_default,
    "math": _fn_math,
    "sum": _fn_sum,
    "min": _min_max("min", min),
    "max": _min_max("max", max),
    "abs": _fn_abs,
    "round": _fn_round,
    "rand": _fn_rand,
    "pick": _fn_pick,
    "shuffle": _fn_shuffle,
    "roll": _fn_roll,
    "chance": _fn_chance,
    "until": _fn_until,
    "member": _mention("<@{}>", "member"),
    "role": _mention("<@&{}>", "role"),
    "channel": _mention("<#{}>", "channel"),
    "addrole": _role_change("addrole"),
    "removerole": _role_change("removerole"),
}



def _color_value(value: int | None) -> discord.Color | None:
    return discord.Color(value) if value is not None else None


def render(
    body: TagBody,
    run: Run,
) -> tuple[str | None, discord.Embed | None, discord.ui.LayoutView | None]:
    def expanded(value: str) -> str:
        return expand(value, run)

    if body.kind == "embed":
        embed = discord.Embed(
            title=_cut(expanded(body.title), EMBED_TITLE_LENGTH) if body.title else None,
            description=(
                _cut(expanded(body.description), EMBED_DESCRIPTION_LENGTH)
                if body.description
                else None
            ),
            url=body.url,
            color=_color_value(body.color),
        )
        if body.image:
            embed.set_image(url=body.image)
        if body.thumbnail:
            embed.set_thumbnail(url=body.thumbnail)
        if body.footer:
            embed.set_footer(text=_cut(expanded(body.footer), EMBED_FOOTER_LENGTH))
        for name, value in body.embed_fields:
            embed.add_field(
                name=_text_or(_cut(expanded(name), EMBED_FIELD_NAME_LENGTH), "\u200b"),
                value=_text_or(_cut(expanded(value), EMBED_FIELD_VALUE_LENGTH), "\u200b"),
                inline=False,
            )
        return None, embed, None

    if body.kind == "container":
        container = discord.ui.Container(accent_color=_color_value(body.color))
        budget = CONTAINER_TEXT_LENGTH
        for kind, value in body.items:
            if kind == "small":
                container.add_item(SmallSeparator())
            elif kind == "large":
                container.add_item(LargeSeparator())
            else:
                text = _cut(expanded(value), budget)
                budget -= len(text)
                container.add_item(discord.ui.TextDisplay(_text_or(text, "\u200b")))
        if body.buttons:
            container.add_item(
                discord.ui.ActionRow(
                    *(
                        discord.ui.Button(
                            label=_text_or(_cut(expanded(label), BUTTON_LABEL_LENGTH), "Link"),
                            style=discord.ButtonStyle.link,
                            url=url,
                        )
                        for label, url in body.buttons
                    ),
                ),
            )
        view = discord.ui.LayoutView()
        view.add_item(container)
        return None, None, view

    return _text_or(expanded(body.text)[:MESSAGE_TEXT_LENGTH], "\u200b"), None, None


def preview_data(raw: str, run: Run) -> dict:
    """What the command would show, as plain data, for the dashboard's preview card."""
    body = build(raw, run)
    data: dict = {"kind": body.kind}
    if body.kind == "embed":
        data.update(
            title=expand(body.title, run) if body.title else "",
            description=expand(body.description, run) if body.description else "",
            color=f"#{body.color:06X}" if body.color is not None else None,
            fields=[
                {"name": expand(name, run), "value": expand(value, run)}
                for name, value in body.embed_fields
            ],
            footer=expand(body.footer, run) if body.footer else "",
            image=body.image,
            thumbnail=body.thumbnail,
            url=body.url,
        )
    elif body.kind == "container":
        data.update(
            blocks=[
                {"type": "text", "text": expand(value, run)}
                if kind == "text"
                else {"type": "separator", "size": kind}
                for kind, value in body.items
            ],
            color=f"#{body.color:06X}" if body.color is not None else None,
            buttons=[{"label": expand(label, run), "url": url} for label, url in body.buttons],
        )
    else:
        data["text"] = expand(body.text, run)
    data["effects"] = list(run.effects)
    return data


def send_kwargs(
    rendered: tuple[str | None, discord.Embed | None, discord.ui.LayoutView | None],
) -> dict:
    content, embed, view = rendered
    if view is not None:
        return {"view": view}
    kwargs: dict = {"content": content}
    if embed is not None:
        kwargs["embed"] = embed
    return kwargs



SAMPLE_VALUES = {
    "word": "word",
    "text": "some text",
    "member": "@member",
    "role": "@role",
    "channel": "#channel",
}


def sample_args(spec: str) -> list[str]:
    values = []
    for arg in parse_args(spec):
        if arg.kind == "number":
            values.append(str(arg.low if arg.low is not None else 1))
        else:
            values.append(SAMPLE_VALUES[arg.kind])
    return values


def sample_run(spec: str = "", sample_text: str = "") -> Run:
    values = split_args(sample_text) if sample_text.strip() else sample_args(spec)
    return Run(args=values, now=int(time.time()), members=1234)


def check_command(raw: str, spec: str = "") -> str | None:
    """The first problem with a command, or None if it's fine to save."""
    if not raw.strip():
        return "A command needs some text."
    try:
        _check_blocks(raw)
        parse_tag(flatten_tag(raw))
        preview_data(raw, sample_run(spec))
    except CommandError as error:
        return str(error)
    return None
