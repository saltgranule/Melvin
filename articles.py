import datetime
import functools
import html
import math
from pathlib import Path

import markdown

ARTICLES_DIR = Path(__file__).resolve().parent / "articles"
WORDS_PER_MINUTE = 200


def _front_matter(text: str) -> tuple[dict, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    meta = {}
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return meta, "\n".join(lines[i + 1 :])
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip().lower()] = value.strip()
    return {}, text


def _date(value: str) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None


@functools.lru_cache(maxsize=64)
def _parse(path: Path, _mtime: float) -> dict:
    meta, body = _front_matter(path.read_text(encoding="utf-8"))
    md = markdown.Markdown(
        extensions=["fenced_code", "tables", "toc"],
        extension_configs={"toc": {"toc_depth": "2-3"}},
    )
    content = md.convert(body)

    headings = []
    for token in md.toc_tokens:
        headings.append({"id": token["id"], "name": html.unescape(token["name"]), "level": 2})
        headings.extend(
            {"id": child["id"], "name": html.unescape(child["name"]), "level": 3}
            for child in token["children"]
        )

    date = _date(meta.get("date", ""))
    return {
        "slug": path.stem,
        "title": meta.get("title") or path.stem.replace("-", " ").replace("_", " ").title(),
        "author": meta.get("author", ""),
        "date": date,
        "date_label": f"{date.day} {date:%B %Y}" if date else "",
        "summary": meta.get("summary", ""),
        "thumbnail": meta.get("thumbnail", ""),
        # special contrib list for changelog articles
        "contributors": [c.strip() for c in meta.get("contributors", "").split(",") if c.strip()],
        "minutes": max(1, math.ceil(len(body.split()) / WORDS_PER_MINUTE)),
        "content": content,
        "headings": headings,
    }


def _paths() -> list[Path]:
    if not ARTICLES_DIR.is_dir():
        return []
    return [p for p in ARTICLES_DIR.glob("*.md") if not p.name.startswith("_")]


def all_articles() -> list[dict]:
    articles = [_parse(p, p.stat().st_mtime) for p in _paths()]
    return sorted(articles, key=lambda a: (a["date"] or datetime.date.min, a["title"]), reverse=True)


def get(slug: str) -> dict | None:
    if slug.startswith("_"):
        return None
    path = ARTICLES_DIR / f"{slug}.md"
    return _parse(path, path.stat().st_mtime) if path.is_file() else None
