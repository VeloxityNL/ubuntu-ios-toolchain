# IceCubesApp: Linux build and App Store .ipa, 2026-10-04

FINDINGS.md item 26. Host: omp-studio-local, clean Arch x86_64 root, user `builder`,
swift-bin 6.4.0, xtool 1.20.1, Xcode 27.0 (27A266a) SDK. Project:
Dimillian/IceCubesApp @ 9efcb16e720f337a401cf61c8e300dd043368282 with
`compat/icecubes/` (this repo).

## Pins

- OpenAppleMacros: `joshuaswarren/OpenAppleMacros` @ a517a2a60c05b69be4e28b3d51161b3cafaea589
  (branch `omarchy/foundation-macros`, on `omarchy/swiftdata` d10b0a9). Integration tests
  against Xcode 27 on a Mac: 113 pass, 0 fail (102 before, 11 new Foundation fixtures).
  swift-foundation macro sources from a211bea22b6fa5b041c37592aaf50c7b3db5c354.
- AssetKit: `joshuaswarren/AssetKit` @ 0521ae7c9d991713c0e9f4ade9f555815345dc0b
  (branch `omarchy/color-csi`): `swift test` 41 tests in 13 suites pass.

## Installer

`./install-toolchain.sh --repair` (re-registers the cached SDK, then installs actool,
xcstringstool and the OpenAppleMacros build):

```
Building OpenAppleMacrosServer a517a2a60c05b69be4e28b3d51161b3cafaea589 (first run: about 5 minutes)
...
real	6m47.772s
ddcb000b151b972fa885344f0c18ea80158d21c36fcce5268966b564a646a1e3  .../darwin.artifactbundle/OpenAppleMacrosServer
ddcb000b151b972fa885344f0c18ea80158d21c36fcce5268966b564a646a1e3  .../oam-a517a2a.../.build/release/OpenAppleMacrosServer
plugins: libFoundationMacros.so libFoundationModelsMacros.so libPreviewsMacros.so libSwiftDataMacros.so libSwiftUIMacros.so
```

## Plugin precedence probe

A `#Predicate` sample with the toolchain plugin, then with an empty
`libFoundationMacros.so` in the SDK plugin directory (OpenAppleMacros v1.3.0):

```
== toolchain
error: 'build_Arg' is not imported through module 'FoundationEssentials'
== stub
error: external macro implementation type 'FoundationMacros.PredicateMacro' could not be found for macro 'Predicate'; failed to load library plugin '.../iPhoneOS.platform/Developer/usr/lib/swift/host/plugins/libFoundationMacros.so' in plugin server '.../OpenAppleMacrosServer'; OpenAppleMacros: Could not find macros for module 'FoundationMacros'
```

With the fork: the same sample and a SwiftData `@Model` sample each print `Build complete!`.

## Compiler crash (fixed in compat/icecubes/Package.swift)

Before `Intents/ListEntity.swift` was excluded:

```
*** Program crashed: Bad pointer dereference at 0x0000000004800041 ***
#7 (anonymous namespace)::toFullyQualifiedTypeNameString[abi:cxx11](swift::Type const&) ConstExtract.cpp:0:0
#10 swift::writePropertyWrapperAttributes(...)
```

Rerun of the same frontend command with one protocol in the const-extract list:

```
.../Sources/IceCubesApp/Intents/ListEntity.swift:26:30: error: cannot find type 'ListsWidgetConfiguration' in scope
```

`IceCubesApp.xcodeproj` lists `ListEntity.swift` in a membership exception set for target
`IceCubesApp`.

## Clean ship run

Fresh copy of `omarchy-xtool` (no `.build`, no `xtool/`), after the installer run above:

```
$ ulimit -n 65536; XCODE_VERSION=27.0 XCODE_BUILD=27A266a APP_ICON=Icon ship.sh
== 1. Release build ==
Build complete! (266.16 secs)
== 2. App icon catalog ==
.../Merged.xcassets/Icon.appiconset: warning: dark and tinted icon variants are not compiled on Linux
== 3. App Store Info.plist keys ==
== 4. Distribution identity and signature ==
== 5. Package ==
wrote /home/builder/icecubes/omarchy-xtool-clean/xtool/IceCubesApp.ipa
== 6. Offline App Store validation ==
38/38 checks passed
```

`IceCubesApp.ipa`: 29,368,047 bytes, sha256
7fd0ee4ef480619d7dbfaf23cb915369e0cb2eddd21152226dfeecb18f84e3a9 (TEST identity).

On macstudio (Xcode 27.0, read-only, temp dir):

```
Authority=Apple Distribution: omarchy-apple-dev TEST (TEST000000)
TeamIdentifier=TEST000000
Sealed Resources version=2 rules=10 files=89
Payload/IceCubesApp.app: valid on disk
Payload/IceCubesApp.app: satisfies its Designated Requirement
```

`xcrun assetutil --info` on the app's `Assets.car`:

```
Icon Image marketing Icon 1024 1 5
Icon Image pad Icon 152 2 2
Icon Image pad Icon 167 2 3
Icon Image phone Icon 120 2 1
Icon Image phone Icon 180 2 4
Icon Image phone Icon 180 3 1
```

## Universal demo (iPad Pro icon)

`OmarchyDemo` with `UIDeviceFamily` `[1, 2]`: `38/38 checks passed`. The iPhone-only demo:
`35/35 checks passed`. `assetutil --info` on the universal demo's `Assets.car` lists pad
152 px (Icon Index 2) and pad 167 px (Icon Index 3), and four MultiSized Image entries.

## Fresh no-sudo user, swift.org tarball (FINDINGS 25 path)

`try-user-only.sh` (root removes fuse3, recreates user `nosudo`) then
`user-only-run.sh /opt/swift-6.4.0-RELEASE-ubi10.tar.gz /opt/xcode-sdk-src.tar ~/omarchy-apple-dev`.
The resources app now also has a SwiftData `Models.swift` (`@Model`, `@Attribute(.unique)`,
`@Relationship`, `#Predicate<Draft> { $0.content.count > 10 && $0.tags.isEmpty }`) and
`UIDeviceFamily` `[1, 2]`:

```
install exit=0
Building OpenAppleMacrosServer a517a2a60c05b69be4e28b3d51161b3cafaea589 (first run: about 5 minutes)
=== template build (01:40:35)
Build complete! (10.59 secs)
=== resources + ship app (01:40:48)
Build complete! (8.42 secs)
xtool/UORes.app/UORes_UORes.bundle/Assets.car
xtool/UORes.app/UORes_UORes.bundle/de.lproj/Localizable.strings
stamped com.example.UORes 1.0.0 (202610040141), iphoneos27.0 24A430, Xcode 27.0 27A266a
38/38 checks passed
```
