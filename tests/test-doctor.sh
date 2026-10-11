#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin"

cat >"$TMP/bin/swift" <<'EOF'
#!/bin/sh
if [ "$1" = sdk ]; then echo darwin; else echo 'Swift version test'; fi
EOF
cat >"$TMP/bin/xtool" <<'EOF'
#!/bin/sh
echo 'xtool test'
EOF
cat >"$TMP/bin/rcodesign" <<'EOF'
#!/bin/sh
echo 'rcodesign test'
EOF
cat >"$TMP/bin/usbmuxd" <<'EOF'
#!/bin/sh
exit 0
EOF
cat >"$TMP/bin/pgrep" <<'EOF'
#!/bin/sh
exit 1
EOF
cat >"$TMP/bin/systemctl" <<'EOF'
#!/bin/sh
exit 1
EOF
cat >"$TMP/bin/idevice_id" <<'EOF'
#!/bin/sh
echo TEST-UDID
EOF
chmod +x "$TMP/bin/"*

run_case() {
  name="$1" expected="$2" pair_text="$3" pair_rc="$4"
  cat >"$TMP/bin/idevicepair" <<EOF
#!/bin/sh
echo '$pair_text'
exit $pair_rc
EOF
  chmod +x "$TMP/bin/idevicepair"
  out="$(PATH="$TMP/bin:$PATH" "$ROOT/ubuntu-ios" doctor --device 2>&1 || true)"
  if ! grep -Fq "$expected" <<<"$out"; then
    echo "FAIL: $name" >&2
    echo "$out" >&2
    exit 1
  fi
  echo "PASS: $name"
}

run_case paired 'paired and trusted' 'SUCCESS: Validated pairing with device' 0
run_case unpaired 'not paired with this host' 'ERROR: Device is not paired with this host' 1
run_case trust 'waiting for Trust This Computer response' 'Please accept the trust dialog on the device' 1
run_case denied 'trust request denied on device' 'User denied the trust request' 1
run_case locked 'device locked; unlock it first' 'Device is locked with a passcode' 1

echo 'All doctor state tests passed.'

# Detection errors must be reported independently from pairing.
cat >"$TMP/bin/idevice_id" <<'EOF'
#!/bin/sh
echo 'ERROR: Unable to retrieve device list!' >&2
exit 1
EOF
chmod +x "$TMP/bin/idevice_id"
out="$(PATH="$TMP/bin:$PATH" "$ROOT/ubuntu-ios" doctor --device 2>&1 || true)"
grep -Fq 'Device detection       ERROR: ERROR: Unable to retrieve device list!' <<<"$out" || {
  echo 'FAIL: detection error reporting' >&2
  echo "$out" >&2
  exit 1
}
grep -Fq 'Pairing state          not checked (detection failed)' <<<"$out" || {
  echo 'FAIL: detection/pairing separation' >&2
  echo "$out" >&2
  exit 1
}
echo 'PASS: detection/pairing separation'
