# ubi9 Swift on Omarchy: the missing sonames, and mise working end to end

Host jwm1-linux, Omarchy 4.0.1rc2 aarch64, ncurses 6.6-2.
mise git build at `533346cc` (post #13293 + #13297).
Tarball: `swift-6.3.3-RELEASE-ubi9-aarch64.tar.gz`, 1001 MB.

## Complete set of missing sonames

`ldd` across all of `usr/bin` + `usr/lib/*.so*`:

```
libform.so.6
libncurses.so.6
libpanel.so.6
```

Host: `libncursesw.so.6`, `libformw.so.6`, `libpanelw.so.6` present.
`libtinfo.so.6` present. `libncurses.so.6` absent.
`/usr/lib/libncurses.so` is an 18-byte linker script.

## Why narrow→wide substitution is sound here

- `liblldb.so` wide-char curses imports (`_wch|_wstr|cchar`): **0**
- narrow imports observed: `keypad`, `newwin` (plus form/panel entry points)
- Arch exports them versioned: `keypad@@NCURSES6_TINFO_5.0.19991023`,
  `newwin@@NCURSESW6_5.1.20000708`, `new_form@@NCURSESW6_…`,
  `new_panel@@NCURSESW6_…`
- `readelf -V` on `liblldb.so`: **no version requirement** recorded against
  libncurses/libform/libpanel
- `ldd -r` with the wide libs substituted: `lldb` ALL RESOLVED,
  `liblldb.so` ALL RESOLVED, zero undefined symbols, zero version warnings

Debian/Ubuntu ship a single wide-compiled ncurses providing both sonames,
so the vendor tarball is already running against a wide build there.

## Shim (no root, no /usr/lib mutation)

```bash
mkdir -p ~/.local/lib/curses-narrow-compat
ln -sf /usr/lib/libncursesw.so.6 ~/.local/lib/curses-narrow-compat/libncurses.so.6
ln -sf /usr/lib/libformw.so.6    ~/.local/lib/curses-narrow-compat/libform.so.6
ln -sf /usr/lib/libpanelw.so.6   ~/.local/lib/curses-narrow-compat/libpanel.so.6
export LD_LIBRARY_PATH=~/.local/lib/curses-narrow-compat
```

## Results with the shim

Direct from the extracted tree:

- `swiftc h.swift -o h && ./h` → `hello from ubi9 swift on omarchy`
- `lldb --version` → `lldb version 21.0.0 (… revision 82cdc19fa54d)`
- `swift package init` + `swift build` → `Build complete! (1.53s)`

Through mise:

- `mise install swift@6.3.3` → passes its own gate, printing
  `Swift version 6.3.3 (swift-6.3.3-RELEASE)` /
  `Target: aarch64-unknown-linux-gnu`; `mise ✓ swift@6.3.3 49.1s`
- `mise ls swift` → `swift 6.3.3`
- `mise exec swift@6.3.3 -- swift build` → `Build complete! (1.47s)`

## Second mise gap found

`LD_LIBRARY_PATH` set in `mise.toml` `[env]` (shell var unset) does **not**
reach the post-extract verification child:

```
mise ✗ swift@6.3.3  48.3s · failed: …/installs/swift/6.3.3/bin/swift exited with non-zero status: exit code 127
```

Same 1 GB download wasted, same bare `exit code 127` with no named library.
Two reportable items: (1) config `[env]` is not applied to the install
verification step; (2) when a fallback artifact cannot be loaded, report the
missing soname instead of `exit code 127`.

Pre-existing and unrelated: `swift runtime: unable to protect path to
swift-backtrace … disabling backtracing` appears on the AUR `swift-bin`
toolchain too.

Scratch left on jwm1: `~/tmp/ubi9-probe/`, `~/.cache/mise-retest/`.

## Upstream, 2026-09-17

- Retest comment on #13289: https://github.com/jdx/mise/discussions/13289#discussioncomment-18482797
- Retest comment on #13291: https://github.com/jdx/mise/discussions/13291#discussioncomment-18482798
- New report #13306 (ubi9 exit 127 + config [env] not reaching install verification): https://github.com/jdx/mise/discussions/13306

Shipped here as `install-toolchain.sh --curses-compat` (commit a661c15), verified
on jwm1: flag reports all sonames resolve, `mise install swift@6.3.3` passes its
own gate, `mise exec -- swift build` links and the binary prints Hello, world!

## lldb --gui smoke test — PASS (2026-09-18, jw16mbp1-linux / M1 Max)

jwm1 was asleep, so the test ran on a second Omarchy arm64 machine —
which also proved the fix generalizes beyond the original host.

jw16 differences discovered and handled:

- libxml2 2.15.4 (soname .16): the ubi9 lldb wants libxml2.so.2. A
  .2->.16 alias RESOLVES CLEAN under ldd -r — no xml-symbol failures,
  only harmless "no version information available" loader warnings.
  Caveat recorded: xml-dependent lldb features are unexercised.
- libpython3.9.so.1.0: genuinely required, no alias possible —
  _Py_IsFinalizing no longer exists in python 3.14 (real ABI break).
  Source used: Rocky 9 python3-libs rpm
  (python3-libs-3.9.25-7.el9_8.aarch64), extracted user-space only,
  symlinked into the compat dir. jwm1 already had it via swift-bin's
  python39 dependency.

GUI test under tmux (110x32), lldb -o gui from the extracted ubi9 tree,
LD_LIBRARY_PATH = curses compat + xml alias:

- curses TUI rendered: menu bar (LLDB F1 | Target F2 | Process F3 |
  Thread F4 | View F5 | Help F6), Sources and Threads panes.
- F1 opened the About/Exit dropdown; Down + Enter selected Exit.
- Clean teardown to the (lldb) prompt; "no target" state correct.
- Embedded python also verified: `script print(1+1)` -> 2 with
  PYTHONHOME pointed at the extracted Rocky python tree.

Draw, input handling, and teardown all exercise the narrow->wide curses
substitution. FINDINGS 21 updated.

Scratch on jw16: ~/tmp/ubi9-gui/ (tarballs + extracted tree, 4 GB).

## jdx shipped all four fixes; verified on a second host (2026-09-18)

mise main (b467f28c, v2026.9.11-dev) built and run on jw16mbp1-linux
(M1 Max, Omarchy arm64 — lacks all three sonames):

- Bare install now fails in 15.5s naming everything at once:
  `this swift build needs shared libraries missing from this host:
  libform.so.6, libncurses.so.6, libpanel.so.6` (#13319 + #13315).
- `install_env = { LD_LIBRARY_PATH = "{{env.HOME}}/…` renders and reaches
  the install verification (#13314); install passes.
- Runtime via `[env]` works; `swift build` + binary run green
  (Build complete! 1.35s / Hello, world!).
- jw16 extras: libxml2.so.2 alias (to .so.16) needed for
  swift-package/swift-build; real libpython3.9.so.1.0 (Rocky 9 rpm)
  needed for lldb. Added to the compat dir on that host.

Verification comment posted:
https://github.com/jdx/mise/discussions/13306#discussioncomment-18501815
