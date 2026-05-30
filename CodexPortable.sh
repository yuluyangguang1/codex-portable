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

# 单实例锁（原子 mkdir）
RUN_LOCK="$SCRIPT_DIR/data/.running"
mkdir -p "$SCRIPT_DIR/data"
if [ -d "$RUN_LOCK" ]; then
    PREV_PID=""
    [ -f "$RUN_LOCK/pid" ] && PREV_PID=$(cat "$RUN_LOCK/pid" 2>/dev/null | tr -d '[:space:]')
    if [ -n "${PREV_PID:-}" ] && kill -0 "$PREV_PID" 2>/dev/null; then
        echo "  [info] 已有另一个实例正在运行 (PID $PREV_PID)。"
        exit 1
    fi
    rm -rf "$RUN_LOCK" 2>/dev/null
fi
if ! mkdir "$RUN_LOCK" 2>/dev/null; then
    echo "  [info] 已有另一个实例正在运行 (并发启动)。"
    exit 1
fi
echo $$ > "$RUN_LOCK/pid"

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
    bind_failed=0
    for active_lock in "$LOCK_FILE" "$LOCK_FILE2"; do
        [ -f "$active_lock" ] || continue
        bash "$LIB_DIR/binding.sh" check "$SCRIPT_DIR" "$active_lock"
        [ $? -eq 1 ] && { bind_failed=1; break; }
    done
    if [ "$bind_failed" = "1" ]; then
        echo ""
        echo "  [ERROR] 此便携包已绑定到原始设备。"
        echo "  解绑：./CodexPortable.sh --unlock"
        echo ""
        exit 1
    fi
fi

# 迁移 + 链接（单路径，绝不 rm -rf 用户数据）
ensure_symlink() {
    local link="$1" target="$2"
    if [ -L "$link" ]; then
        [ "$(readlink "$link")" = "$target" ] && return 0
        rm "$link" 2>/dev/null
    elif [ -d "$link" ]; then
        if [ -n "$(ls -A "$link" 2>/dev/null)" ]; then
            if [ -z "$(ls -A "$target" 2>/dev/null)" ]; then
                echo "  [migrate] $link → $target"
                local cp_err
                cp_err=$(mktemp -t codex-cp.XXXXXX 2>/dev/null) || cp_err="/tmp/codex-cp.$$"
                if cp -a "$link/." "$target/" 2>"$cp_err"; then
                    rm -f "$cp_err"
                else
                    echo "  [ERROR] migration failed; system dir kept intact: $link"
                    [ -s "$cp_err" ] && sed 's/^/    /' "$cp_err" >&2
                    rm -f "$cp_err"
                    return 1
                fi
            else
                echo "  [warn] portable target not empty, backing up system dir: $link"
                local backup="${link}.before-portable.$(date +%Y%m%d-%H%M%S)"
                mv "$link" "$backup" 2>/dev/null && echo "  [info] system data backed up to: $backup"
                ln -s "$target" "$link" 2>/dev/null
                return 0
            fi
        fi
        rm -rf "$link" 2>/dev/null
    fi
    ln -s "$target" "$link" 2>/dev/null
}
ensure_symlink "$SYS_CCS" "$PORTABLE_CCS"
ensure_symlink "$SYS_CODEX" "$PORTABLE_CODEX"

CC_SWITCH_PID=""
WE_STARTED_CCS=0

cleanup() {
    if [ "$WE_STARTED_CCS" = "1" ] && [ -n "${CC_SWITCH_PID:-}" ] && kill -0 "$CC_SWITCH_PID" 2>/dev/null; then
        # 先收集子进程再 kill 父进程（父死后子进程 reparent，pgrep -P 找不到）
        local children
        children=$(pgrep -P "$CC_SWITCH_PID" 2>/dev/null || true)
        kill -TERM "$CC_SWITCH_PID" 2>/dev/null
        for _ in 1 2 3 4 5; do
            kill -0 "$CC_SWITCH_PID" 2>/dev/null || break
            sleep 1
        done
        kill -0 "$CC_SWITCH_PID" 2>/dev/null && kill -9 "$CC_SWITCH_PID" 2>/dev/null
        for child in $children; do
            kill -9 "$child" 2>/dev/null
        done
    fi
    [ -L "$SYS_CCS" ] && rm "$SYS_CCS" 2>/dev/null
    [ -L "$SYS_CODEX" ] && rm "$SYS_CODEX" 2>/dev/null
    [ -d "$RUN_LOCK" ] && rm -rf "$RUN_LOCK"
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
        # cc-switch 死亡检测
        if [ "$WE_STARTED_CCS" = "1" ] && [ -n "${CC_SWITCH_PID:-}" ] && ! kill -0 "$CC_SWITCH_PID" 2>/dev/null; then
            echo "  [!] CC Switch 已退出但仍未检测到配置。请重新运行。"
            exit 1
        fi
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
CODEX_EXIT=$?
# 提前清理（不依赖 trap）
[ -L "$SYS_CCS" ] && rm "$SYS_CCS" 2>/dev/null
[ -L "$SYS_CODEX" ] && rm "$SYS_CODEX" 2>/dev/null
[ -d "$RUN_LOCK" ] && rm -rf "$RUN_LOCK"
exit $CODEX_EXIT
