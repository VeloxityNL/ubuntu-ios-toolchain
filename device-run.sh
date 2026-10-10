#!/usr/bin/env bash
# Run an xtool project on an iPhone from Omarchy Linux.
# Run this from inside your xtool project directory (the one with xtool.yml).
# First run ever: do `xtool auth` once beforehand (interactive Apple ID sign-in).
#
# Modes:
#   ./device-run.sh [--lldb]               USB (default; the proven path). --lldb then
#       starts LLDB on the app (sudo for the tunnel; FINDINGS.md 56).
#   ./device-run.sh --network [--udid U]   WiFi, phone on the SAME network.
#       TESTED EXHAUSTIVELY 2026-09-16 on iOS 26.6.2: BLOCKED for hosts the
#       phone has no RemotePairing tunnel with. iOS gives every host its own
#       encrypted tunnel (`<uuid>._rp-tunnel._tcp`, ephemeral port), accepts
#       nobody else, and offers no device-side pairing screen to add a host
#       (that flow is iOS 27+). A Mac that once enabled "Connect via Network"
#       keeps a working wireless tunnel; a Linux host cannot get one today.
#       Full evidence in FINDINGS.md 17. Use USB, or the tunneld bridge below
#       through a Mac that holds the tunnel.
#   ./device-run.sh --rsd HOST PORT PKG    install+launch an already-signed
#       .app/.ipa against an explicit RemoteServiceDiscovery address. Works
#       against tunnels you DO hold: the RSD endpoint printed by
#       `sudo pymobiledevice3 lockdown start-tunnel` (USB) or a tunneld
#       instance. Addressing the phone's WiFi interfaces directly does not
#       work on iOS 26 (per-host tunnel gating, FINDINGS.md 17).
#       PKG must be signed with a real certificate: xtool's free-provisioning
#       signing only happens inside `xtool dev run`.
#
# Tailscale: mDNS discovery does not cross tailscale0, and Apple's remoted
# binds the phone's LAN interface, so a phone reachable only via Tailscale is
# not directly deployable. The supported remote pattern is pymobiledevice3's
# tunneld WebSocket bridge -- on a machine that CAN see the phone (USB or
# same LAN):
#     sudo pymobiledevice3 remote tunneld        # prints its WS port
# then, from the remote host:
#     pymobiledevice3 apps install PKG --tunnel UDID@BRIDGE_HOST:WS_PORT
#     pymobiledevice3 developer core-device launch-application BID "" \
#         --tunnel UDID@BRIDGE_HOST:WS_PORT
set -euo pipefail
# The toolchain's own bin dir (lldb) first: /usr/lib/swift/bin on swift-bin
# 6.3, /usr/lib/swift/usr/bin on 6.4, elsewhere under mise.
PATH="$(dirname "$(readlink -f "$(command -v swift)")"):$PATH"
export PATH

XT="$HOME/.local/bin/xtool"
PMD3="$HOME/pymobile3-venv/bin/pymobiledevice3"

MODE=usb; UDID=; RSD_HOST=; RSD_PORT=; PKG=; LLDB=0
while [ $# -gt 0 ]; do
  case "$1" in
    --network) MODE=network ;;
    --lldb) LLDB=1 ;;
    -u|--udid) UDID="${2:?--udid needs a value}"; shift ;;
    --rsd) MODE=rsd
      RSD_HOST="${2:?usage: --rsd HOST PORT PACKAGE}"
      RSD_PORT="${3:?usage: --rsd HOST PORT PACKAGE}"
      PKG="${4:?usage: --rsd HOST PORT PACKAGE}"
      shift 3 ;;
    *) echo "Unknown argument: $1 (modes: [--lldb] [--network] [--rsd HOST PORT PKG])" >&2; exit 2 ;;
  esac
  shift
done

UDID_ARGS=()
if [ -n "$UDID" ]; then UDID_ARGS=(--udid "$UDID"); fi

