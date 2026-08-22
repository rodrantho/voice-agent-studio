#!/bin/sh
set -eu

install -d -o 10001 -g 10001 -m 0700 /tmp/vas-secrets
setpriv --reuid=10001 --regid=10001 --clear-groups test -w /data || {
  echo "/data is not writable by UID 10001" >&2
  exit 1
}
copy_secret() {
  variable="$1"
  eval "source_path=\${$variable:-}"
  [ -n "$source_path" ] || return 0
  [ -r "$source_path" ] || { echo "Unable to read $variable" >&2; exit 1; }
  destination="/tmp/vas-secrets/$(basename "$source_path")"
  cp "$source_path" "$destination"
  chmod 0400 "$destination"
  chown 10001:10001 "$destination"
  eval "$variable=\$destination"
  export "$variable"
}

copy_secret VAS_MASTER_KEY_FILE
exec setpriv --reuid=10001 --regid=10001 --clear-groups --bounding-set=-all --no-new-privs "$@"
