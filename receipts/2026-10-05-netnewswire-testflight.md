# NetNewsWire: an all-Linux TestFlight build is VALID (2026-10-05)

A real app, built, signed and uploaded entirely on Linux: NetNewsWire 7.1.4 at
`8c322c28`, app plus widget and share extensions, 15 SwiftPM `.dynamic`
products. Nothing was submitted for review.

## The build

Arch Linux x86_64 chroot, toolchain from `install-toolchain.sh` at this commit
(xtool 3cbf66b, AssetKit 16c561f):

```
$ BUNDLE_ID=com.joshuaswarren.omarchyappledev.netnewswire compat/nnw/setup.sh ~/reg-nnw-final
$ cd ~/reg-nnw-final/omarchy-xtool && ship.sh --upload
== 3. App Store Info.plist keys and frameworks ==
stamped com.joshuaswarren.omarchyappledev.netnewswire 7.1.4 (202610050846), iphoneos27.0 24A430, Xcode 27.0 27A266a, Mach-O sdk 27.0 in 18 file(s)
wrapped 15 dylib(s) as frameworks
== 6. Offline App Store validation ==
83/83 checks passed
== 7. Upload to App Store Connect ==
uploaded 15577819 bytes in 3 part(s)
buildUpload ad8849b0-06cc-472d-a2a6-27eef2d4ca26: COMPLETE
```

`.ipa` sha256 `6324bf5da9f5e05a0da9a7d9d21adb381b9fbdaecc15ff133d47add2759d21f5`:
`Frameworks/` holds 15 `<Name>.framework` bundles, `PlugIns/` the two
extensions, `Assets.car` 7,098,044 bytes from the Linux `actool`.

App Store Connect API, `GET /v1/builds?filter[app]=6819098049`, two minutes later:

```
ad8849b0-06cc-472d-a2a6-27eef2d4ca26 202610050846 VALID 2026-10-05T01:48:39-07:00 False 17.0 APP_STORE_ELIGIBLE
```

## What App Store processing rejected on the way

| Upload | Result | Cause | Fix |
|---|---|---|---|
| f17f16e0 (10-04) | 90022, 90023 | single-size icon compiled for iPhone only, no dark or tinted | AssetKit 87cd7d6, `actool` keys per `--target-device` |
| aada7e9f | 90426 "SwiftSupport folder is missing" | loose `Frameworks/lib*.dylib` | `asc.py frameworks` wraps them as `.framework` |
| 74522556, 79d1c58d, 57cdfde3 | `PROCESSING` for hours, no error | `Assets.car` BITMAPKEYS descriptors | AssetKit 1f23d61, 16c561f |

The third row has no error message, so it was bisected with real uploads. The
control was NetNewsWire built by Xcode 27.0 on a Mac (unsigned), then signed
and uploaded by the Linux pipeline: VALID. Swapping in parts of the Linux
build, one at a time:

| Xcode-built app plus our ... | Result |
|---|---|
| executable | VALID |
| executable, Info.plist | VALID |
| executable, Info.plist, 15 frameworks | VALID |
| executable, Info.plist, Assets.car | stuck |
| ... Assets.car of AppIcon base, or base + dark | VALID |
| ... AppIcon base + dark + PNG imagesets, or + PDF imagesets | VALID |
| ... AppIcon base + tinted | stuck |
| ... AppIcon base + dark + any one colorset group | stuck |
| ... AppIcon base + dark + one colorset, Apple's actool | VALID |
| ... the same, AssetKit 1f23d61 | VALID |

Apple's `assetutil --info` and `assetutil` thinning read every stuck car
without complaint. The difference was in BITMAPKEYS: each descriptor must be
`(tokens + 4) * 4` bytes for the car's KEYFORMAT token count, with the real
icon group count and all-1 color slots. AssetKit hard-coded the 9-token icon
form and the 8-token color form.

The full catalog with the tinted icon, built with 16c561f, is the VALID build
above. The regression set at this commit (`regress-full.sh`, fresh clones):
template, `branch:` dependency and `.dynamic` product build; demo 37/37, iPad
demo 38/38, IceCubesApp 98/98, NetNewsWire 83/83.

Upload 8198e86f (the Linux build with Apple's `actool` car for the main
catalog) also stayed in `PROCESSING`, because the app has a second car. The
SwiftPM resource bundle `NetNewsWire-iOS_NetNewsWire-iOS.bundle/Assets.car`
(37 colors and 1 image, from another catalog) was still compiled by the old
AssetKit. Two uploads of the Xcode-built control with our executable and
Info.plist settle it:

| Added `NetNewsWire-iOS_NetNewsWire-iOS.bundle` | Result |
|---|---|
| car from AssetKit 793a650 (sha256 `e12fff0e…`, the 8198e86f bundle) | stayed in `PROCESSING` |
| car from AssetKit 16c561f (sha256 `3f68b3ba…`) | `fc19d596`, `VALID` |

So App Store processing checks every `Assets.car` in the app, nested resource
bundles included, and the theory holds: Apple's car was fine.

## IceCubesApp, same toolchain

IceCubesApp from `regress-full.sh` (`reg-icecubes-0853`), its extensions left
out because their bundle IDs have no App Store Connect records, uploaded under
the NetNewsWire record as a diagnostic: `buildUpload 531e358f: COMPLETE`, then

```
531e358f-a804-4f65-ba84-702a88d746ac 202610050911 VALID 2026-10-05T02:12:47-07:00 False 18.5 APP_STORE_ELIGIBLE
```

Before AssetKit 1f23d61, the same app stayed in `PROCESSING`.
