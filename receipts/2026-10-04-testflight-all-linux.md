# A TestFlight build made entirely on Linux, 2026-10-04

FINDINGS.md item 38. Host: omp-studio-local, clean Arch x86_64 root, user `builder`, installer
state at the commit of this receipt (xtool 3cbf66b, AssetKit 410cf2f in tools/darwin-tools).
App: the demo app `com.joshuaswarren.omarchyappledev.demo` (App Store Connect app 6819062752,
team Creatuity Corp.), built from `make-demo.sh` (SwiftUI, single-size 1024 AppIcon, iPhone).
Key: App Store Connect API key with the App Manager role (Key ID and Issuer ID passed in the
environment; the `.p8` path is local and is not part of this receipt).

```
$ XCODE_VERSION=27.0 XCODE_BUILD=27A266a ASC_KEY_ID=... ASC_ISSUER_ID=... ASC_KEY_PATH=... ship.sh --upload
== 1. Release build ==
== 2. App icon catalog ==
== 3. App Store Info.plist keys ==
stamped com.joshuaswarren.omarchyappledev.demo 1.0.0 (202610042155), iphoneos27.0 24A430, Xcode 27.0 27A266a, Mach-O sdk 27.0 in 1 file(s)
== 4. Distribution identity and signature ==
== 5. Package ==
== 6. Offline App Store validation ==
36/36 checks passed
== 7. Upload to App Store Connect ==
uploaded 36181 bytes in 1 part(s)
buildUpload 5e68f02d-d0cd-401c-b4ee-ef3a2b44f099: COMPLETE
```

App Store Connect API, `GET /v1/builds?filter[app]=6819062752`, five minutes later:

```
5e68f02d-d0cd-401c-b4ee-ef3a2b44f099 202610042155 VALID 2026-10-04T14:55:45-07:00 False 17.0 APP_STORE_ELIGIBLE
```

Every file in that `.ipa` came from Linux: the Mach-O binary (xtool + Swift 6.4), `Assets.car` and
the icon PNGs (the Linux `actool` on AssetKit), the Info.plist keys (`asc.py stamp`), the
signature (`rcodesign` with an Apple Distribution certificate and App Store profile that
`asc.py identity` created through the API). Nothing was submitted for review.

## The asset-catalog bisect (uploads of the same app, one change each)

| build | Assets.car | result |
|---|---|---|
| 202610041813, 1827 | AssetKit (CoreUI 970 header, then 1010 header) | INVALID, 90562 |
| 202610041830 | Apple actool 27.0 (on a Mac) | VALID |
| 202610042042, 2114 | AssetKit single-size form, BITMAPKEYS fix | INVALID, 90562 |
| 202610042049 | Apple's car + our LZFSE pixel payload | VALID |
| 202610042051 | Apple's car + our NameIdentifier (5444) | VALID |
| 202610042054 | Apple's car + our identity strings | VALID |
| 202610042119 | Apple's car + all three of the above | VALID |
| 202610042155 | AssetKit 410cf2f (all 256 BOM index entries written) | VALID |

The cause: AssetKit's BOM writer declared 256 index entries but wrote only the used ones, so the
file ended inside the index table. Apple's `assetutil` reads such a file; App Store processing
does not. With the full index, the Linux car differs from the accepted 202610042119 car only in
the BITMAPKEYS value block, where it now matches Apple's own output.
