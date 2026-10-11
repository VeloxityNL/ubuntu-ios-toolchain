# Roadmap

## Near term

- Validate the installer on more clean Ubuntu 24.04 machines.
- Expand reproducible smoke tests.
- Add a full clean-machine walkthrough from fresh Ubuntu 24.04 to first successful signed build.
- Document expected `ubuntu-ios doctor` output for missing SDK, broken signing setup, missing App Store Connect credentials and common first-build failures.
- Improve diagnostics for SDK, signing and App Store Connect setup so failures include clear next actions.
- Expand device diagnostics beyond pairing into deploy/debug readiness where reliable APIs are available.
- Add more minimal sample projects and CI examples.
- Add an official containerized/Docker CI example for build/sign/TestFlight workflows where practical.
- Document ARM64 Ubuntu support as it matures.

## Community

Issues and pull requests are welcome. Reproducible reports with Ubuntu version, Swift version and `ubuntu-ios doctor` output are especially useful.
