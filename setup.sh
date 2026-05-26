#!/bin/bash
# Local build script — downloads codex binaries for the current platform
# Usage:
#   bash setup.sh               # current platform
#   bash setup.sh --all          # all platforms (for USB distribution)
#   bash setup.sh --version rust-v0.133.0

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

VER=""
ALL=0
while [ $# -gt 0 ]; do
    case "$1" in
        --version) VER="$2"; shift 2 ;;
        --all)     ALL=1; shift ;;
        -h|--help)
            echo "Usage: bash setup.sh [--all] [--version <tag>]"
            exit 0
            ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

if [ -z "$VER" ]; then
    echo "  [info] Resolving latest Codex release..."
    VER=$(curl -fsSL https://api.github.com/repos/openai/codex/releases/latest | grep -m1 tag_name | cut -d '"' -f 4)
    if [ -z "$VER" ]; then
        echo "  [!] Failed to resolve latest version. Specify with --version."
        exit 1
    fi
fi
echo "  Codex version: $VER"

BASE="https://github.com/openai/codex/releases/download/${VER}"

download() {
    local target_dir="$1" archive_name="$2" want_exe="$3"
    mkdir -p "$target_dir"
    echo "  [download] $archive_name → $target_dir/"
    if [[ "$archive_name" == *.tar.gz ]]; then
        curl -fsSL "${BASE}/${archive_name}" | tar -xz -C "$target_dir"
    else
        curl -fsSL -o "$target_dir/_download" "${BASE}/${archive_name}"
        tar -xzf "$target_dir/_download" -C "$target_dir"
        rm -f "$target_dir/_download"
    fi
    # Normalize name to "codex" or "codex.exe"
    if [ "$want_exe" = "1" ]; then
        if [ ! -f "$target_dir/codex.exe" ]; then
            local found
            found=$(find "$target_dir" -maxdepth 2 -type f -name '*.exe' | head -1 || true)
            [ -n "$found" ] && mv "$found" "$target_dir/codex.exe"
        fi
    else
        if [ ! -f "$target_dir/codex" ]; then
            local found
            found=$(find "$target_dir" -maxdepth 2 -type f -name 'codex*' ! -name '*.tar*' ! -name '*.exe' | head -1 || true)
            [ -n "$found" ] && mv "$found" "$target_dir/codex"
        fi
        chmod +x "$target_dir/codex" 2>/dev/null || true
    fi
}

OS="$(uname -s)"
ARCH="$(uname -m)"

if [ "$ALL" = "1" ]; then
    download bin/macos-arm64  codex-aarch64-apple-darwin.tar.gz       0
    download bin/macos-x64    codex-x86_64-apple-darwin.tar.gz        0
    download bin/linux-x64    codex-x86_64-unknown-linux-musl.tar.gz  0
    download bin/windows-x64  codex-x86_64-pc-windows-msvc.exe.tar.gz 1
else
    case "$OS-$ARCH" in
        Darwin-arm64)   download bin/macos-arm64 codex-aarch64-apple-darwin.tar.gz       0 ;;
        Darwin-x86_64)  download bin/macos-x64   codex-x86_64-apple-darwin.tar.gz        0 ;;
        Linux-x86_64)   download bin/linux-x64   codex-x86_64-unknown-linux-musl.tar.gz  0 ;;
        Linux-aarch64)  download bin/linux-arm64 codex-aarch64-unknown-linux-musl.tar.gz 0 ;;
        *) echo "  [!] Unsupported platform: $OS-$ARCH"; exit 1 ;;
    esac
fi

echo ""
echo "  [done] Codex binaries ready."
echo ""
echo "  Next step: drop a cc-switch binary into the matching bin/ folder."
echo "  Get it from: https://github.com/farion1231/cc-switch/releases"
echo ""
echo "  Then launch:"
case "$OS" in
    Darwin) echo "    ./CodexPortable.command" ;;
    Linux)  echo "    ./CodexPortable.sh" ;;
esac
