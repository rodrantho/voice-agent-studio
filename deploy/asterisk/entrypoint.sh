#!/bin/sh
set -eu
umask 077
for name in PBX_HOST PBX_PORT SIP_EXTENSION SIP_AUTH_USERNAME SIP_PASSWORD RTP_START RTP_END ARI_PASSWORD; do
  eval "value=\${$name:-}"
  [ -n "$value" ] || { echo "Missing required variable: $name" >&2; exit 1; }
done
mkdir -p /etc/asterisk /generated
for f in pjsip.conf extensions.conf rtp.conf ari.conf http.conf modules.conf; do
  envsubst < "/templates/$f.template" > "/etc/asterisk/$f"
  chown asterisk:asterisk "/etc/asterisk/$f"
  chmod 600 "/etc/asterisk/$f"
done
for name in pjsip.conf extensions.conf rtp.conf; do
  if [ -s "/generated/$name" ]; then
    cp "/generated/$name" "/etc/asterisk/$name"
    chown asterisk:asterisk "/etc/asterisk/$name"
    chmod 600 "/etc/asterisk/$name"
  fi
done
/usr/sbin/asterisk -f -U asterisk -G asterisk -vvv &
ASTERISK_PID=$!
(
  while inotifywait -q -e close_write,move,create /generated >/dev/null 2>&1; do
    for name in pjsip.conf extensions.conf rtp.conf; do
      if [ -s "/generated/$name" ]; then
        cp "/generated/$name" "/etc/asterisk/$name"
        chown asterisk:asterisk "/etc/asterisk/$name"
        chmod 600 "/etc/asterisk/$name"
      fi
    done
    /usr/sbin/asterisk -rx 'core reload' >/dev/null 2>&1 || true
  done
) &
WATCH_PID=$!
trap 'kill "$WATCH_PID" "$ASTERISK_PID" 2>/dev/null || true' INT TERM EXIT
wait "$ASTERISK_PID"
