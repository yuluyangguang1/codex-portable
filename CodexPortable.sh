#!/bin/bash
# ═══════════════════════════════════════════
# Codex CLI Portable + CC Switch · Linux
# ═══════════════════════════════════════════

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ARCH="$(uname -m)"

if [ "${1:-}" = "--unlock" ]; then
    LOCK_FILE="$SCRIPT_DIR/data/.lock"
    LOCK_FILE2="$SCRIPT_DIR/data/.cc-switch/.bind"
    REMOVED=0
    [ -f "$LOCK_FILE" ] && { rm -f "$LOCK_FILE"; REMOVED=1; }
    [ -f "$LOCK_FILE2" ] && { rm -f "$LOCK_FILE2"; REMOVED=1; }
    [ "$REMOVED" = "1" ] && echo "  [ok] 已移除绑定锁。" || echo "  [info] 没有绑定锁需要移除。"
    exit 0
fi

echo ""
echo "  Codex CLI Portable"
echo ""

# 架构检测（Linux 仅 x86_64）
case "$ARCH" in
    x86_64|amd64) BIN_DIR="$SCRIPT_DIR/bin/linux-x64" ;;
    aarch64|arm64) BIN_DIR="$SCRIPT_DIR/bin/linux-arm64" ;;
    *) echo "[ERROR] 不支持的架构: $ARCH"; exit 1 ;;
esac

if [ ! -f "$BIN_DIR/codex" ]; then
    echo "[ERROR] 未找到 Codex CLI: $BIN_DIR/codex"
    exit 1
fi

chmod +x "$BIN_DIR/codex" 2>/dev/null
[ -f "$BIN_DIR/cc-switch" ] && chmod +x "$BIN_DIR/cc-switch" 2>/dev/null

# 单实例锁
RUN_LOCK="$SCRIPT_DIR/data/.running"
mkdir -p "$SCRIPT_DIR/data"
if [ -f "$RUN_LOCK" ]; then
    PREV_PID=$(cat "$RUN_LOCK" 2>/dev/null | head -1 | tr -d '[:space:]')
    if [ -n "${PREV_PID:-}" ] && kill -0 "$PREV_PID" 2>/dev/null; then
        echo "  [info] 已有另一个实例正在运行 (PID $PREV_PID)。"
        exit 1
    fi
    rm -f "$RUN_LOCK"
fi
echo $$ > "$RUN_LOCK"

# 便携目录
PORTABLE_DATA="$SCRIPT_DIR/data"
PORTABLE_CCS="$PORTABLE_DATA/.cc-switch"
PORTABLE_CODEX="$PORTABLE_DATA/.codex"
SYS_CCS="$HOME/.cc-switch"
SYS_CODEX="$HOME/.codex"
LIB_DIR="$SCRIPT_DIR/lib"
LOCK_FILE="$PORTABLE_DATA/.lock"
LOCK_FILE2="$PORTABLE_CCS/.bind"

mkdir -p "$PORTABLE_CCS" "$PORTABLE_CODEX"

# 设备绑定校验
LOCK_PRESENT=0
[ -f "$LOCK_FILE" ] && LOCK_PRESENT=1
[ -f "$LOCK_FILE2" ] && LOCK_PRESENT=1
if [ "$LOCK_PRESENT" = "1" ] && [ -f "$LIB_DIR/binding.sh" ]; then
    chmod +x "$LIB_DIR/binding.sh" 2>/dev/null
    ACTIVE_LOCK="$LOCK_FILE"
    [ ! -f "$LOCK_FILE" ] && ACTIVE_LOCK="$LOCK_FILE2"
    bash "$LIB_DIR/binding.sh" check "$SCRIPT_DIR" "$ACTIVE_LOCK"
    bind_result=$?
    if [ $bind_result -eq 1 ]; then
        echo ""
        echo "  [ERROR] 此便携包已绑定到原始设备。"
        echo "  解绑：./CodexPortable.sh --unlock"
        echo ""
        exit 1
    fi
fi

