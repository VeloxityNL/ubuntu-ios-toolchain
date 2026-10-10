#!/usr/bin/env bash
# Check out IceCubesApp at the tested commit and generate its xtool adapter.
# Usage: [BUNDLE_ID=<id>] compat/icecubes/setup.sh DIR
# then: cd DIR/omarchy-xtool && ulimit -n 65536 && xtool dev build
set -euo pipefail
here=$(dirname "$(readlink -f "$0")")
dir=${1:?usage: setup.sh DIR}
ICECUBES=9efcb16e720f337a401cf61c8e300dd043368282

git clone -q https://github.com/Dimillian/IceCubesApp "$dir"
git -C "$dir" checkout -q "$ICECUBES"
python3 "$here/../../tools/xcodeproj2xtool.py" "$dir/IceCubesApp.xcodeproj" ${BUNDLE_ID:+--bundle-id "$BUNDLE_ID"}
