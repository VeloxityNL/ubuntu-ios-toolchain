# ship.sh: App Store .ipa built, signed and validated on Linux (2026-10-03)

Host: the clean Arch x86_64 root of
`2026-10-03-xtool-1.20-swift-6.4-x86_64.md`. A brand-new user `shipper`
ran `install-toolchain.sh`, `xtool new ShipDemo`, added an iPhone-only
`Info.plist` (`UIDeviceFamily` `[1]`) and a single-size 1024 AppIcon (an
SVG rendered with `rsvg-convert`), then ran `ship.sh` with no App Store
Connect key and no `XCODE_*` variables.

## Install and ship

```
install exit=0
darwin-iPhoneOS27.0.xtoolsdk
darwin-iPhoneOS27.0.xtoolsdk.version.plist
App icon AppIcon: 4 loose PNGs, Info.plist updated
stamped com.example.ShipDemo 1.0.0 (202610032152), iphoneos27.0 24A430, Xcode 27.0 27A266a
TEST identity (self-signed, team TEST000000): Apple will reject this signature; use it to check the pipeline
wrote /home/shipper/apps/ShipDemo/xtool/ShipDemo.ipa
```

## Offline validation (`asc.py validate`)

```
ok   every entry is under Payload/
ok   no __MACOSX or .DS_Store
ok   exactly one app bundle in Payload/: ['ShipDemo.app']
ok   Info.plist has the required keys
ok   CFBundleShortVersionString '1.0.0' is up to three integers
ok   CFBundleVersion '202610032152' is up to three integers
ok   CFBundlePackageType is APPL
ok   CFBundleSupportedPlatforms is [iPhoneOS]
ok   built against the device SDK: iphoneos27.0
ok   DTXcode 2700 / 27A266a
ok   launch screen declared
ok   executable ShipDemo is a thin 64-bit Mach-O
ok   arm64 MH_EXECUTE
ok   position independent (MH_PIE)
ok   LC_BUILD_VERSION iOS minos (17, 0, 0) <= MinimumOSVersion 17.0
ok   LC_CODE_SIGNATURE present
ok   Assets.car present (4 rendition sizes)
ok   Assets.car has the App Store 1024 icon (1024x1024)
ok   Assets.car has the iPhone 60@2x icon (120x120)
ok   App Store icon has no alpha channel
ok   declared icon file AppIcon60x60*.png is in the bundle
ok   embedded.mobileprovision present
ok   profile app id TEST000000.com.example.ShipDemo covers com.example.ShipDemo
ok   App Store profile (no device list, not enterprise)
ok   profile get-task-allow is false
ok   profile valid until 2027-10-03
note TEST identity: structure only; Apple rejects this signature
ok   rcodesign verify ShipDemo
ok   CodeDirectory team id TEST000000 matches the profile
ok   Info.plist matches its sealed hash
ok   _CodeSignature/CodeResources matches its sealed hash
ok   every bundle file is sealed with a matching hash
ok   signed entitlements match the profile: TEST000000.com.example.ShipDemo
ok   signed get-task-allow is false
ok   signed entitlements are a subset of the profile
ok   signing certificate is one of the profile's DeveloperCertificates
35/35 checks passed
```

## Apple's tools on the same .ipa (Mac, Xcode 27.0, read-only)

```
== plutil -lint
Payload/ShipDemo.app/Info.plist: OK
== codesign -dvvv
Identifier=com.example.ShipDemo
Format=app bundle with Mach-O thin (arm64)
CodeDirectory v=20400 size=1048 flags=0x0(none) hashes=22+7 location=embedded
Hash type=sha256 size=32
Authority=Apple Distribution: omarchy-apple-dev TEST (TEST000000)
TeamIdentifier=TEST000000
Sealed Resources version=2 rules=10 files=6
== codesign --verify --deep --strict
Payload/ShipDemo.app: valid on disk
Payload/ShipDemo.app: satisfies its Designated Requirement
```

`xcrun assetutil --info` on its `Assets.car`: CoreUI 970, StorageVersion
17, renditions marketing 1024, phone 120 (@2x), phone 180 (@3x), pad 152.

## The validator fails on broken builds

Copies of the signed app, broken one way each:

```
== no team id in CodeDirectory
FAIL CodeDirectory team id None matches the profile
== Info.plist edited after signing
FAIL CFBundleVersion '1.x' is up to three integers
FAIL Info.plist matches its sealed hash
== debug entitlements (get-task-allow true)
FAIL signed get-task-allow is false
== no Assets.car, no profile
FAIL Assets.car present (0 rendition sizes)
FAIL Assets.car has the App Store 1024 icon (1024x1024)
FAIL Assets.car has the iPhone 60@2x icon (120x120)
FAIL embedded.mobileprovision present
```

All four exit 1. The template app with iPad enabled fails one check:
`FAIL Assets.car has the iPad Pro 83.5@2x icon (167x167)` (FINDINGS 23.2).

## Upload path

`ship.sh --upload` without a key stops at `--upload needs ASC_KEY_ID`.
`asc.py upload` with a freshly generated P-256 key that Apple does not know:

```
asc.py: GET /v1/apps?filter[bundleId]=com.example.ShipDemo: HTTP 401
"code": "NOT_AUTHORIZED", "title": "Authentication credentials are missing or invalid."
```

Not proven: anything after authentication (certificate and profile
creation, build upload, Apple's processing, TestFlight).

## actool reference for the iPad gap

Xcode 27 `actool` on 60@2x, 60@3x, 76@2x, 83.5@2x and 1024 images, read
with `assetutil --info`: Icon Index 1 (phone 120, 180), 2 (pad 152),
3 (pad 167), 4 (phone 90 pt subtype 1792), 5 (marketing 1024), plus
"MultiSized Image" entries `60x60 index:1`, `76x76 index:2`,
`83x83 index:3`, `1024x1024 index:5`. AssetKit 1.0.0 writes Icon Index 1
for every icon and no MultiSized entries.
