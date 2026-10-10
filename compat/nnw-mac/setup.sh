#!/usr/bin/env bash
# Check out NetNewsWire at the tested commit and generate a macOS adapter with
# tools/xcodeproj2xtool.py (the Mac app target; the iOS adapter lives in
# compat/nnw/setup.sh).
#
# Three patches, all mechanical:
# 1. Shared ObjC category members (NSOpenPanel.acceptOPML,
#    WKPreferences._developerExtrasEnabled) become Swift shims - ObjC sources
#    do not build on Linux and the bridging header is inert there.
# 2. Swift files that use AppKit types without importing Cocoa get one
#    `import Cocoa` after the header comment block. Xcode injects those
#    imports through the bridging header; SwiftPM does not. The rule scans the
#    files, nothing is hand-listed.
# 3. RSCore's two package-declared AppKit xibs (WebViewWindow,
#    IndeterminateProgressWindow) are removed from its .process resources:
#    the Linux ibtool compiles only the UIKit golden subset and fails closed
#    on AppKit nibs. One warning per file; a separate track is writing the
#    AppKit nib compiler.
#
# Usage: compat/nnw-mac/setup.sh DIR
#   BUNDLE_ID overrides the app's bundleID (the project's
#   ORGANIZATION_IDENTIFIER placeholder resolves to com.ranchero).
#   then, with the darwin Swift SDK registered:
#     S=$HOME/.swiftpm/swift-sdks/darwin.artifactbundle
#     cd DIR/omarchy-xtool && ulimit -n 65536
#     XCODE_EXTRA_PLATFORM_FOLDERS=$S/Developer/Platforms PATH=$S/toolset/bin:$PATH \
#       swift build -c release --build-system swiftbuild \
#       --triple arm64-apple-macosx --toolset $S/toolset-swb.json
set -euo pipefail
here=$(dirname "$(readlink -f "$0")")
dir=${1:?usage: setup.sh DIR}
NNW=8c322c287bec510a2ee0ebd0487e0481ad45ad82

git clone -q https://github.com/Ranchero-Software/NetNewsWire "$dir"
git -C "$dir" checkout -q "$NNW"

# NetNewsWire's own prebuild step (Xcode runs it as a build phase): expand
# Sources/Secrets/SecretKey.swift.gyb.
bash "$dir/buildscripts/updateSecrets.sh"

# 2. Rule-based `import Cocoa` for AppKit-using files without an import.
python3 - "$dir" <<'PY'
import os, re, sys
root = sys.argv[1]
fixed = 0
for base in ("Mac", "Shared", "Modules"):
    for b, dirs, files in os.walk(os.path.join(root, base)):
        dirs[:] = [d for d in dirs if d not in (".build", ".git")]
        for fn in files:
            if not fn.endswith(".swift"):
                continue
            p = os.path.join(b, fn)
            s = open(p, encoding="utf-8").read()
            if "import Cocoa" in s or "import AppKit" in s:
                continue
            if not re.search(r"\bNS[A-Z]", s):
                continue
            lines = s.split("\n")
            i = 0
            while i < len(lines) and (lines[i].startswith("//") or lines[i].strip() == ""):
                i += 1
            lines.insert(i, "import Cocoa")
            open(p, "w").write("\n".join(lines))
            fixed += 1
print(f"import Cocoa: {fixed} files patched")
PY

# 1. Swift shims for the excluded ObjC category members.
cat > "$dir/Mac/ObjCPrivateShims.swift" <<'EOF'
// Linux adapter: Swift replacements for the target's ObjC-only category
// members (ObjC sources do not build on Linux; the bridging header is inert).
// Same API and semantics as Mac/NSOpenPanel+Extras.m and
// Mac/WKPreferencesPrivate.h.

import ObjectiveC
import WebKit

extension NSOpenPanel {
	// https://github.com/Ranchero-Software/NetNewsWire/issues/4840
	// The deprecated allowedFileTypes is deliberate: the OPML UTI is not
	// reliable, so pin the file extensions.
	func acceptOPML() {
		allowedFileTypes = ["opml", "xml"]
	}
}

nonisolated(unsafe) private var developerExtrasKey: UInt8 = 0

extension WKPreferences {
	// Private WebKit property; the Darwin SDK hides it. Store the flag on the
	// object so get/set round-trip (the WebKit-internal effect is not wired).
	var _developerExtrasEnabled: Bool {
		get { objc_getAssociatedObject(self, &developerExtrasKey) as? Bool ?? false }
		set { objc_setAssociatedObject(self, &developerExtrasKey, newValue, .OBJC_ASSOCIATION_RETAIN) }
	}
}
EOF

