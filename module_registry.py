# finds the modules declared in cogs/. a module's cog sets MODULE at the top of its file.
# the website imports cog files without loading them, so cog files can't run anything on import

import importlib
import logging
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

COGS_DIR = Path(__file__).parent / "cogs"

# the most channels a channel select can hold
MAX_CHANNELS = 25


@dataclass(frozen=True)
class Setting:
    key: str
    label: str
    description: str
    # channel, channels, role, choice, text, url, color, or image
    kind: str
    default: str | None = None
    # (value, label) pairs for choice settings
    choices: tuple[tuple[str, str], ...] = ()
    max_length: int = 100
    placeholder: str = ""
    # a discord permission needed on top of Manage Server to change this setting
    permission: str | None = None
    # which channels channel settings offer, text, or any for text and announcement
    channel_type: str = "text"


@dataclass(frozen=True)
class Module:
    # the cog's command group name, or the cog's name if it has no commands
    key: str
    label: str
    description: str
    settings: tuple[Setting, ...] = ()


def cog_names() -> list[str]:
    # the cogs the bot loads. files starting with an underscore are skipped
    return [
        f"cogs.{path.stem}"
        for path in sorted(COGS_DIR.glob("*.py"))
        if not path.stem.startswith("_")
    ]


_modules: dict[str, Module] | None = None


def modules() -> dict[str, Module]:
    # built on first use rather than on import, since cogs import module_config,
    # which imports this file
    global _modules
    if _modules is not None:
        return _modules

    found: dict[str, Module] = {}
    for name in cog_names():
        try:
            module = getattr(importlib.import_module(name), "MODULE", None)
        except Exception:
            # a cog that fails to import is skipped, so the other modules still load
            log.exception("Couldn't import %s to look for its module", name)
            continue
        if not isinstance(module, Module):
            continue
        if module.key in found:
            msg = f"two cogs declare the module {module.key!r}"
            raise ValueError(msg)
        found[module.key] = module

    # sorted by label
    _modules = dict(sorted(found.items(), key=lambda item: item[1].label.lower()))
    return _modules


class _View(Mapping):
    # read-only dict over the modules, built once on first use. is_enabled reads it on
    # every message
    def __init__(self, build: Callable[[], dict]) -> None:
        self._build = build
        self._data: dict | None = None

    def _get(self) -> dict:
        if self._data is None:
            self._data = self._build()
        return self._data

    def __getitem__(self, key: str) -> object:
        return self._get()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._get())

    def __len__(self) -> int:
        return len(self._get())


# module key -> (label, description)
MODULES: Mapping[str, tuple[str, str]] = _View(
    lambda: {key: (m.label, m.description) for key, m in modules().items()},
)
# module key -> its settings, only for modules that have some
CONFIG: Mapping[str, tuple[Setting, ...]] = _View(
    lambda: {key: m.settings for key, m in modules().items() if m.settings},
)
