#!/bin/sh
# Optional user-local launcher, no admin permissions required.
set -eu
HERE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
BIN="$HERE/APO_TIMIMO/APO_TIMIMO"
ICON="$HERE/app-icon.png"
if [ ! -x "$BIN" ]; then
    echo 'Не найден исполняемый файл АПО.ТИМИМО.' >&2
    exit 1
fi
mkdir -p "$HOME/.local/share/applications"
DEST="$HOME/.local/share/applications/apo-timimo.desktop"
cat > "$DEST" <<EOF
[Desktop Entry]
Type=Application
Name=АПО.ТИМИМО
GenericName=Аудит программного обеспечения
Exec="$BIN"
Icon=$ICON
Terminal=false
Categories=System;Utility;
EOF
chmod 755 "$DEST"
echo "Создан ярлык: $DEST"
