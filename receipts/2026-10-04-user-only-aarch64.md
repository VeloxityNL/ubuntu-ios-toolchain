# No-sudo install and ship on aarch64 Omarchy, 2026-10-04

FINDINGS.md item 28. Host: jwm1 (M1 MacBook Pro, Omarchy, Arch aarch64, kernel 7.1.12),
a new user with no sudo, 8 cores, 15 GiB RAM. Repo at 839a7a35d5985f30b42d426f0a32b02f2a41bc9e.
Inputs: swift.org `swift-6.4.0-RELEASE-ubi10-aarch64.tar.gz` (sha256
641931cd5fdd4d17e47b75b959ba21d67d0f5749cb7d14c854971b49e23bfbd2) and the Xcode 27.0 SDK
pieces (README, Route B). Procedure: the same script as the x86_64 no-sudo run
(`--curses-compat`, `install-toolchain.sh --user-only`, template build, resource app with
`.xcassets`, `.xcstrings` and a SwiftData `Models.swift` with `#Predicate`, `ship.sh`).

```
=== uname / limits (02:39:17)
aarch64
Swift version 6.4 (swift-6.4-RELEASE)
Target: aarch64-unknown-linux-gnu
install exit=0
xtool 1.20.1
darwin
Installed actool and xcstringstool into .../darwin.artifactbundle/Developer/Platforms/iPhoneOS.platform/Developer/usr/bin
Building OpenAppleMacrosServer a517a2a60c05b69be4e28b3d51161b3cafaea589 (first run: about 5 minutes)
=== template build (02:45:59)
Build complete! (7.03 secs)
xtool/UO.app/UO: Mach-O 64-bit arm64 executable, flags:<NOUNDEFS|DYLDLINK|TWOLEVEL|PIE>
=== resources + ship app (02:46:09)
Build complete! (6.96 secs)
xtool/UORes.app/UORes_UORes.bundle/Assets.car
xtool/UORes.app/UORes_UORes.bundle/de.lproj/Localizable.strings
stamped com.example.UORes 1.0.0 (202610040246), iphoneos27.0 24A430, Xcode 27.0 27A266a
38/38 checks passed
RUN_EXIT=0
```

`UORes.ipa`: 72,486 bytes, sha256 0b05d524674b5a18b03fc599db225850df949eb268f2b6a512fc173036b2ac42.
Apple's tools on a Mac (Xcode 27.0):

```
Payload/UORes.app/Info.plist: OK
TeamIdentifier=TEST000000
Payload/UORes.app: valid on disk
Payload/UORes.app: satisfies its Designated Requirement
```

Noise in the log, not failures: `xtool: .../curses-narrow-compat/libxml2.so.2: no version
information available` (the run exports LD_LIBRARY_PATH with the compat directory, so the xtool
AppImage sees the libxml2 alias), and the tarball's `swift runtime: unable to protect path to
swift-backtrace`.
