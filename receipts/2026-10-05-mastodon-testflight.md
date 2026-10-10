# Mastodon for iOS: an all-Linux TestFlight build is VALID (2026-10-05)

Mastodon for iOS (mastodon/mastodon-ios @ c52a630) with all five app extensions
(NotificationService, ShareActionExtension, MastodonIntent,
OpenInActionExtension, WidgetExtension), its App Group, 28 custom SF Symbols,
its main and share-extension storyboards and its Core Data model, built,
signed and uploaded on Linux. Nothing was submitted for review.

## The build

Arch Linux x86_64 chroot, Swift 6.4.0, toolchain from `install-toolchain.sh` at
this commit (xtool 3cbf66b, AssetKit baf0f98, the repo's `tools/ibtool`). App
Store Connect app 6819300325; the App Group
`group.com.joshuaswarren.omarchyappledev.mastodon` is assigned to all six
bundle IDs, so `ship.sh` (with `APP_GROUPS` set) recreated the six App Store
profiles with the group entitlement.

```
$ BUNDLE_ID=com.joshuaswarren.omarchyappledev.mastodon compat/mastodon/setup.sh ~/mas-ship-1734
$ cd ~/mas-ship-1734/omarchy-xtool
$ APP_ICON=AppIcon APP_GROUPS=group.com.joshuaswarren.omarchyappledev.mastodon ship.sh --upload
stamped com.joshuaswarren.omarchyappledev.mastodon 2026.08 (202610051741), iphoneos27.0 24A430, Xcode 27.0 27A266a, Mach-O sdk 27.0 in 7 file(s)
wrapped 1 dylib(s) as frameworks
117/117 checks passed
uploaded 47103458 bytes in 9 part(s)
buildUpload 52016c3b-66d9-45f7-a401-5a89c6b620b8: COMPLETE
  warning 90176: Unrecognized Locale ... Mastodon_Mastodon.bundle/kmr-TR.lproj ...
```

`GET /v1/builds?filter[app]=6819300325`:

```
52016c3b-66d9-45f7-a401-5a89c6b620b8 202610051741 VALID 2026-10-05T10:44:06-07:00 False 18.6 APP_STORE_ELIGIBLE
```

The `.app` carries `Base.lproj/Main.storyboardc` and the share extension's
`Base.lproj/MainInterface.storyboardc`, both compiled by `tools/ibtool`
(byte-identical to Apple's ibtool 27.0 for these files, `tests/ibtool`).

## What App Store processing rejected on the way

| Upload | Result | Cause | Fix |
|---|---|---|---|
| 60cfb40f | 90029 `Main~ipad.storyboardc was not found` | storyboards excluded | `tools/ibtool` storyboard path; generator emits compilable IB files |
| 89319fe0 | 90357 share-extension `MainInterface.storyboardc` missing; 90362 `Action.js` not in the extension | storyboard not compilable yet; SwiftPM put `Action.js` in the extension's resource bundle | ibtool navigation-controller scenes; `ship.sh` moves IB files and the JavaScript file to the bundle roots |
| 111683f6 | `PROCESSING`, never finished | `Mastodon_Mastodon.bundle/Assets.car` was EMPTY | `actool` resolves symlinked catalog inputs |

The empty car was found with hybrids of the built app: Apple's car for the big
MastodonAsset catalog alone did not help; removing the empty car as well gave
build 202610051714 (438b4b07), `VALID`. The generated adapter links the app's
`Preview Assets.xcassets` into the package as a symlink, and Foundation on
Linux lists a symlinked directory's children as non-directories, so the Linux
`actool` found no assets and wrote a car with zero renditions. Compiled from
the resolved path, the same catalog gives a 3,111,048-byte car (Apple's:
3,111,000 bytes, six JPEG images).

The big MastodonAsset catalog (714 renditions in Apple's car) also found three
AssetKit gaps, fixed in baf0f98 before these uploads: Apple's `assetutil`
refused our single 778-entry RENDITIONS leaf (`page->numKeys(778) >
tree->maxKeys(510)`), so large trees are now split into linked leaves under a
branch page; folders with `provides-namespace` now prefix asset names
(`Colors/Border/status`); and symbol templates whose guides are `<path>`
elements (template v3, SwiftDraw) are read.
