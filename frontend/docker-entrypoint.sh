#!/bin/sh
set -eu

escaped_api_url=$(printf '%s' "${API_BASE_URL:-}" | sed 's/\\/\\\\/g; s/"/\\"/g')
printf 'window.__VFE_DEVIZ_CONFIG__ = { API_URL: "%s" };\n' "$escaped_api_url" > /app/public/runtime-config.js
exec node server.js
