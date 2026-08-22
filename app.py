import subprocess
import sys

from flask import Flask, render_template
from globals import PRIMARY, SECONDARY, TERTIARY, QUATERNARY

app = Flask(__name__)

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


@app.route("/")
def home():
    return render_template("index.html", active="home", theme=THEME)


@app.route("/docs")
def docs():
    return render_template("index.html", active="docs", theme=THEME)


if __name__ == "__main__":
    start_bot()

    try:
        app.run(host="0.0.0.0", port=3005, debug=True, use_reloader=False)
    finally:
        if bot_process is not None:
            bot_process.terminate()