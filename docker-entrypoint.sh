#!/bin/sh
set -eu

if [ "$(id -u)" = "0" ]; then
    chown -R character-relay:character-relay /data
    exec gosu character-relay "$@"
fi

exec "$@"
