# IceCubesApp on xtool 1.20.1 + Swift 6.4, Arch x86_64 (2026-10-03)

Project: Dimillian/IceCubesApp at 9efcb16e720f337a401cf61c8e300dd043368282.
Adapter: `compat/icecubes/setup.sh DIR` (adds `omarchy-xtool/`, changes one line in
`Packages/DesignSystem/Package.swift`). Host: the clean Arch x86_64 root of
`2026-10-03-xtool-1.20-swift-6.4-x86_64.md`; SDK iPhoneOS 27.0 from Xcode 27.0 (27A266a).
Apple reference outputs come from Xcode 27.0's own tools on a Mac, used read-only.

## Build attempts, in order

| # | First error | Fix |
|---|---|---|
| 1 | `a resolved file is required when automatic dependency resolution is disabled ... 'emojitext' ... was resolved to 'fix-ios26' but now has a different revision-based requirement` | local checkout of the branch (one line) |
| 2 | `failed to launch. .../xtool/.xtool-tmp/actool is not an executable file` (12x), same for `xcstringstool` | Linux `actool`, `xcstringstool` in the SDK platform bin dir |
| 3 | `.../de.lproj/Localizable.strings no --inputencoding specified and could not detect encoding from input file` | `STRINGS_FILE_INPUT_ENCODING = utf-8` |
| 4 | `unable to open output file ... 'Too many open files'` (soft limit 1024) | `ulimit -n 65536` |
| 5 | `exactly one .xcassets input is supported, got 2` | actool merges catalogs |
| 6 | `Key 'color-space' not found ... label.colorset` (system color) | AssetKit fork: system colors |
| 7 | `Key 'color' not found ... AccentColor.colorset`, then `Unsupported asset type: avatar.heic` | actool leaves out what AssetKit cannot compile, with a warning (37) |
| 8 | `cannot find type 'StoreView' in scope` (RevenueCat, StoreKit + SwiftUI) | `-Xfrontend -enable-cross-import-overlays` in `toolset-swb.json` |
| 9 | `external macro implementation type 'SwiftDataMacros.PersistentModelMacro' could not be found for macro 'Model()'` | open (xtool#149) |

## Minimal repros on the template app

- `branch: "main"` dependency: the error of row 1; `from: "2.2.11"`: `Build complete! (55.21 secs)`.
  Re-running xtool's own builder `swift build` after `cp Package.resolved xtool/.xtool-tmp/`:
  `Build complete! (9.98 secs)`.
- `.process("Media.xcassets")`, `.process("Localizable.xcstrings")`: row 2 errors; `.process("data.json")` builds.
  After `install-toolchain.sh`, as a brand-new user: both `Build complete!`; the app holds
  `HelloOmarchy_HelloOmarchy.bundle/Assets.car` and `de.lproj/Localizable.strings` (`{'Hello': 'Hallo'}`).
- `StoreView(ids:)` in a file importing StoreKit and SwiftUI: row 8 error; with
  `-Xfrontend -enable-cross-import-overlays`: `Build complete! (14.86 secs)`.

## xcstringstool against Apple's

```
[stringsAndStringsdict] files: ours 38, apple 38, same set True; dry-run same as Apple's: True
[stringsAndStringsdict] differing keys: 0
[stringsdictOnly] files: ours 19, apple 19, same set True; dry-run same as Apple's: True
[stringsdictOnly] differing keys: 0
[stringsAndStringsdict] files: ours 4, apple 4, same set True; dry-run same as Apple's: True   (edge-case catalog)
[stringsAndStringsdict] differing keys: 0
```

`generate-symbols --language swift`: `diff -u` against Apple's output, 0 changed lines for both catalogs.

## actool against Apple's (light/dark colorset, 1x/2x/3x imageset)

```
same  sym/GeneratedAssetSymbols.swift
same  sym/GeneratedAssetSymbols.h
same  compile/partial.plist
same  --version
same  sym/GeneratedAssetSymbols-Index.plist (catalogPath ignored)
same  sym stdout
same  compile stdout
deps records: apple  0a 61 0a 10 0a 40 0a 40 0a
deps records: ours   0a 61 0a 10 0a 40 0a 40 0a
assetutil renditions identical: True 5 5
```

Before the AssetKit color fix, `assetutil` read the colors as
`('Color components', '[2e-323]'), ('Colorspace', 'generic')`. IceCubes' system-color catalog
(`labelColor`, light and dark): `system colors identical in assetutil: True`.
AssetKit fork tests: `Test run with 39 tests in 12 suites passed`.
