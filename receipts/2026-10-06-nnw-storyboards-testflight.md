# NetNewsWire storyboards compiled on Linux, in TestFlight, 2026-10-06

NetNewsWire's `Main.storyboard`, `Settings.storyboard`, `Inspector.storyboard` and
`SettingsComboTableViewCell.xib` now compile with the Linux `tools/ibtool`. Before this, the
generator excluded all four ("Linux ibtool cannot compile them").

## Byte comparison with Xcode 27.0

The ground truth is NetNewsWire built by Xcode 27.0 on macstudio
(`/opt/nnwxcode/NetNewsWire.app` in the chroot). Its storyboardc trees equal `tests/ibtool/golden`.
Compiled with Xcode's flags (`--module NetNewsWire`):

```
$ cmp-nnw.sh tools/ibtool OUT
Main: identical=11 differ=0
Settings: identical=10 differ=0
Inspector: identical=7 differ=0
Combo xib: identical
$ python3 tools/ibtool --self-test
self-test passed (round-trip 56 golden nibs; TinyView and TinyLabel and SettingsTableViewCell and
SettingsComboTableViewCell and LaunchScreenPhone.storyboardc and LaunchScreenPad.storyboardc and
Mastodon Main.storyboardc and Mastodon ShareActionExtension MainInterface.storyboardc and NetNewsWire
Main.storyboardc and NetNewsWire Settings.storyboardc and NetNewsWire Inspector.storyboardc
byte-identical to golden)
```

The self-test now includes the three NetNewsWire storyboards and the combo xib.

## TestFlight

```
$ BUNDLE_ID=com.joshuaswarren.omarchyappledev.netnewswire compat/nnw/setup.sh ~/nnw-sb-0013   (no IB file excluded)
$ ship.sh --upload
85/85 checks passed
buildUpload 256e6e7e-5cac-4939-a75b-668fabed6cef: COMPLETE
$ asc-builds.sh 6819098049
256e6e7e-5cac-4939-a75b-668fabed6cef 202610060017 VALID 2026-10-05T17:19:01-07:00 False 17.0 APP_STORE_ELIGIBLE
```

The shipped nibs differ from Xcode's app only in Swift class names, because the xtool adapter's
target module is `NetNewsWire_iOS` where Xcode's is `NetNewsWire`
(`_TtC15NetNewsWire_iOS22SettingsViewController` vs `_TtC11NetNewsWire22SettingsViewController`).
A local compile with `--module NetNewsWire_iOS` equals the shipped files: Main 11/11, Settings 10/10,
Inspector 7/7.

## Module name fix found on the way

SwiftBuild passes ibtool the resource-bundle module (`NetNewsWire-iOS_NetNewsWire-iOS`). Before the
fix, ibtool wrote that into the class names, so the classes would not resolve at run time (build
202610052356, upload 1d212250, VALID but wrong). `ibtool` now maps `<package>_<target>` to the target's
Swift module, using the package name in SwiftBuild's `Intermediates.noindex/<package>.build` paths.
The same bug affected Mastodon's share extension storyboard (FINDINGS 43); its next upload carries the fix.
