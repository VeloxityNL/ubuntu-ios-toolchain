#!/usr/bin/env bash
# Regenerate the golden corpus with Apple's ibtool, on a Mac with Xcode (read-only use).
#   tar -C tests/ibtool -cf - src | ssh mac "$(cat tests/ibtool/compile-golden.sh)" | tar -C tests/ibtool -xf -
# Reads a tar of src/ on stdin, writes a tar of golden/ on stdout. The commands are the ones Xcode 27.0
# runs for NetNewsWire's iOS target (iPhone + iPad, iOS 17.0): src/<Module>/... compiles with
# --module <Module> (no module for files directly in src/); a storyboard compiles into a
# --compilation-directory, then --link copies it into golden/, keeping its .lproj directory.
set -euo pipefail
w=$(mktemp -d -t ibtool-golden)
trap 'rm -rf "$w"' EXIT
cd "$w"
tar -xf -
common=(--errors --warnings --notices)
target=(--target-device iphone --target-device ipad --minimum-deployment-target 17.0
        --output-format human-readable-text)
find src -name '*.storyboard' -o -name '*.xib' | sort | while read -r f; do
  name=$(basename "${f%.*}")
  rel=${f#src/}
  module=(); [ "$rel" != "${rel#*/}" ] && module=(--module "${rel%%/*}")
  lproj=$(basename "$(dirname "$f")"); case "$lproj" in *.lproj) ;; *) lproj= ;; esac
  # Per-module output roots: NetNewsWire keeps the legacy golden/<lproj> layout
  # (committed paths); every other module nests under golden/<Module> so equal
  # storyboard names (two Base.lproj/Main.storyboards) cannot overwrite.
  mod=${rel%%/*}; [ "$mod" = "$rel" ] && mod=
  root=; if [ -n "$mod" ] && [ "$mod" != NetNewsWire ]; then root=$mod; fi
  sub="$root${lproj:+/$lproj}"; sub="${sub#/}"
  mkdir -p "golden/$sub" "stage/$sub"
  case "$f" in
    *.storyboard)
      # --link keeps the input's .lproj parent, so compile into stage/<lproj> and link into golden/.
      xcrun ibtool "${common[@]}" "${module[@]}" --output-partial-info-plist "stage/$sub/$name-SBPartialInfo.plist" \
        --auto-activate-custom-fonts "${target[@]}" "$f" --compilation-directory "stage/$sub" >&2
      xcrun ibtool "${common[@]}" "${module[@]}" "${target[@]}" --link "golden/$root" \
        "stage/$sub/$name.storyboardc" >&2 ;;
    *.xib)
      xcrun ibtool "${common[@]}" "${module[@]}" --output-partial-info-plist "stage/$sub/$name-PartialInfo.plist" \
        --auto-activate-custom-fonts "${target[@]}" --compile "golden/$sub/$name.nib" "$f" >&2 ;;
  esac
done
xcrun ibtool --version --output-format xml1 >&2
tar -cf - golden
