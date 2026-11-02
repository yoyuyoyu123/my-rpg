#!/bin/sh
set -eu
if [ "$(id -u)" = 0 ]; then
  case "${WUJI_DATA_DIR:-/data}" in
    /data|/data/*) ;;
    *) echo 'Container data must be mounted below /data' >&2; exit 1 ;;
  esac
  mkdir -p "${WUJI_DATA_DIR:-/data}"
  chown -R wuji:wuji "${WUJI_DATA_DIR:-/data}"
  exec gosu wuji "$@"
fi
exec "$@"
