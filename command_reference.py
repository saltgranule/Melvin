"""The reference shown beside the command editor.

Every function in command_engine.FUNCTIONS is listed here, and the tests check that
the examples still give the results written next to them.
"""

FUNCTION_GROUPS = (
    (
        "Text",
        (
            ("upper", "{text}", "Capital letters.", "$upper{hello} → HELLO"),
            ("lower", "{text}", "Lower case.", "$lower{HELLO} → hello"),
            ("title", "{text}", "Capitalises each word.", "$title{hi there} → Hi There"),
            ("trim", "{text}", "Removes spaces at the ends.", "$trim{  hi  } → hi"),
            ("reverse", "{text}", "Backwards.", "$reverse{abc} → cba"),
            ("len", "{text}", "Number of characters.", "$len{hello} → 5"),
            ("count", "{a,b,c}", "Items in a comma list.", "$count{a,b,c} → 3"),
            (
                "index",
                "{a,b,c|n}",
                "Item number n in a comma list. Negative counts from the end.",
                "$index{red,green,blue|2} → green",
            ),
            (
                "replace",
                "{text|find|new}",
                "Swaps `find` for `new`.",
                "$replace{a-b|-|+} → a+b",
            ),
            (
                "repeat",
                "{text|times}",
                "Repeats up to 20 times.",
                "$repeat{ha|3} → hahaha",
            ),
            (
                "contains",
                "{text|part}",
                "1 if it has the part, else 0. Ignores capitals.",
                "$contains{Hello|ell} → 1",
            ),
            (
                "default",
                "{value|fallback}",
                "The value, or the fallback if empty.",
                "$default{$2|nobody} → nobody",
            ),
        ),
    ),
    (
        "Numbers",
        (
            (
                "math",
                "{expression}",
                "Arithmetic with + - * / // % ** and brackets. `error` if it fails.",
                "$math{(2 + 3) * 4} → 20",
            ),
            ("sum", "{a|b|...}", "All the numbers added together.", "$sum{1|2|3} → 6"),
            ("min", "{a|b|...}", "The smallest number.", "$min{4|2|9} → 2"),
            ("max", "{a|b|...}", "The largest number.", "$max{4|2|9} → 9"),
            ("abs", "{number}", "Without its sign.", "$abs{-7} → 7"),
            (
                "round",
                "{number|places}",
                "To a whole number, or to that many decimal places.",
                "$round{2.567|2} → 2.57",
            ),
        ),
    ),
    (
        "Random",
        (
            (
                "rand",
                "{low-high}",
                "Random whole number in the range, inclusive.",
                "$rand{1-6} → 3",
            ),
            ("pick", "{a|b|c}", "One option at random.", "$pick{red|green} → red or green"),
            (
                "shuffle",
                "{a|b|c}",
                "Options in random order.",
                "$shuffle{a|b|c} → c, a, b",
            ),
            (
                "roll",
                "{2d6}",
                "Total of the dice. Up to 20 dice, 1000 sides.",
                "$roll{2d6} → 7",
            ),
            (
                "chance",
                "{percent}",
                "1 with that chance, else 0.",
                "{if $chance{30}}lucky{endif}",
            ),
        ),
    ),
    (
        "Time",
        (
            (
                "until",
                "{seconds}",
                "Relative time from now, like \"in an hour\".",
                "$until{3600}",
            ),
        ),
    ),
    (
        "Mentions and roles",
        (
            ("member", "{id}", "A mention of a member.", "$member{123456789012345678}"),
            ("role", "{id}", "A mention of a role.", "$role{123456789012345678}"),
            ("channel", "{id}", "A link to a channel.", "$channel{123456789012345678}"),
            (
                "addrole",
                "{member|role}",
                "Gives the role after posting. Needs Manage Roles.",
                "$addrole{$user|<@&123456789012345678>}",
            ),
            (
                "removerole",
                "{member|role}",
                "Takes the role after posting. Needs Manage Roles.",
                "$removerole{$1|<@&123456789012345678>}",
            ),
        ),
    ),
)

VARIABLES = (
    ("$1, $2, ...", "The argument in that position."),
    ("$2+", "That argument and every argument after it."),
    ("$*", "Every argument."),
    ("$$", "A literal $."),
    ("$user", "Mentions whoever used it."),
    ("$username", "Display name, no mention."),
    ("$userid", "The person's ID."),
    ("$server", "The name of this server."),
    ("$serverid", "The ID of this server."),
    ("$members", "How many members the server has."),
    ("$time", "Date and time, in each reader's timezone."),
    ("$time:R", "Relative, like \"in 2 hours\". Also t, T, d, D, f, F."),
)

EMBED_KEYS = (
    ("title:", "Up to 256 characters.", "title: Welcome"),
    ("description:", "Up to 4096 characters. Can span lines.", "description: Read the rules."),
    ("url:", "Link on the title.", "url: https://example.com"),
    ("color:", "Side bar color, as hex.", "color: #F4A261"),
    ("image:", "Large picture, as a link.", "image: https://example.com/a.png"),
    ("thumbnail:", "Small corner picture, as a link.", "thumbnail: https://example.com/a.png"),
    ("footer:", "Bottom text. Up to 2048 characters.", "footer: Ask a mod"),
    ("field:", "A box. Up to 25. Name | value.", "field: Rule one | Be kind"),
)

CONTAINER_KEYS = (
    ("color:", "Side bar color, as hex.", "color: #F4A261"),
    ("button:", "Link button. Up to 5. Label | link.", "button: Rules | https://example.com"),
    ("{separator}", "Small divider.", "{separator}"),
    ("{separator:large}", "Large divider.", "{separator:large}"),
)

USAGE = (
    (
        "Start with a marker",
        [
            "Plain text unless the first line is {embed} or {container}.",
            "Lines without a key are text.",
            "A backslash makes a key plain text: \\Color: red",
        ],
    ),
    (
        "Arguments",
        [
            "Like amount:number:1-100 or reason?:text.",
            "Types: word, number, member, role, channel, text (last).",
            "A ? makes it optional. Quote a value to keep spaces.",
        ],
    ),
    (
        "Stored values",
        [
            "$score = $roll{2d6} saves a value for this run.",
            "The line itself isn't posted.",
            "Use it later as $score.",
        ],
    ),
    (
        "Conditions",
        [
            "{if $1 == word}yes{elif $1 == other}maybe{else}no{endif}",
            "Compare with ==, !=, <, >, <=, >=. A single = is an error.",
            "Put text with spaces in quotes: $1 == \"two words\"",
            "On its own, true unless empty or 0.",
        ],
    ),
    (
        "Role changes",
        [
            "Put $addrole{member|role} on its own line.",
            "Members and roles: a mention, an ID, or an argument.",
            "Up to 10. Skipped for roles above the user's or Melvin's.",
        ],
    ),
    (
        "Who can use it",
        [
            "Everyone, a permission like manage_messages, or a role.",
        ],
    ),
)


def build() -> dict:
    """Everything the reference template needs, as plain data."""
    return {
        "groups": [
            {
                "title": title,
                "entries": [
                    {"name": name, "usage": usage, "description": text, "example": example}
                    for name, usage, text, example in items
                ],
            }
            for title, items in FUNCTION_GROUPS
        ],
        "variables": [{"name": name, "description": text} for name, text in VARIABLES],
        "embed": [{"key": key, "description": text, "example": example} for key, text, example in EMBED_KEYS],
        "container": [{"key": key, "description": text, "example": example} for key, text, example in CONTAINER_KEYS],
        "usage": [{"title": title, "lines": lines} for title, lines in USAGE],
    }
