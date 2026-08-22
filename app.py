import subprocess
import sys
from pathlib import Path

import markdown
from flask import Flask, abort, render_template

from globals import PRIMARY, QUATERNARY, SECONDARY, TERTIARY

app = Flask(__name__)

DOCS_DIR = Path(app.root_path) / "docs"
bot_process = None


def start_bot():
    global bot_process
    bot_process = subprocess.Popen([sys.executable, "main.py"])


THEME = {
    "primary": PRIMARY,
    "secondary": SECONDARY,
    "tertiary": TERTIARY,
    "quaternary": QUATERNARY,
}


def get_docs_list():
    if not DOCS_DIR.is_dir():
        return []

    docs = []
    for path in sorted(DOCS_DIR.glob("*.md")):
        title = path.stem.replace("-", " ").replace("_", " ").title()
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
        docs.append({"slug": path.stem, "title": title})
    return docs


def render_doc(slug):
    path = DOCS_DIR / f"{slug}.md"
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    return markdown.markdown(text, extensions=["fenced_code", "tables"])


@app.route("/")
def home():
    return render_template("index.html", active="home", theme=THEME)


@app.route("/docs")
def docs_index():
    return render_template(
        "docs.html",
        active="docs",
        theme=THEME,
        docs=get_docs_list(),
        content=None,
        active_slug=None,
    )


@app.route("/docs/<slug>")
def docs_page(slug):
    content = render_doc(slug)
    if content is None:
        abort(404)
    return render_template(
        "docs.html",
        active="docs",
        theme=THEME,
        docs=get_docs_list(),
        content=content,
        active_slug=slug,
    )


if __name__ == "__main__":
    start_bot()

    try:
        app.run(host="0.0.0.0", port=3005, debug=True, use_reloader=False)
    finally:
        if bot_process is not None:
            bot_process.terminate()