# 3. Drop AppKit xibs from local packages. SwiftPM auto-detects .xib under a
# target dir even when undeclared, so the entries must move to the target's
# `exclude:` - removal alone does not stop the IB compiler.
python3 - "$dir" <<'PY'
import glob, os, re, sys
for p in sorted(glob.glob(os.path.join(sys.argv[1], "Modules/*/Package.swift"))):
    s = open(p, encoding="utf-8").read()
    blocks = [(m.group(1), m.start(), m.end()) for m in
              re.finditer(r"\.target\(\s*\n\s*name:\s*\"([^\"]+)\""
                          r".*?(?=\.target\(|\.executableTarget\(|\.testTarget\(|\Z)",
                          s, re.S)]
    for name, start, end in blocks:
        body = s[start:end]
        paths = re.findall(r'\.process\("([^"]+\.(?:xib|storyboard))"\)', body)
        if not paths:
            continue
        new_body = re.sub(r"^[ \t]*\.process\(\"[^\"]+\.(?:xib|storyboard)\"\),?\n",
                          "", body, flags=re.M)
        ex = ", ".join(f'"{x}"' for x in paths)
        if "exclude:" in new_body:
            new_body = new_body.replace("exclude: [",
                                        f"exclude: [\n\t\t\t{ex},", 1)
        else:
            new_body = re.sub(r"(\.target\(\s*\n\s*name:\s*\"[^\"]+\",\s*\n)",
                              rf"\1\t\t\texclude: [{ex}],\n",
                              new_body, count=1)
        s = s[:start] + new_body + s[end:]
        for x in paths:
            print(f"warning: {os.path.basename(os.path.dirname(p))}: excluded "
                  f"AppKit IB file {x} (Linux ibtool cannot compile it)")
        # SwiftPM generates Bundle.module only for targets with resources.
        # If the target's sources still reference it, shim the accessor.
        src_dir = os.path.join(os.path.dirname(p), "Sources", name)
        uses = any("Bundle.module" in open(os.path.join(b, f), encoding="utf-8", errors="replace").read()
                   for b, _d, fs in os.walk(src_dir) for f in fs if f.endswith(".swift"))
        if uses and re.search(r"resources:\s*\[\s*\]", new_body):
            shim = os.path.join(src_dir, "LinuxBundleModule.swift")
            with open(shim, "w") as f:
                f.write(
                    "// Linux adapter: the target's resources were excluded\n"
                    "// (AppKit IB files); SwiftPM then omits the Bundle.module\n"
                    "// accessor the sources still reference.\n"
                    "import Foundation\n\n"
                    "extension Bundle {\n"
                    "\tstatic let module: Bundle = Bundle(for: BundleToken.self)\n"
                    "\tprivate final class BundleToken {}\n"
                    "}\n")
            print(f"warning: {os.path.basename(os.path.dirname(p))}: wrote "
                  "Bundle.module shim for target " + name)
    if s != open(p, encoding="utf-8").read():
        open(p, "w").write(s)
PY

# 3b. The Xcode project links some local products statically twice and
# suppresses the diagnostic with DISABLE_DIAMOND_PROBLEM_DIAGNOSTIC = YES
# (NetNewsWire_project.xcconfig). SwiftPM exposes no override channel, so
# give every local package's primary library product the repo's own
# `type: .dynamic` convention (Account, RSCore already declare it).
python3 - "$dir" <<'PY'
import glob, os, re, sys
fixed = 0
for p in sorted(glob.glob(os.path.join(sys.argv[1], "Modules/*/Package.swift"))):
    s = open(p, encoding="utf-8").read()
    # Primary product only: the first .library( gets type: .dynamic when it
    # does not declare a type yet.
    new = re.sub(
        r"(\.library\(\s*\n\s*name:\s*\"[^\"]+\",\s*\n)(?!\s*type:)",
        r"\1\t\t\ttype: .dynamic,\n",
        s, count=1)
    if new != s:
        open(p, "w").write(new)
        fixed += 1
print(f"local packages made dynamic: {fixed}")
PY

python3 "$here/../../tools/xcodeproj2xtool.py" "$dir/NetNewsWire.xcodeproj" \
    --target NetNewsWire ${BUNDLE_ID:+--bundle-id "$BUNDLE_ID"}
