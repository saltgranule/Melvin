import enum

PRIMARY = "#f4a261"
SECONDARY = "#7EA861"  # green
TERTIARY = "#E86461"  # red
QUATERNARY = "#ffffff"  # white

LOG_CHANNEL = 1535283504105922620
ERROR_CHANNEL = 1536683441616064532

MELVIN_EMOJI = "<:MelvinEmoji:1540125757219803267>"
MELVIN_CROSS_EMOJI = "<:warningcirclefill:1547368137597653124>"
MELVIN_WARN_EMOJI = "<:warnyellow:1547364932368990208>"
MELVIN_MISC_EMOJI = "<:warnmisc:1547366223300264006>"
MELVIN_CHECK_EMOJI = "<:checkcirclefill:1547368139266723850>"
THUMBS_UP = "<:thumbsupfill:1547368133763928114>"
THUMBS_DOWN = "<:thumbsdownfill:1547368136091893860>"

IMAGE = "<:imageduotone:1547366631284678676>"
TEXT = "<:textboxduotone:1547366633440284813>"
CLICK = "<:handpointingduotone:1547366634459766814>"

INVITE_URL = "https://discord.gg/PfyKM7dyx4"
ERROR_MESSAGE = f"**Something went wrong with that. Please [join the support server]({INVITE_URL}) to report this issue.**"
MELVIN_BANNER = "https://cdn.discordapp.com/attachments/1537874702146469988/1541048056751849512/image.png?ex=6a8c2c58&is=6a8adad8&hm=a13f54c4349d9a4d2672fd6b90b544ca5b00d27964c28891d56a0e49e00cead1&"
MELVIN_HELP_BANNER = "https://cdn.discordapp.com/attachments/1537874702146469988/1540084821462884475/MNBCMD.png?ex=6a88ab42&is=6a8759c2&hm=9d4c248fff8eda006f93ae87e8965c00f5afdefd017b185e935edf7f3e663f9d&"
MELVIN_GITHUB_URL = "https://github.com/saltgranule/Melvin"


class DisplayNameFont(enum.Enum):
    bangers = 1  # Unimplemented
    bio_rhyme = 2  # Unimplemented
    cherry_bomb = 3
    chicle = 4
    compagnon = 5  # Unimplemented
    museo_moderno = 6
    neo_castel = 7
    pixelify = 8
    ribes = 9  # Unimplemented
    sinistre = 10
    default = 11
    zilla_slab = 12


class DisplayNameEffect(enum.Enum):
    solid = 1
    gradient = 2
    neon = 3
    toon = 4
    pop = 5
    glow = 6  # Unimplemented
