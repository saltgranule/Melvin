import enum
from pathlib import Path

# where the bot and the website keep their databases and shared files. built from this
# file's location, so it's the same folder whichever directory melvin is started from
DATA_DIR = Path(__file__).parent / "data"

# colors
PRIMARY = "#f4a261"
SECONDARY = "#7EA861"  # green
TERTIARY = "#E86461"  # red
QUATERNARY = "#ffffff"  # white

# channels
LOG_CHANNEL = 1535283504105922620
ERROR_CHANNEL = 1536683441616064532

# status emojis
MELVIN_EMOJI = "<:MelvinEmoji:1540125757219803267>"
MELVIN_CROSS_EMOJI = "<:warningcirclefill:1547368137597653124>"
MELVIN_WARN_EMOJI = "<:warnyellow:1547364932368990208>"
MELVIN_MISC_EMOJI = "<:warnmisc:1547366223300264006>"
MELVIN_CHECK_EMOJI = "<:checkcirclefill:1547368139266723850>"

# filled emojis
THUMBS_UP = "<:thumbsupfill:1547368133763928114>"
THUMBS_DOWN = "<:thumbsdownfill:1547368136091893860>"

# white duotone emojis
THUMBS_UP_WHITE = "<:thumbsupduotone:1557697976669970523>"
THUMBS_DOWN_WHITE = "<:thumbsdownduotone:1557697975138910220>"
BROWSER = "<:browsersduotone:1548410087037477066>"
IMAGE = "<:imageduotone:1547366631284678676>"
TEXT = "<:textboxduotone:1547366633440284813>"
CLICK = "<:handpointingduotone:1547366634459766814>"

# status page icons
SHARD_ICON = "<:shard:1555862593749385276>"
API_ICON = "<:API:1555862891691778160>"

# links
INVITE_URL = "https://discord.gg/PfyKM7dyx4"
ADD_BOT_URL = "https://discord.com/oauth2/authorize?client_id=1468362201197973756"
MELVIN_GITHUB_URL = "https://github.com/saltgranule/Melvin"
WEBSITE_URL = "https://justmelvin.site"
MELVIN_BANNER = "https://cdn.discordapp.com/attachments/1537874702146469988/1541048056751849512/image.png?ex=6a8c2c58&is=6a8adad8&hm=a13f54c4349d9a4d2672fd6b90b544ca5b00d27964c28891d56a0e49e00cead1&"

# messages
ERROR_MESSAGE = f"**Something went wrong with that. Please [join the support server]({INVITE_URL}) to report this issue.**"


class DisplayNameFont(enum.Enum):
    bangers = 1  # unimplemented
    bio_rhyme = 2  # unimplemented
    cherry_bomb = 3
    chicle = 4
    compagnon = 5  # unimplemented
    museo_moderno = 6
    neo_castel = 7
    pixelify = 8
    ribes = 9  # unimplemented
    sinistre = 10
    default = 11
    zilla_slab = 12


class DisplayNameEffect(enum.Enum):
    solid = 1
    gradient = 2
    neon = 3
    toon = 4
    pop = 5
    glow = 6  # unimplemented
