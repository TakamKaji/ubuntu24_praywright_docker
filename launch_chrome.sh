#!/usr/bin/env bash
set -euo pipefail

PROFILE_DIR="${NOTE_CHROME_PROFILE:-/data/chrome-profile}"
CDP_PORT="${NOTE_CDP_PORT:-9222}"
START_URL="${NOTE_START_URL:-https://note.com/}"

mkdir -p "${PROFILE_DIR}"

if python3 - "${CDP_PORT}" <<'PY'
import json
import sys
import urllib.request

port = sys.argv[1]
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1) as response:
        json.load(response)
except Exception:
    raise SystemExit(1)
raise SystemExit(0)
PY
then
    echo "Google Chrome は既に起動しています (CDP :${CDP_PORT})。"
    exit 0
fi

if pgrep -af "google-chrome.*--user-data-dir=${PROFILE_DIR}" >/dev/null 2>&1; then
    echo "Chrome process exists but CDP is unavailable. Stop that Chrome process before retrying." >&2
    exit 1
fi

find "${PROFILE_DIR}" -maxdepth 1 \
    \( -name 'SingletonLock' -o -name 'SingletonSocket' -o -name 'SingletonCookie' \) \
    -delete 2>/dev/null || true

exec google-chrome-stable \
    --no-sandbox \
    --user-data-dir="${PROFILE_DIR}" \
    --remote-debugging-port="${CDP_PORT}" \
    --remote-debugging-address=127.0.0.1 \
    "${START_URL}"
