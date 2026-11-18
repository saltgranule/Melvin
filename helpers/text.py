import codecs
import re

LOOKALIKES = {
    "a": "a4@",
    "e": "e3",
    "i": "i1!|l",
    "o": "o0",
    "s": "s5$z",
    "g": "g69",
    "t": "t7+",
}
OFFENSIVE = tuple(
    codecs.decode(word, "rot13")
    for word in (
        "avttre",
        "avttn",
        "snttbg",
        "snt",
        "ergneq",
        "genaal",
        "xvxr",
        "puvax",
        "fcvp",
        "jrgonpx",
        "pbba",
        "qlxr",
        "ornare",
        "tbbx",
        "enturnq",
        "gbjryurnq",
    )
)
LINK = re.compile(r"(?:https?://|discord(?:app)?\.(?:gg|com/invite)/)\S+", re.IGNORECASE)


def _term(word: str) -> str:
    letters = r"[\W_]?".join(
        f"[{re.escape(LOOKALIKES.get(char, char))}]+" for char in word
    )
    end = r"(?:e?[s5$z])?(?![a-z])" if len(word) <= 4 else r"\w*"
    return rf"(?<![a-z]){letters}{end}"


OFFENSIVE_PATTERN = re.compile("|".join(map(_term, OFFENSIVE)), re.IGNORECASE)


def truncate(text: str, length: int) -> str:
    return text[: length - 3] + "..." if len(text) > length else text


def censor(text: str) -> str:
    text = LINK.sub("[link]", text)
    return OFFENSIVE_PATTERN.sub(lambda match: "*" * len(match.group(0)), text)
