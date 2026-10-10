# App Intents metadata built on Linux, 2026-10-05

`tools/appintentsmeta.py` replaces Xcode 27.0's two App Intents build steps,
`appintentsmetadataprocessor` (`extract.actionsdata`, `version.json`) and
`appintentsnltrainingprocessor --archive-ssu-assets` (`root.ssu.yaml`, `nlu/<md5>.version`,
`nlu/nlu.lzfse`). Its input is the `.swiftconstvalues` that swift-build already emits for each target.
`ship.sh` step 5 runs it for the app and each extension before signing.

## Parity with Xcode 27.0 (macstudio oracle)

- Minimal App Intents app built with `xcodebuild`: all 5 files byte-identical
  (`tests/appintentsmeta/check.sh`, `SSU_RESOURCES=... bash tests/appintentsmeta/check.sh`:
  `ok   min: 5 files byte-identical to Xcode`, `ok   probeD: 5 files byte-identical to Xcode`).
- The Linux `.swiftconstvalues` of the minimal app equals Xcode's apart from the absolute source path.
- IceCubesApp: Xcode's two processors and the Linux tool, both run on the Linux const values
  (`IceCubesApp-primary.swiftconstvalues`, 12 types). Lead re-run
  (`~/tmp/apple-dev/appintents/lead-verify.sh`): `extract.actionsdata` (19143 B), `version.json`,
  `root.ssu.yaml` and `nlu/c0b41daa….version` identical; `nlu.lzfse` differs only in its 8-byte creation
  timestamp (offsets 9312-9315 of the decoded payload).
- IceCubes widget extension: `version.json` identical; `extract.actionsdata` JSON-equal after sorting two
  arrays that Xcode writes in Swift hash order (the order changes between Xcode's own runs).
- Extensions that link AppIntents but declare no App Intents types get no `Metadata.appintents`, as with
  Xcode ("Extracted no relevant App Intents symbols, skipping writing output").

## TestFlight

```
== 5. App Intents metadata ==
xtool/IceCubesApp.app/Metadata.appintents: 5 intents, 2 entities, 2 queries, 2 enums, 5 App Shortcuts
xtool/IceCubesApp.app/Metadata.appintents: App Shortcuts trained for en, nlu/e0f97578c5e48fcacc1d34cdd1407686.version
xtool/IceCubesApp.app/PlugIns/IceCubesAppWidgetsExtensionExtension.appex/Metadata.appintents: 5 intents, 3 entities, 3 queries, 0 enums, 0 App Shortcuts
ok   IceCubesApp.app declares App Intents types and has Metadata.appintents/extract.actionsdata + version.json
ok   IceCubesAppWidgetsExtensionExtension.appex declares App Intents types and has Metadata.appintents/extract.actionsdata + version.json
101/101 checks passed
buildUpload 633e191b-e3b0-4a08-9802-8f7e172a1c27: COMPLETE
$ asc-builds.sh 6819399771
633e191b-e3b0-4a08-9802-8f7e172a1c27 202610052033 VALID 2026-10-05T13:35:14-07:00 ... APP_STORE_ELIGIBLE
```

IceCubesApp with its 4 extensions, ASC app 6819399771. Nothing was submitted for review.

## Limits

- Constructs outside the probed set (other Measurement units, union values, EntityPropertyQuery,
  TransientAppEntity, negativePhrases, and others) stop the build with `error:`; the tool never guesses.
- swift-build's const-extraction protocol list has 17 entries; Xcode's has 19 (adds `AppUnionValue`,
  `AppUnionValueCasesProviding`). Apps with App Intents union values hit the error above.
- App Shortcuts training needs Xcode's `SiriSSUKitModel.framework` resources; `install-toolchain.sh`
  keeps a copy next to the SDK cache (`SSU_RESOURCES` overrides).
