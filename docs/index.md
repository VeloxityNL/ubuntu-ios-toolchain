# Ubuntu iOS Toolchain

**Build, sign and ship native iOS apps from Ubuntu Linux.**

Ubuntu iOS Toolchain provides an Ubuntu-focused workflow around Swift, xtool, Apple SDK extraction, code signing and App Store Connect delivery.

## Quick start

```bash
git clone https://github.com/VeloxityNL/ubuntu-ios-toolchain.git
cd ubuntu-ios-toolchain
./install-ubuntu.sh
ubuntu-ios doctor
```

You provide your own legally obtained Xcode `.xip`; this repository does **not** redistribute Xcode or Apple SDKs.

## Workflow

1. Install the Ubuntu dependencies and Swift toolchain.
2. Import an Xcode SDK from your own Xcode `.xip`.
3. Convert your Xcode project where needed.
4. Build with `ubuntu-ios build`.
5. Sign/package with `ubuntu-ios ship`.
6. Upload with `ubuntu-ios ship --upload`.

## Documentation

- [Main README](../README.md)
- [Getting started](../GETTING-STARTED.md)
- [Security](../SECURITY.md)
- [Contributing](../CONTRIBUTING.md)
- [Example SwiftUI app](../examples/HelloSwiftUI/README.md)

## Scope

The project targets developers who want a Linux-native iOS build pipeline. It is independent and is not affiliated with Apple.