# 迁移
migrate_dir() {
    local src="$1" dst="$2"
    if [ -d "$src" ] && [ ! -L "$src" ] && [ -n "$(ls -A "$src" 2>/dev/null)" ] && [ -z "$(ls -A "$dst" 2>/dev/null)" ]; then
        echo "  [migrate] $src → $dst"
        cp -a "$src/." "$dst/" 2>/dev/null
    fi
}
migrate_dir "$SYS_CCS" "$PORTABLE_CCS"
migrate_dir "$SYS_CODEX" "$PORTABLE_CODEX"

# 符号链接
ensure_symlink() {
    local link="$1" target="$2"
    if [ -L "$link" ]; then
        [ "$(readlink "$link")" = "$target" ] && return 0
        rm "$link" 2>/dev/null
    elif [ -d "$link" ]; then
        rmdir "$link" 2>/dev/null || rm -rf "$link" 2>/dev/null
    fi
    ln -s "$target" "$link" 2>/dev/null
}
ensure_symlink "$SYS_CCS" "$PORTABLE_CCS"
ensure_symlink "$SYS_CODEX" "$PORTABLE_CODEX"

CC_SWITCH_PID=""
WE_STARTED_CCS=0

cleanup() {
    if [ "$WE_STARTED_CCS" = "1" ] && [ -n "${CC_SWITCH_PID:-}" ] && kill -0 "$CC_SWITCH_PID" 2>/dev/null; then
        kill -TERM "$CC_SWITCH_PID" 2>/dev/null
        for _ in 1 2 3 4 5; do
            kill -0 "$CC_SWITCH_PID" 2>/dev/null || break
            sleep 1
        done
        kill -0 "$CC_SWITCH_PID" 2>/dev/null && kill -9 "$CC_SWITCH_PID" 2>/dev/null
    fi
    [ -L "$SYS_CCS" ] && rm "$SYS_CCS" 2>/dev/null
    [ -L "$SYS_CODEX" ] && rm "$SYS_CODEX" 2>/dev/null
    [ -f "$RUN_LOCK" ] && rm -f "$RUN_LOCK"
}
trap cleanup EXIT INT TERM

# 配置检查
has_valid_config() {
    local auth_file="$PORTABLE_CODEX/auth.json"
    [ -f "$auth_file" ] || return 1
    local size
    size=$(stat -c%s "$auth_file" 2>/dev/null || echo 0)
    [ "$size" -lt 20 ] && return 1
    if command -v python3 &>/dev/null; then
        AUTH_FILE="$auth_file" python3 - <<'PYEOF' 2>/dev/null
import os, json, sys
try:
    with open(os.environ['AUTH_FILE'], 'r') as f:
        data = json.load(f)
    key = data.get('OPENAI_API_KEY', '')
    tokens = data.get('tokens', {})
    if (key and len(key) > 5) or (tokens and tokens.get('access_token')):
        sys.exit(0)
except Exception:
    pass
sys.exit(1)
PYEOF
        return $?
    fi
    return 0
}

if ! has_valid_config; then
    echo "═══════════════════════════════════════════"
    echo "  首次运行 - 配置 API"
    echo "═══════════════════════════════════════════"
    echo ""
    if [ -f "$BIN_DIR/cc-switch" ]; then
        echo "  正在打开 CC Switch GUI..."
        "$BIN_DIR/cc-switch" >/dev/null 2>&1 &
        CC_SWITCH_PID=$!
        WE_STARTED_CCS=1
    else
        echo "  [warn] 未找到 cc-switch GUI，请手动配置 $PORTABLE_CODEX/auth.json"
    fi
    echo "  等待配置..."
    for i in $(seq 1 150); do
        sleep 2
        has_valid_config && { echo "  [ok] 配置已就绪"; sleep 1; break; }
    done
    has_valid_config || { echo "  [!] 等待超时"; exit 1; }
fi

# 创建绑定锁
if [ -f "$LIB_DIR/binding.sh" ]; then
    [ ! -f "$LOCK_FILE" ] && bash "$LIB_DIR/binding.sh" create "$SCRIPT_DIR" "$LOCK_FILE" 2>/dev/null
    [ ! -f "$LOCK_FILE2" ] && bash "$LIB_DIR/binding.sh" create "$SCRIPT_DIR" "$LOCK_FILE2" 2>/dev/null
fi

# 启动
echo "  架构: $ARCH | 数据: 便携包内"
echo ""
export CODEX_HOME="$PORTABLE_CODEX"
"$BIN_DIR/codex" "$@"
exit $?
