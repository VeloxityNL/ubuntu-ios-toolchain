#!/usr/bin/env bash
# tools/appintentsmeta.py against Xcode 27.0 (27A266a) output. Each case dir holds the
# .swiftconstvalues swiftc emitted (min, probeD: Xcode's swiftc; nnw: NetNewsWire's Linux build),
# the Info.plist, the Swift source (for reference) and golden/, the Metadata.appintents that Xcode's
# appintentsmetadataprocessor + appintentsnltrainingprocessor wrote from those const values.
# args pins the NLU archive timestamp to the golden one. Every file must be byte-identical.
# Needs Xcode's SiriSSUKitModel resources: SSU_RESOURCES, or the copy install-toolchain.sh keeps.
set -euo pipefail
here=$(dirname "$(readlink -f "$0")")
ssu=${SSU_RESOURCES:-$(ls -dt "$HOME"/.cache/xtool/darwin-*.xtoolsdk.SiriSSUKitModel 2>/dev/null | head -n1 || true)}
[ -d "$ssu" ] || { echo "no SiriSSUKitModel resources: set SSU_RESOURCES" >&2; exit 1; }
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT
status=0
for case in "$here"/*/; do
  name=$(basename "$case")
  mkdir "$out/$name"
  # shellcheck disable=SC2046
  python3 "$here/../../tools/appintentsmeta.py" $(cat "$case/args") --output "$out/$name" \
    --info-plist "$case/Info.plist" --ssu-resources "$ssu" --const-values "$case"/*.swiftconstvalues > /dev/null
  if diff -r "$case/golden" "$out/$name"; then
    echo "ok   $name: $(find "$case/golden" -type f | wc -l) files byte-identical to Xcode"
  else
    echo "FAIL $name"
    status=1
  fi
done
exit "$status"
