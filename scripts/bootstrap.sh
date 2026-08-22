#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
umask 077

if [ -e .env ] || [ -e secrets/master_key ]; then
  echo "Bootstrap files already exist; refusing to overwrite" >&2
  exit 1
fi

KEY="$(python3 - <<'PY'
import base64
import secrets
print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
PY
)"
mkdir -p secrets
chmod 700 secrets
printf '%s\n' "$KEY" > secrets/master_key
chmod 600 secrets/master_key
cat > .env <<'EOF'
VAS_BIND_HOST=127.0.0.1
VAS_HTTP_PORT=8080
VAS_SECURE_COOKIES=false
EOF
chmod 600 .env
printf 'Created .env and secrets/master_key with mode 0600. Start with: docker compose up -d --build\n'
