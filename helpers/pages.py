import html

import markdown


def render_markdown(text: str) -> tuple[str, list[dict]]:
    md = markdown.Markdown(
        extensions=["fenced_code", "tables", "toc"],
        extension_configs={"toc": {"toc_depth": "2-3"}},
    )
    content = md.convert(text)

    headings = []
    for token in md.toc_tokens:
        headings.append(
            {"id": token["id"], "name": html.unescape(token["name"]), "level": 2},
        )
        headings.extend(
            {"id": child["id"], "name": html.unescape(child["name"]), "level": 3}
            for child in token["children"]
        )
    return content, headings
