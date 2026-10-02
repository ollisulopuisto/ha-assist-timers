#!/usr/bin/env bash
# Render tools/icon.svg to the integration's brand icons (transparent PNG, 256 and 512 px).
set -euo pipefail
cd "$(dirname "$0")/.."
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
out=custom_components/assist_timer_ring/brand
for scale in 1 2; do
  name=icon.png; [ "$scale" = 2 ] && name=icon@2x.png
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --default-background-color=00000000 \
    --force-device-scale-factor=$scale --window-size=256,256 --screenshot="$out/$name" "file://$PWD/tools/icon.svg" >/dev/null 2>&1
  echo "wrote $out/$name"
done
