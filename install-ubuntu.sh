#!/usr/bin/env bash
set -euo pipefail
SWIFT_VERSION="${SWIFT_VERSION:-6.3.3}"
PREFIX="${PREFIX:-$HOME/.local/ubuntu-ios-toolchain}"
SWIFT_PREFIX="${SWIFT_PREFIX:-$HOME/.local/swift-$SWIFT_VERSION}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JOBS="${JOBS:-$(nproc)}"

[[ "$(uname -s)" == Linux ]] || { echo "Linux required." >&2; exit 1; }
grep -qi '^ID=ubuntu' /etc/os-release || echo "Warning: this installer is designed for Ubuntu."
[[ "$(uname -m)" == x86_64 ]] || { echo "Currently tested on Ubuntu x86_64 only." >&2; exit 2; }

sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
 build-essential git curl ca-certificates pkg-config autoconf automake libtool cmake ninja-build \
 python3 python3-venv python3-pip unzip zip xz-utils zstd rsync jq \
 libssl-dev libcurl4-openssl-dev libxml2-dev libsqlite3-dev libedit-dev libncurses-dev \
 libusb-1.0-0-dev usbmuxd libusbmuxd-dev libimobiledevice-dev libimobiledevice-utils libplist-dev poppler-utils libheif-examples

if [[ ! -x "$SWIFT_PREFIX/usr/bin/swift" ]]; then
  URL="https://download.swift.org/swift-${SWIFT_VERSION}-release/ubuntu2404/swift-${SWIFT_VERSION}-RELEASE/swift-${SWIFT_VERSION}-RELEASE-ubuntu24.04.tar.gz"
  TMP=$(mktemp -d)
  echo "Downloading official Swift $SWIFT_VERSION for Ubuntu 24.04..."
  curl -fL "$URL" -o "$TMP/swift.tar.gz"
  mkdir -p "$SWIFT_PREFIX"
  tar -xzf "$TMP/swift.tar.gz" --strip-components=1 -C "$SWIFT_PREFIX"
  rm -r "$TMP"
fi
export PATH="$SWIFT_PREFIX/usr/bin:$HOME/.local/bin:$PATH"

mkdir -p "$PREFIX/src" "$PREFIX/lib" "$PREFIX/bin"
export PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig:$PREFIX/lib/x86_64-linux-gnu/pkgconfig:${PKG_CONFIG_PATH:-}"
export LD_LIBRARY_PATH="$PREFIX/lib:$PREFIX/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}"
export PATH="$PREFIX/bin:$PATH"

build_dep() {
  name="$1"; repo="$2"; ref="$3"; src="$PREFIX/src/$name"
  [[ -d "$src/.git" ]] || git clone --depth 1 --branch "$ref" "$repo" "$src"
  (cd "$src"; ./autogen.sh --prefix="$PREFIX" --without-cython >/dev/null; make -j"$JOBS" >/dev/null; make install >/dev/null)
}
build_dep libplist https://github.com/libimobiledevice/libplist.git 2.8.0
build_dep libimobiledevice-glue https://github.com/libimobiledevice/libimobiledevice-glue.git 1.3.0
build_dep libtatsu https://github.com/libimobiledevice/libtatsu.git 1.0.5
build_dep libimobiledevice https://github.com/libimobiledevice/libimobiledevice.git 1.4.0

"$REPO_DIR/install-toolchain-upstream.sh" --user-only

mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/ubuntu-ios" <<WRAP
#!/usr/bin/env bash
export PATH="$SWIFT_PREFIX/usr/bin:\$HOME/.local/bin:\$PATH"
export PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig:$PREFIX/lib/x86_64-linux-gnu/pkgconfig:\${PKG_CONFIG_PATH:-}"
export LD_LIBRARY_PATH="$PREFIX/lib:$PREFIX/lib/x86_64-linux-gnu:\${LD_LIBRARY_PATH:-}"
exec "$REPO_DIR/ubuntu-ios" "\$@"
WRAP
chmod +x "$HOME/.local/bin/ubuntu-ios"

echo "Installed. Next: ubuntu-ios sdk /path/to/Xcode_26.xip"
echo "Then run: ubuntu-ios doctor"
