#!/usr/bin/env bash
# Check out Mastodon for iOS at the tested commit and generate its xtool adapter.
# Usage: BUNDLE_ID=<id> compat/mastodon/setup.sh DIR
#   then: cd DIR/omarchy-xtool && ulimit -n 65536 && xtool dev build
#   ship: cd DIR/omarchy-xtool && ship.sh   (prints APP_ICON=... to pass it)
#
# Two overlay changes, both applied before the generator runs; everything else
# is the stock project.
#
# 1. Nuke 10 -> 12 (FINDINGS.md 36). Mastodon pins Nuke from 10.3.1, which
#    resolves to 10.11.2, and 10.11.2 does not compile with Swift 6.4:
#    ImagePipeline.swift:286:47: cannot convert value of type
#    'Result<(data: Data, response: URLResponse?), ImagePipeline.Error>'
#    (Xcode 27 fails on it too). The pin moves to 12.x, which resolves to
#    12.9.0, the newest 12.x that compiles. Mastodon's only Nuke call site is
#    MastodonUI's AnimatedImage.swift, and in Nuke 12 the image-view API
#    (loadImage/cancelRequest) lives in the NukeExtensions module, so the call
#    site and the MastodonUI target dependency move with it.
#
# 2. The SwiftSoup diamond (FINDINGS.md 32/36). SwiftPM 6.4.0 rejects the
#    graph: "Swift package product 'SwiftSoup-product' is linked as a static
#    library by 'Mastodon-App-product' and 'MastodonSDKDynamic-product'" -
#    SwiftSoup reaches the app through MastoParse and the MastodonSDKDynamic
#    dylib through FaviconFinder. Xcode 27 builds the same graph by promoting
#    the shared static library to a dynamic variant so SwiftSoup is built
#    once; SwiftPM restored that only in release/6.4.2 (b3613845), which has
#    no release. The overlay removes the diamond the same way from the
#    project side: MastoParse (3 source files, Foundation + SwiftSoup, no
#    resources) is vendored into the MastodonSDK package as a target inside
#    MastodonSDKDynamic, so both SwiftSoup consumers sit in the dylib and the
#    app gets MastoParse as a module of the dynamic product it already
#    declares. The generator then omits the app's own MastoParse dependency
#    exactly as it omits Bodega ("already carried by MastodonSDKDynamic").
set -euo pipefail
here=$(dirname "$(readlink -f "$0")")
dir=${1:?usage: setup.sh DIR}
MAS=c52a63091abe557724a1e588149f3172466756e5
MP=ce10e6999a6ad886a400863429e4b3f3ca004bdd

if [ -d "$dir/.git" ]; then
	cur=$(git -C "$dir" rev-parse HEAD)
	if [ "$cur" != "$MAS" ]; then
		git -C "$dir" fetch -q origin "$MAS"
		git -C "$dir" checkout -q "$MAS"
	fi
else
	git clone -q https://github.com/mastodon/mastodon-ios "$dir"
	git -C "$dir" checkout -q "$MAS"
fi
if [ -e "$dir/omarchy-xtool/Package.swift" ]; then
	echo "error: $dir/omarchy-xtool already holds an adapter; move it away to regenerate" >&2
	exit 1
fi

# Overlay 1+2: patch MastodonSDK/Package.swift (see the header for why).
MPDIR="$dir/MastodonSDK/Vendor/MastoParse"
if [ ! -d "$MPDIR/.git" ]; then
	git clone -q https://github.com/mastodon/MastoParse.git "$MPDIR"
fi
git -C "$MPDIR" checkout -q "$MP"
python3 - "$dir/MastodonSDK/Package.swift" <<'PY'
import sys

path = sys.argv[1]
text = open(path, encoding="utf-8").read()

def sub(old, new):
	global text
	assert text.count(old) == 1, f"patch target not unique: {old!r}"
	text = text.replace(old, new)

# Nuke 12 (overlay 1)
sub('.package(url: "https://github.com/kean/Nuke.git", from: "10.3.1"),',
    '.package(url: "https://github.com/kean/Nuke.git", from: "12.0.0"),')
sub('                .product(name: "Nuke", package: "Nuke"),',
    '                .product(name: "Nuke", package: "Nuke"),\n'
    '                .product(name: "NukeExtensions", package: "Nuke"),')

# SwiftSoup diamond (overlay 2)
sub('let publicLibraryTargets = [\n    "CoreDataStack",',
    'let publicLibraryTargets = [\n    "MastoParse",\n    "CoreDataStack",')
sub('.package(url: "https://github.com/kean/Nuke.git", from: "12.0.0"),',
    '.package(url: "https://github.com/kean/Nuke.git", from: "12.0.0"),\n'
    '        .package(url: "https://github.com/scinfu/SwiftSoup.git", '
    '.upToNextMajor(from: "2.8.8")),')
sub('        .testTarget(',
    '        // MastoParse, vendored (see compat/mastodon/setup.sh): lives in\n'
    '        // MastodonSDKDynamic so SwiftSoup is linked once, into the dylib.\n'
    '        .target(\n'
    '            name: "MastoParse",\n'
    '            dependencies: [\n'
    '                .product(name: "SwiftSoup", package: "SwiftSoup"),\n'
    '            ],\n'
    '            path: "Vendor/MastoParse/Sources/MastoParse"\n'
    '        ),\n'
    '        .testTarget(')

open(path, "w", encoding="utf-8").write(text)
print("patched", path)
PY

# Overlay 1: the one Nuke call site. Nuke 12 moved loadImage/cancelRequest
# from the Nuke module to NukeExtensions.
sed -i -e 's/^import Nuke$/import Nuke\nimport NukeExtensions/' \
	-e 's/Nuke\.loadImage(/NukeExtensions.loadImage(/g' \
	-e 's/Nuke\.cancelRequest(/NukeExtensions.cancelRequest(/g' \
	"$dir/MastodonSDK/Sources/MastodonUI/SwiftUI/AnimatedImage.swift"

python3 "$here/../../tools/xcodeproj2xtool.py" "$dir/Mastodon.xcodeproj" ${BUNDLE_ID:+--bundle-id "$BUNDLE_ID"}
echo "next: cd $dir/omarchy-xtool && ulimit -n 65536 && xtool dev build"
