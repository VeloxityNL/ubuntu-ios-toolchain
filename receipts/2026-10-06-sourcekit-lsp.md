# SourceKit-LSP on Linux for NetNewsWire and IceCubes, 2026-10-06

x86_64 Arch chroot, Swift 6.4.0, `/usr/lib/swift/usr/bin/sourcekit-lsp`, xtool
0563868 built by `install-toolchain.sh` (FINDINGS.md 55).

`regress-full.sh` with this pin: install exit 0, the three sample apps build,
OmarchyDemo 38/38 and OmarchyDemoPad 39/39 checks, IceCubes (4 extensions)
102/102, NetNewsWire (2 extensions) 86/86.

The probe (`sk-probe.py`, stdlib LSP client) starts sourcekit-lsp in the folder
of the `.xcodeproj` of those fresh regress clones, so the generator's
`.bsp/xtool.json` (`xtool dev build-server --package-path omarchy-xtool`) is
used. It opens real project files and waits for indexing to end.

```
== NetNewsWire (/home/builder/reg-nnw-1717)
[PASS] diag-clean: 0 diagnostics (0 errors):
[PASS] diag-error: 1 diagnostics; probe error reported: Cannot convert value of type 'String' to specified type 'Int'
[PASS] def-same-file: file:///home/builder/reg-nnw-1717/iOS/Settings/TimelineCustomizerCollectionViewController.swift:14
[PASS] def-cross-target: file:///home/builder/reg-nnw-1717/Modules/Account/Sources/Account/AccountManager.swift:18
[PASS] def-sdk: file:///home/builder/tmp/sourcekit-lsp/GeneratedInterfaces/2965812579652537134/UIKit.UIApplication.swiftinterface:75
[PASS] def-remote: file:///home/builder/reg-nnw-1717/.build/index-build/checkouts/Zip/Zip/Zip.swift:66
[PASS] completion: 200 items; want windows: ['windows async']
[PASS] hover: ```swift @MainActor @_nonSendable(_assumed) class UIApplication : UIResponder ```
== IceCubes (/home/builder/reg-icecubes-1710)
[PASS] diag-clean: 0 diagnostics (0 errors):
[PASS] diag-error: 1 diagnostics; probe error reported: Cannot convert value of type 'String' to specified type 'Int'
[PASS] def-same-file: file:///home/builder/reg-icecubes-1710/IceCubesApp/App/Tabs/TagGroup/EditTagGroupView.swift:12
[PASS] def-cross-target: file:///home/builder/reg-icecubes-1710/Packages/DesignSystem/Sources/DesignSystem/Theme.swift:6
[PASS] def-sdk: file:///home/builder/tmp/sourcekit-lsp/GeneratedInterfaces/6447297376909986111/SwiftUI.swiftinterface:95106
[PASS] def-remote: file:///home/builder/reg-icecubes-1710/.build/index-build/checkouts/SFSafeSymbols/Sources/SFSafeSymbols/Symbols/SFSymbol.swift:7
[PASS] completion: 200 items; want font: ['fontWidth(width: Font.Width?)', 'fontWeight(weight: Font.Weight?)', 'fontDesign(design: Font.Design?)']
[PASS] hover: ```swift @_originallyDefinedIn(module: "SwiftUI", iOS 18.0) ...
```

The same 8 checks also pass with the editor opened in `omarchy-xtool` for both
apps (debug build of the same xtool source). Before the fix, 2 of 8 passed
(diag-clean and def-same-file); the others returned nothing, and SwiftPM
answered real-path `textDocument/sourceKitOptions` with "Found multiple
indexing informations for the same source file".
