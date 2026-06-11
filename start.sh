#!/usr/bin/env bash
# Render Studio launcher (macOS / Linux) — run this once; the app installs
# the engine and models itself with one-click buttons in the browser.
set -e
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 was not found."
    if [[ "$(uname)" == "Darwin" ]]; then
        read -r -p "Install Apple's command line tools (includes Python)? [y/N] " yn
        [[ "$yn" == [yY]* ]] && xcode-select --install
    else
        echo "Install it with your package manager, e.g.: sudo apt install python3 python3-pip"
    fi
    exit 1
fi

echo "Checking app dependencies…"
python3 -m pip install -q -r requirements.txt

echo "Starting Render Studio at http://127.0.0.1:8500 (browser opens automatically)"
python3 -m backend.main
