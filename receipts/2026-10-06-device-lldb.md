# LLDB on an iPhone from Linux, 2026-10-06

Host jw16 (Arch Linux aarch64). iPhone 15 Pro Max (iPhone16,2), iOS 27.0.1,
over USB. Swift 6.4.0 swift.org toolchain (`lldb` 21.0.0, revision 903b9faa),
pymobiledevice3 11.22.0, xtool 3cbf66b (FINDINGS.md 56).

1. `xtool install --udid 00008130-000978E630E1401C UO.app`: "Successfully installed!", exit 0. The app is a
   debug build of `xtool new` with two locals in `ContentView.body`.
2. `pymobiledevice3 mounter mount-personalized` with Xcode 27's
   `iOS_DDI/Restore/022-21793-062.dmg`, its trustcache and `BuildManifest.plist`.
3. `sudo pymobiledevice3 lockdown start-tunnel`, then
   `pymobiledevice3 developer debugserver lldb XTL-69A6DE8B.com.example.UO --rsd HOST PORT`
   with `breakpoint set --file ContentView.swift --line 7`, a synchronous `continue` and
   `frame variable greeting launches`.

First session, 17:38Z:

```
* thread #1, queue = 'com.apple.main-thread', stop reason = breakpoint 1.3
      frame #0: 0x00000001007280a0 UO`ContentView.body.getter() at ContentView.swift:7:23
   5   	        let greeting = "Hello from Omarchy Linux"
   6   	        let launches = 42
(lldb) (String) greeting = 6164403120
(Int) launches = 42
```

Next session, 18:18Z, same commands, LLDB's Swift metadata cache from the first session present:

```
(lldb) (String) greeting = "Hello from Omarchy Linux"
(Int) launches = 42
```

Session at 18:25Z with an empty cache (`settings set symbols.swift-metadata-cache-path` to a new
directory):

```
(lldb) (String) greeting = 6092755888
(lldb) (Swift.String) greeting = {
  utf16Length = 6092755888 {
    _value = 6092755888
  }
  crumbs = {
    _buffer = {
      _storage = {
        Swift.ManagedBuffer<Swift.Double.SIMD64Storage, Swift.AnyObject> = {
```

`utf16Length` and `crumbs` are the stored properties of the standard library's
`_StringBreadcrumbs`, not of `String`. In `libswiftCore`'s `__swift5_fieldmd`, the descriptor of
`String` (name `SS`, field `_guts`) is at 0x18223ca5c and the one of `_StringBreadcrumbs` follows it
at 0x18223ca78 (dump of the dylib extracted from the 24A446 shared cache).

Session at 19:16Z with an empty cache and the iOS 27.0.1 (24A446) Swift dylibs from Apple's IPSW
(`ipsw download ipsw --device iPhone16,2 --version 27.0.1 --dyld`, then `ipsw dyld extract --slide` of the
80 dylibs under `/usr/lib/swift/` and `libobjc`), passed as a sysroot:

```
(lldb) platform select remote-ios --sysroot "/home/joshuawarren/ios-devsupport/27.0.1 (24A446)"
   Sysroot: /home/joshuawarren/ios-devsupport/27.0.1 (24A446)
(String) greeting = "Hello from Omarchy Linux"
(Int) launches = 42
(lldb) image list libswiftCore.dylib
[  0] D65D98D2-5161-3FA0-9B03-7B7085A01DAC 0x000000018360e000 /home/joshuawarren/ios-devsupport/27.0.1 (24A446)/Symbols/usr/lib/swift/libswiftCore.dylib
```

The libobjc "being read from process memory" warning of the earlier sessions is gone. `expr greeting`
fails in every session: LLDB cannot load the Swift modules for the app ("could not load Swift
Standard Library").
