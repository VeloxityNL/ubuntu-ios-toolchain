# A macOS app built, signed and notarized on Linux, 2026-10-06

x86_64 Arch chroot, Swift 6.4.0, the darwin Swift SDK from Xcode 27.0 (MacOSX27.0.sdk), rcodesign 0.29.0.

1. Build, a SwiftUI `@main` app (`Package.swift`, one executable target, macOS 14):

   ```
   S=~/.swiftpm/swift-sdks/darwin.artifactbundle
   XCODE_EXTRA_PLATFORM_FOLDERS=$S/Developer/Platforms PATH=$S/toolset/bin:$PATH \
     swift build -c release --build-system swiftbuild --triple arm64-apple-macosx14.0 --toolset $S/toolset-swb.json
   Build complete! (20.16 secs)
   ```

2. Wrap in `MacHello.app/Contents/{MacOS,Info.plist}`. Sign with the Developer ID Application identity
   (certificate G349BR5A3A, key made on Linux):

   ```
   rcodesign sign --pem-file key.pem --pem-file cert.pem --for-notarization MacHello.app
   creating cryptographic signature with certificate Developer ID Application: Creatuity Corp. (9LX44YXXVX)
             flags: CodeSignatureFlags(RUNTIME)
   ```

3. Notarize and staple from Linux:

   ```
   rcodesign notary-submit --api-key-file rcodesign-api-key.json --max-wait-seconds 1600 --staple MacHello.app
   writing notarization ticket to MacHello.app/Contents/CodeResources
   ```

   Notary history (GET /notary/v2/submissions): `883cb50d-56b4-403c-a2c1-ba16c31e9596 MacHello.app.zip Accepted`.
   An earlier ad hoc signed submission, `afd186e3-d0a5-44a2-871b-46b21a52f57f`, is `Invalid`, as expected.

4. On macstudio (macOS, Xcode 27), with a quarantine attribute set as for a download:

   ```
   $ codesign --verify --deep --strict --verbose=2 MacHello.app
   MacHello.app: valid on disk
   MacHello.app: satisfies its Designated Requirement
   $ xcrun stapler validate MacHello.app
   The validate action worked!
   $ spctl -a -t exec -vv MacHello.app
   MacHello.app: accepted
   source=Notarized Developer ID
   origin=Developer ID Application: Creatuity Corp. (9LX44YXXVX)
   $ open MacHello.app; pgrep -fl MacHello.app
   45992 /private/var/folders/.../AppTranslocation/.../d/MacHello.app/Contents/MacOS/MacHello
   ```
