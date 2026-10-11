# Changelog

## Unreleased

- Expanded `ubuntu-ios doctor` with physical-device diagnostics.
- Report `usbmuxd` availability/state separately from device detection.
- Use `idevice_id -l` for USB visibility and `idevicepair validate` for pairing/trust state.
- Surface actionable states for unpaired, pending trust, denied trust and locked devices.
- Added `ubuntu-ios doctor --device` for CI/setup checks that require a ready physical iPhone.
- Install `libimobiledevice-utils` so `idevice_id` and `idevicepair` are available on Ubuntu.

## v1.0.0

- First public Ubuntu-focused release.
- Ubuntu 24.04 installer and `ubuntu-ios` helper CLI.
- Swift/SwiftUI iOS build workflow.
- IPA signing and App Store Connect/TestFlight upload workflow.
- Security, contribution and validation documentation.