# Xcode 27.0's personalized Developer Disk Image, pinned by checksum. DDI_DIR overrides it, e.g. a
# copy of a Mac's /Library/Developer/DeveloperDiskImages/iOS_DDI.
DDI_URL=https://raw.githubusercontent.com/DeveloperDiskImages/DeveloperDiskImages/136b031cf581985c0663847915fd404d6fec2d5f/PersonalizedImages/iOS_DDI
DDI_FILES="05beb4f7a054ea1d53f49b04aaf0a210814e4cfa7d2ba9790b03b01c48ea8a6e Restore/BuildManifest.plist
c7cbaf4f8a94d4b4c1fe9aad21b7c74a1848cfd0139c3030a4082b8b0f6af9b3 Restore/022-20190-411.dmg
04dd84b0affafedf86c7ada177a5c2289a1ad197caf7cfded9ccf1dc0a310eb0 Restore/Firmware/022-20190-411.dmg.trustcache"

# Mount the DDI, open an RSD tunnel, give LLDB the phone's Swift runtime on disk, attach to the app.
lldb_session() {
  local bid ddi info sym log host port wrap
  bid=$(grep -E '^bundleID:' xtool.yml | awk '{print $2}')
  # xtool may prefix the bundle id (XTL-<team>.<id>); find the installed one.
  bid=$("$PMD3" apps list "${UDID_ARGS[@]}" 2>/dev/null | python3 -c '
import json, sys
b = sys.argv[1]
print(next(k for k in json.load(sys.stdin) if k == b or k.endswith("." + b)))' "$bid")
  ddi=${DDI_DIR:-$HOME/.cache/omarchy-apple-dev/iOS_DDI}
  if [ -z "${DDI_DIR:-}" ]; then
    while read -r sha f; do
      if ! echo "$sha  $ddi/$f" | sha256sum -c --status 2>/dev/null; then
        mkdir -p "$(dirname "$ddi/$f")"
        curl -fsSL "$DDI_URL/$f" -o "$ddi/$f"
        echo "$sha  $ddi/$f" | sha256sum -c --quiet
      fi
    done <<<"$DDI_FILES"
  fi
  info=$("$PMD3" lockdown info "${UDID_ARGS[@]}")
  if ! sudo "$PMD3" mounter list "${UDID_ARGS[@]}" 2>/dev/null | grep -qi personalized; then
    # The image and trust cache of a build identity for this phone's chip.
    read -r dmg tc < <(python3 -c '
import json, plistlib, sys
d = json.loads(sys.argv[2])
m = plistlib.load(open(sys.argv[1], "rb"))
for b in m["BuildIdentities"]:
    if "PersonalizedDMG" in b["Manifest"] and int(b["ApChipID"], 16) == d["ChipID"]:
        print(b["Manifest"]["PersonalizedDMG"]["Info"]["Path"], b["Manifest"]["LoadableTrustCache"]["Info"]["Path"])
        break' "$ddi/Restore/BuildManifest.plist" "$info")
    sudo "$PMD3" mounter mount-personalized "${UDID_ARGS[@]}" "$ddi/Restore/$dmg" "$ddi/Restore/$tc" \
      "$ddi/Restore/BuildManifest.plist"
  fi
  log=$(mktemp)
  sudo "$PMD3" lockdown start-tunnel "${UDID_ARGS[@]}" >"$log" 2>&1 &
  trap 'sudo pkill -f "lockdown start-tunne[l]"' EXIT
  for _ in $(seq 30); do grep -q "RSD Port" "$log" && break; sleep 1; done
  host=$(grep -o "RSD Address: [^ ]*" "$log" | awk '{print $3}')
  port=$(grep -o "RSD Port: [0-9]*" "$log" | awk '{print $3}')
  [ -n "$port" ] || { cat "$log"; exit 1; }
  # Linux LLDB reads the Swift runtime from process memory unless it has the dylibs of the
  # phone's exact iOS build on disk, and then misreads String (FINDINGS.md 56).
  sym="$HOME/.cache/omarchy-apple-dev/DeviceSupport/$(python3 -c '
import json, sys
d = json.loads(sys.argv[1])
print(d["ProductVersion"] + " (" + d["BuildVersion"] + ")")' "$info")"
  if [ ! -f "$sym/Symbols/usr/lib/swift/libswiftCore.dylib" ]; then
    echo "Copying the shared cache from the iPhone (once per iOS build, a few GB)"
    "$PMD3" developer fetch-symbols download "$sym/dsc" --rsd "$host" "$port"
    dsc=$(find "$sym/dsc" -name dyld_shared_cache_arm64e | head -n1)
    "$HOME/.local/bin/ipsw" dyld info "$dsc" --dylibs 2>/dev/null | grep -o '/[^ ]*$' |
      grep -E '^/usr/lib/(swift/|libobjc)' | while read -r p; do
        mkdir -p "$sym/Symbols$(dirname "$p")"
        "$HOME/.local/bin/ipsw" dyld extract "$dsc" "$(basename "$p")" --slide -o "$sym/Symbols$(dirname "$p")" >/dev/null
      done
  fi
  # pymobiledevice3 sends its own "platform select remote-ios"; add the sysroot to it.
  # LLDB_PYTHONHOME: a CPython of the version lldb links (3.12 for Swift 6.4), when the system
  # has none. It goes to lldb only; pymobiledevice3 and python3 here use their own Python.
  wrap=$(mktemp)
  {
    echo '#!/bin/bash'
    if [ -n "${LLDB_PYTHONHOME:-}" ]; then
      printf 'export PYTHONHOME=%q LD_LIBRARY_PATH=%q\n' "$LLDB_PYTHONHOME" "$LLDB_PYTHONHOME/lib"
    fi
    printf 'exec lldb "$@" < <(sed -u "s|^platform select remote-ios\\$|platform select remote-ios --sysroot \\"%s\\"|")\n' "$sym"
  } >"$wrap"
  chmod +x "$wrap"
  sudo env PATH="$PATH" "$PMD3" developer debugserver lldb "$bid" --rsd "$host" "$port" --lldb-command "$wrap"
}

case "$MODE" in
usb)
  echo "== 1. Device visible over USB? =="
  # usbmuxd is started by udev when a device is plugged in. Nothing to enable.
  lsusb | grep -i apple || echo "WARNING: no Apple USB device found by lsusb."

  echo "== 2. Trust and pair =="
  # The phone shows a 'Trust This Computer' prompt on first connect. Accept it.
  $PMD3 lockdown info >/dev/null 2>&1 \
    && echo "Lockdown reachable, pairing OK." \
    || { echo "Pairing needed: run '$PMD3 lockdown pair' and accept the prompt on the phone."; }

  echo "== 3. List devices via xtool =="
  $XT devices "${UDID_ARGS[@]}"

  echo "== 4. Build, sign, install, launch =="
  # Signing uses your Apple ID (free tier works); the first deploy creates a free
  # provisioning profile for your device.
  if [ "$LLDB" = 0 ]; then
    $XT dev run "${UDID_ARGS[@]}"
  else
    # LLDB launches the app itself, stopped, so breakpoints in startup code hit.
    $XT dev build
    $XT install "${UDID_ARGS[@]}" "$(ls -d xtool/*.app | head -n1)"
    echo "== 5. LLDB =="
    lldb_session
  fi
  ;;
network)
  echo "== WiFi deploy (phone on the same network) -- UNVERIFIED =="
  echo "Expects: paired over USB once, Developer Mode on, same LAN segment."
  $XT devices --network
  $XT dev run --network "${UDID_ARGS[@]}"
  ;;
rsd)
  echo "== Install/launch via RSD $RSD_HOST:$RSD_PORT -- UNVERIFIED =="
  $PMD3 apps install "$PKG" --rsd "$RSD_HOST" "$RSD_PORT"
  BID=$(grep -E '^bundleID:' xtool.yml | awk '{print $2}')
  if [ -z "$BID" ]; then echo "No bundle_id in xtool.yml; launch it by hand:"; else
    $PMD3 developer core-device launch-application "$BID" "" --rsd "$RSD_HOST" "$RSD_PORT"
  fi
  ;;
esac
