# Mac symbolsets found by AppKit — receipts, 2026-10-07

Fixes the NetNewsWire Mac launch abort in `NSImageSymbolRepProvider`
("NSImage requested a variant from a symbol that wasn't found in the asset
catalog") during MainWindow toolbar layout. Branch `mac-symbols` (this
commit) pins AssetKit `omarchy/mac-symbols` 83dccf7.

## 1. Root cause (Apple oracle: Xcode 27.0 actool on macstudio)

Apple's `actool` compiled NNW's Mac catalog for `--platform macosx` and
`--platform iphoneos` to **byte-identical** cars (sha256
`9093259e…bdaf25` for both). The Linux car failed on macOS for a reason
that has nothing to do with the symbol renditions themselves:

- Apple's symbol encoding equals ours item for item: 9 Medium cached
  bitmaps (scales 1–3, Glyph Cached Index 0–2, point sizes 15/17/20) + 3
  Regular-weight vector glyphs (Small/Medium/Large), same layout numbers
  (1003/1017), same TVLs, same metrics, same `UIAppearanceAny` /
  `UIAppearanceDark` APPEARANCEKEYS strings (values 9/11 vs Apple's 11/9 —
  both cars key renditions at 0/1, so the values are decoration).
- The difference is the **rendition-key schema**. Apple's car has a
  13-attribute KEYFORMAT `[7, 13, 12, 15, 16, 26, 27, 9, 8, 25, 17, 1, 2]`
  (`dimension1` at its canonical rank, no `displayGamut`) and 68-byte
  BITMAPKEYS descriptors (`hdrSize` 56, keyLen 13). Ours had 12 attributes
  (no `dimension1`) and 64-byte descriptors. macOS 26 CoreUI resolves
  **no rendition at all** from a car in the 12-attribute schema.

Minimal AppKit probe on macstudio (`Bundle.image(forResource:)` on a bundle
holding only the car): Apple car → `NSSymbolImageRep` +
`NSImageSymbolRepProvider` for all four symbolsets and `NSCGImageRep` for
images; our old car → **nil for every name**. That also explains the NNW
crash path: `NSImage(named:)` returns an empty placeholder for a missing
name, and the toolbar button's later variant query aborts.

`assetutil --info` display fields for symbols (12 Image renditions at
scales 1–2 with Medium/Large, "PixelWidth 10x15") are virtualized by the
dumper; a raw BOM walk shows the physical content listed above. Do not
treat assetutil's symbol rows as the car's rendition list.

## 2. Change

AssetKit `omarchy/mac-symbols` (83dccf7, off 9f509fe): `--platform macosx`
compilations widen KEYFORMAT with `dimension1` and switch the symbol
BITMAPKEYS template to the Apple Mac shape
`[1, 1, 0x10, 14, 7, 1, 0x20]`. Everything else is untouched, so iOS
output is gated away from the new schema. actool (this repo) forwards
`--platform`. AssetKit tests: 72/72 pass.

Probe after the fix, same harness, car compiled by the new actool with
`--app-icon AppIcon`: all four symbolsets resolve as `NSSymbolImageRep`,
images resolve as `NSCGImageRep`.

## 3. iOS output unchanged

`actool` is not byte-deterministic run to run (the unsorted
`contentsOfDirectory` catalog walk reshuffles BOM block order: two runs of
the *same* 9f509fe binary differ in 3.1 M of 7.1 M bytes on the NNW iOS
catalog), so byte-identity is proven at the level the baseline itself
meets: canonical form (every block's bytes + every tree's entries sorted
by key), base vs new, two catalogs:

| car | canonical base vs new |
|---|---|
| NNW iOS `iOS/Resources/Assets.xcassets` (137 renditions) | EQUAL |
| IceCubes `IceCubesApp/Assets.xcassets` (78 renditions) | EQUAL |
| baseline rerun vs itself (both catalogs) | EQUAL |

Raw baseline rerun sha256s differ (`ff3ebc3b…` / `2ba722ac…` NNW,
`7ed56955…` / `38272f25…` IceCubes), matching the known volatility; base
and new agree exactly where 9f509fe agrees with itself. Packed-atlas order
behavior is 9f509fe's, unchanged (FINDINGS 54).

## 4. Launch result on macstudio (macOS 26.6.2)

Rebuilt `~/nnw-mac5/omarchy-xtool` (car now 13-attribute, 1 129 293
bytes), signed, notarized (Accepted, stapled), `spctl` accepted:

```
NetNewsWire.app: accepted
source=Notarized Developer ID
origin=Developer ID Application: Creatuity Corp. (9LX44YXXVX)
```

`open` → process stays alive (previous build died 1.0 s in), no new
crash reports (9 before, 9 after). **The main window shows**: three-pane
split view (Smart Feeds sidebar, timeline "NetNewsWire 0 unread", detail
"No selection"), search field, and the toolbar drawing the custom catalog
symbols that previously aborted the launch (markAllAsRead group,
preferencesToolbarExtensions). NNW's own Crash Log Reporter window opened
over it offering to report the *old* pre-fix crash; dismissed, app quit
cleanly. Screenshots: `~/tmp/apple-dev/nnw-mac-shots/nnw-main.png`
(sha256 `08589337…5f7b5`), `nnw-second.png` (`dc7284c4…8e7c8`), captured
with cua-driver `get_window_state` (window_id 34113, 1345×900).

## 5. SHAs

- AssetKit branch `omarchy/mac-symbols`: `83dccf7a47ad8257a8dddd8b0750db592628f67a`
- omarchy-apple-dev branch `mac-symbols` (this commit, pin bump): `00825d5499788d0d5118a5a656295188a8870aae` → receipt commit on top
