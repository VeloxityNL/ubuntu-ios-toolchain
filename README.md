# Ubuntu iOS Toolchain

Build, sign, install, and upload native iOS / SwiftUI apps **from Ubuntu Linux** — without running macOS or the Xcode application.

This repository packages a reproducible Ubuntu workflow around the official Swift toolchain, `xtool`, `rcodesign`, `pymobiledevice3`, Linux replacements for Apple build utilities, and an iOS SDK extracted from an Xcode archive supplied by the user.

> **Tested host:** Ubuntu 24.04 LTS x86_64  
> **Tested Swift:** 6.3.3  
> **SDK family:** Xcode 26 / iOS 26  
> **Status:** experimental community toolchain; not affiliated with Apple.

## Why this exists

Several iOS-on-Linux projects focus on Arch/Omarchy. This distribution is specifically packaged for **Ubuntu 24.04**. It keeps the newer libimobiledevice stack in a private prefix, so Ubuntu's system libraries do not have to be replaced.

## What works

- Swift and SwiftUI iOS compilation on Ubuntu
- conversion of many `.xcodeproj` projects to an `xtool`/SwiftPM adapter
- asset catalogs, localized strings, storyboards/XIBs and Core Data resources
- app/framework code signing
- `.ipa` creation and local validation
- physical-device tooling
- App Store Connect / TestFlight uploads with an API key
- common capabilities such as APNs and associated domains when correctly provisioned

## What is not included

- Xcode or Apple SDK binaries
- an iOS Simulator
- Apple credentials, certificates, provisioning profiles or App Store Connect keys

Apple SDKs must be obtained directly from Apple.

## Stack

```text
Ubuntu 24.04
├── official Swift 6.3.3 toolchain
├── private libplist / libimobiledevice stack
├── xtool
├── Darwin + iPhoneOS SDK extracted from your Xcode.xip
├── Linux compatibility tools (actool, ibtool, xcstringstool, momc)
├── rcodesign
└── App Store Connect upload tooling
```

## Requirements

- Ubuntu 24.04 LTS x86_64
- `sudo` access
- 25–40 GB free disk space recommended
- 8 GB RAM minimum; 16 GB+ recommended for larger apps
- internet access for installation
- Apple ID for Apple Developer Downloads
- paid Apple Developer membership for normal TestFlight/App Store distribution

## 1. Install

```bash
git clone https://github.com/VeloxityNL/ubuntu-ios-toolchain.git
cd ubuntu-ios-toolchain
./install-ubuntu.sh
```

The installer uses `apt` for Ubuntu dependencies, downloads the official Swift 6.3.3 Ubuntu 24.04 toolchain, builds a compatible private libimobiledevice stack, and installs the Linux iOS build tools.

It intentionally **does not download or redistribute Apple's SDK**.

## 2. Add the Apple iOS SDK

Download a matching Xcode `.xip` from Apple Developer Downloads. Swift 6.3.x should be paired with the matching Xcode 26 generation.

```bash
ubuntu-ios sdk ~/Downloads/Xcode_26.xip
```

Verify:

```bash
ubuntu-ios doctor
swift sdk list
```

`swift sdk list` should include `darwin`.

## 3. Convert an Xcode project

```bash
ubuntu-ios convert MyApp.xcodeproj \
  --target MyApp \
  --out .build/linux-ios \
  --bundle-id com.example.myapp

cd .build/linux-ios
ubuntu-ios build
```

Projects already prepared for `xtool` can skip conversion.

## 4. Build and sign an IPA

From the generated adapter/project directory:

```bash
ubuntu-ios ship
```

The shipping pipeline performs a release build, processes resources, wraps dynamic SwiftPM products where required, signs the app and embedded code, creates an IPA, and runs local validation checks.

## 5. Upload to TestFlight

Create an App Store Connect API key, keep the `.p8` file outside the repository, and export:

```bash
export ASC_KEY_PATH="$HOME/keys/AuthKey_XXXXXXXXXX.p8"
export ASC_ISSUER_ID="00000000-0000-0000-0000-000000000000"
export ASC_KEY_ID="XXXXXXXXXX"

ubuntu-ios ship --upload
```

This uploads a build to App Store Connect. It does not automatically submit the app for App Review.

## Entitlements / capabilities

For capabilities such as push notifications and associated domains:

```bash
export APP_ENTITLEMENTS=/absolute/path/to/MyApp.entitlements
ubuntu-ios ship --upload
```

The included signing changes preserve supported requested capabilities when they are also granted by the provisioning profile.

## Physical iPhone

USB communication uses `usbmuxd`, the libimobiledevice ecosystem, and `pymobiledevice3`. Trust/pair the Ubuntu host with the iPhone first. `device-run.sh` contains the lower-level device workflow.

## Ubuntu-specific library handling

Ubuntu 24.04's packaged libplist/libimobiledevice versions can be older than the ABI expected by the pinned iOS build stack. `install-ubuntu.sh` builds these into a private user prefix:

- libplist 2.8.0
- libimobiledevice-glue 1.3.0
- libtatsu 1.0.5
- libimobiledevice 1.4.0

The `ubuntu-ios` launcher sets `LD_LIBRARY_PATH` and `PKG_CONFIG_PATH` for that private prefix. It does not replace Ubuntu's copies in `/usr/lib`.

## Security

Never commit App Store Connect keys, credential `.env` files, signing private keys, provisioning profiles, passwords, or generated secret material. The `.gitignore` blocks common secret/signing file types, but always review commits before publishing.

## Limitations

This is **not Xcode running on Linux**. It reproduces enough of the build/sign/package workflow for many projects, but complex Xcode build phases, proprietary tools, unusual binary dependencies, or packages that assume macOS may need project-specific changes.

There is no iOS Simulator. Use a physical iPhone and/or TestFlight for runtime testing. Apple can change SDK formats, signing rules, App Store validation and service APIs, so pin known-good versions for production builds.

## Troubleshooting

### `xtool` cannot find `libplist-2.0.so.12`

Run through the installed `ubuntu-ios` launcher. It exports the private Ubuntu-compatible library prefix automatically.

### `swift sdk list` does not show `darwin`

```bash
ubuntu-ios sdk /path/to/Xcode.xip
```

Make sure the Xcode archive matches the Swift major/minor generation.

### Too many open files

```bash
ulimit -n 65536
ubuntu-ios build
```

The helper already attempts this for build/ship commands.

### Apple rejects the uploaded build

Read the full `ubuntu-ios ship --upload` output. The local validator catches many packaging/signing issues, but Apple's server-side validation is authoritative.

## Credits

This Ubuntu distribution builds on the excellent work in **joshuaswarren/omarchy-apple-dev**, **xtool**, Swift, the libimobiledevice ecosystem, pymobiledevice3, and rcodesign/apple-codesign. The original upstream project targets Omarchy/Arch; this repository adds the Ubuntu installer, private dependency prefix, Ubuntu CLI/documentation, and the fixes used on the tested Ubuntu build host.

See `THIRD_PARTY.md` for attribution.

## License

MIT — see `LICENSE`.

Apple, Xcode, iOS, SwiftUI, TestFlight and App Store Connect are trademarks of Apple Inc. This project is independent and is not endorsed by or affiliated with Apple.
