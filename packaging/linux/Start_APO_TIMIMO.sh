#!/bin/sh
set -eu
HERE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
exec "$HERE/APO_TIMIMO/APO_TIMIMO" "$@"
