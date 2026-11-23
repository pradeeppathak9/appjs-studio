#!/bin/sh
# Writes the app's runtime settings from the container's environment (see Dockerfile).
set -eu
key=$(printf '%s' "${APP_KEY:-}" | sed 's/[\\"]//g')
printf 'window.RESTYLE_CONFIG = { appKey: "%s" };\n' "$key" > /usr/share/nginx/html/config.js
[ -n "$key" ] || echo "restyle-web: APP_KEY is not set; the app can't reach Studio" >&2
