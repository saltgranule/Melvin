import enum

PRIMARY = "#f8b95c"
SECONDARY = "#6f9459"  # green
TERTIARY = "#bd3b44"  # red
QUARTERNARY = "#f8b95c"  # yellow
MELVIN_EMOJI = "<:Melvin:1538313845309706411>"
LOG_CHANNEL = 1535283504105922620
MELVIN_CROSS_EMOJI = "<:Cross:1538140651613462538>"
MELVIN_WARN_EMOJI = "<:Warn:1538140683389636618>"
MELVIN_MISC_EMOJI = "<:Alert:1538140718772658277>"
MELVIN_CHECK_EMOJI = "<:Checkmark:1538140630625292348>"
ERROR_CHANNEL = 1536683441616064532
INVITE_URL = "https://discord.gg/PfyKM7dyx4"
MELVIN_BANNER = "https://cdn.discordapp.com/attachments/1537874702146469988/1538311690775433266/New_Project.png?ex=6a8237e7&is=6a80e667&hm=79599bdfd26d5a1f6ab499996055a6ae6e3c7a9e8fab582db518b4dd66773072&"
MELVIN_HELP_BANNER = "https://cdn.discordapp.com/attachments/1537874702146469988/1538311472436748288/cmdbanneryellow.png?ex=6a8237b3&is=6a80e633&hm=7b1f806fd48cd994d0e267f66f42b242961383a0f6f4ce69a2b36f40849f0cfd&"
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
