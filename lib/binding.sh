#!/bin/bash
# USB drive binding for Claude Portable (macOS + Linux)
# Computes SHA256 hash of the filesystem UUID (or volume identifier).
#
# Modes:
#   check  <portable_dir> <lock_file>  → exit 0 if match, 1 if mismatch, 2 if no lock
#   create <portable_dir> <lock_file>  → write current fingerprint hash to lock file
# Exit 3 = couldn't compute fingerprint (fail closed)

set -u

MODE="${1:-}"
PORTABLE_DIR="${2:-}"
LOCK_FILE="${3:-}"

if [ -z "$MODE" ] || [ -z "$PORTABLE_DIR" ] || [ -z "$LOCK_FILE" ]; then
    echo "Usage: $0 {check|create} <portable_dir> <lock_file>" >&2
    exit 5
fi

get_fingerprint() {
    local path="$1"
    local abs
    abs=$(cd "$path" 2>/dev/null && pwd) || return 1
    [ -n "$abs" ] || return 1

    local os
    os=$(uname -s)

    if [ "$os" = "Darwin" ]; then
        # macOS: use diskutil to get volume UUID
        local mount_point
        # df -P 强制单行输出。Mount point 是第 6 列起到行尾（可能含空格）。
        # 用 awk 提取 $6, $7, ... 拼接，比反向扫描更稳健
        # （反向找第一个 / 的旧写法会把含空格的挂载点解析错）。
        mount_point=$(df -P "$abs" 2>/dev/null | tail -1 | awk '{
            line=""
            for (i=6; i<=NF; i++) {
                if (i>6) line = line " "
                line = line $i
            }
            print line
        }')
        [ -z "$mount_point" ] && return 1
        # Try Volume UUID first
        local uuid
        uuid=$(diskutil info "$mount_point" 2>/dev/null | awk -F': *' '/Volume UUID/ { print $2; exit }' | tr -d '[:space:]')
        if [ -n "$uuid" ]; then echo "uuid:$uuid"; return 0; fi
        # Fallback: Disk / Partition UUID
        uuid=$(diskutil info "$mount_point" 2>/dev/null | awk -F': *' '/Disk \/ Partition UUID/ { print $2; exit }' | tr -d '[:space:]')
        if [ -n "$uuid" ]; then echo "puuid:$uuid"; return 0; fi
        # Last resort: device node (changes if drive remounted as different device)
        local dev
        dev=$(df -P "$abs" 2>/dev/null | tail -1 | awk '{print $1}')
        [ -n "$dev" ] && { echo "dev:$dev"; return 0; }
    else
        # Linux: use findmnt or blkid for filesystem UUID
        local dev
        dev=$(df -P "$abs" 2>/dev/null | tail -1 | awk '{print $1}')
        [ -z "$dev" ] && return 1
        # Try findmnt (most reliable, doesn't need root)
        local uuid
        uuid=$(findmnt -no UUID --target "$abs" 2>/dev/null)
        if [ -n "$uuid" ]; then echo "uuid:$uuid"; return 0; fi
        # Try blkid (may need root on some systems)
        uuid=$(blkid -s UUID -o value "$dev" 2>/dev/null)
        if [ -n "$uuid" ]; then echo "uuid:$uuid"; return 0; fi
        # /dev/disk/by-uuid scan
        for link in /dev/disk/by-uuid/*; do
            [ -e "$link" ] || continue
            if [ "$(readlink -f "$link")" = "$(readlink -f "$dev")" ]; then
                echo "uuid:$(basename "$link")"
                return 0
            fi
        done
        # Last resort: device node
        echo "dev:$dev"
        return 0
    fi
    return 1
}

compute_hash() {
    local input="$1"
    [ -z "$input" ] && return 1
    local salted="CodexPortable-v1::${input}"
    if command -v sha256sum >/dev/null 2>&1; then
        printf '%s' "$salted" | sha256sum | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        printf '%s' "$salted" | shasum -a 256 | awk '{print $1}'
    elif command -v openssl >/dev/null 2>&1; then
        printf '%s' "$salted" | openssl dgst -sha256 | awk '{print $NF}'
    else
        return 1
    fi
}

fingerprint=$(get_fingerprint "$PORTABLE_DIR")
if [ -z "$fingerprint" ]; then
    exit 3
fi
current_hash=$(compute_hash "$fingerprint")
if [ -z "$current_hash" ]; then
    exit 3
fi

case "$MODE" in
    check)
        [ -f "$LOCK_FILE" ] || exit 2
        stored=$(tr -d '[:space:]' < "$LOCK_FILE")
        [ "$current_hash" = "$stored" ] && exit 0 || exit 1
        ;;
    create)
        printf '%s' "$current_hash" > "$LOCK_FILE" 2>/dev/null || exit 4
        exit 0
        ;;
    *)
        exit 5
        ;;
esac
