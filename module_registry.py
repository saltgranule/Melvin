import importlib
import logging
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path

log = logging.getLogger(__name__)

COGS_DIR = Path(__file__).parent / "cogs"
MAX_CHANNELS = 25


@dataclass(frozen=True)
class Setting:
    key: str
    label: str
    description: str
    kind: str
    default: str | None = None
    choices: tuple[tuple[str, str], ...] = ()
    max_length: int = 100
    placeholder: str = ""
    permission: str | None = None
    channel_type: str = "text"
    minimum: int = 0
    maximum: int = 0
    group: str = "Settings"


@dataclass(frozen=True)
class Module:
    key: str
    label: str
    description: str
    settings: tuple[Setting, ...] = ()
    enabled_by_default: bool = True


def cog_names() -> list[str]:
    return [
        f"cogs.{path.stem}"
        for path in sorted(COGS_DIR.glob("*.py"))
        if not path.stem.startswith("_")
    ]


@cache
def modules() -> dict[str, Module]:
    found: dict[str, Module] = {}
    for name in cog_names():
        try:
            module = getattr(importlib.import_module(name), "MODULE", None)
        except Exception:
            log.exception("Couldn't import %s to look for its module", name)
            continue
        if not isinstance(module, Module):
            continue
        if module.key in found:
            msg = f"two cogs declare the module {module.key!r}"
            raise ValueError(msg)
        found[module.key] = module

    return dict(sorted(found.items(), key=lambda item: item[1].label.lower()))


class _View(Mapping):
    def __init__(self, build: Callable[[], dict]) -> None:
        self._build = cache(build)

    def __getitem__(self, key: str) -> object:
        return self._build()[key]

    def __contains__(self, key: object) -> bool:
        return key in self._build()

    def __iter__(self) -> Iterator[str]:
        return iter(self._build())

    def __len__(self) -> int:
        return len(self._build())


MODULES: Mapping[str, tuple[str, str]] = _View(
    lambda: {key: (m.label, m.description) for key, m in modules().items()},
)
CONFIG: Mapping[str, tuple[Setting, ...]] = _View(
    lambda: {key: m.settings for key, m in modules().items() if m.settings},
)
