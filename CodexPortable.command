#!/bin/bash
# ═══════════════════════════════════════════
# Codex CLI Portable + CC Switch · macOS
# ═══════════════════════════════════════════

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ARCH="$(uname -m)"

# 处理 --unlock 参数
if [ "${1:-}" = "--unlock" ]; then
    LOCK_FILE="$SCRIPT_DIR/data/.lock"
    LOCK_FILE2="$SCRIPT_DIR/data/.cc-switch/.bind"
    REMOVED=0
    [ -f "$LOCK_FILE" ] && { rm -f "$LOCK_FILE"; REMOVED=1; }
    [ -f "$LOCK_FILE2" ] && { rm -f "$LOCK_FILE2"; REMOVED=1; }
    if [ "$REMOVED" = "1" ]; then
        echo "  [ok] 已移除绑定锁，下次运行将重新绑定到当前位置。"
    else
        echo "  [info] 没有绑定锁需要移除。"
    fi
    exit 0
fi

# Resolve python3: bundled > system
# Uses SCRIPT_DIR directly (BIN_DIR may not be set yet in --config path)
resolve_python3() {
    local _arch
    _arch="$(uname -m)"
    local _bin_dir="$SCRIPT_DIR/bin/macos-x64"
    [ "$_arch" = "arm64" ] && _bin_dir="$SCRIPT_DIR/bin/macos-arm64"
    # 1. Bundled python3 (inside portable package)
    if [ -x "$_bin_dir/python3" ]; then
        echo "$_bin_dir/python3"
        return 0
    fi
    # 2. System python3
    if command -v python3 >/dev/null 2>&1; then
        echo "python3"
        return 0
    fi
    return 1
}

# 处理 --config 参数（随时打开配置中心）
if [ "${1:-}" = "--config" ]; then
    CONFIG_SERVER="$SCRIPT_DIR/lib/config_server.py"
    if PY3=$(resolve_python3) && [ -f "$CONFIG_SERVER" ]; then
        echo "  打开配置中心 http://127.0.0.1:17590 ..."
        exec "$PY3" "$CONFIG_SERVER"
    else
        echo "  [!] 未找到 python3 或 config_server.py"
        exit 1
    fi
fi

# Banner
CYAN='\033[38;5;45m'
BLUE='\033[38;5;33m'
DIM='\033[38;5;240m'
NC='\033[0m'
echo ""
echo -e "${CYAN}   ██████╗ ██████╗ ██████╗ ███████╗██╗  ██╗${NC}"
echo -e "${CYAN}  ██╔════╝██╔═══██╗██╔══██╗██╔════╝╚██╗██╔╝${NC}"
echo -e "${BLUE}  ██║     ██║   ██║██║  ██║█████╗   ╚███╔╝${NC}"
echo -e "${BLUE}  ██║     ██║   ██║██║  ██║██╔══╝   ██╔██╗${NC}"
echo -e "${DIM}  ╚██████╗╚██████╔╝██████╔╝███████╗██╔╝ ██╗${NC}"
echo -e "${DIM}   ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝${NC}"
echo ""
echo "     Codex CLI Portable"
echo ""

# 架构检测
case "$ARCH" in
    arm64)  BIN_DIR="$SCRIPT_DIR/bin/macos-arm64" ;;
    x86_64) BIN_DIR="$SCRIPT_DIR/bin/macos-x64" ;;
    *)      echo "[ERROR] 不支持的架构: $ARCH"; exit 1 ;;
esac

if [ ! -f "$BIN_DIR/codex" ]; then
    echo "[ERROR] 未找到 Codex CLI: $BIN_DIR/codex"
    exit 1
fi

chmod +x "$BIN_DIR/codex" 2>/dev/null
[ -f "$BIN_DIR/cc-switch" ] && chmod +x "$BIN_DIR/cc-switch" 2>/dev/null

# Pre-flight self-check
LIB_DIR="$SCRIPT_DIR/lib"
if [ -f "$LIB_DIR/preflight.sh" ]; then
    source "$LIB_DIR/preflight.sh"
    preflight_check "$BIN_DIR" "$SCRIPT_DIR/data" "codex" || {
        echo "  请修复上述错误后重试。"
        exit 1
    }
fi

# macOS: 移除 quarantine 属性（Gatekeeper）
xattr -dr com.apple.quarantine "$BIN_DIR/codex" 2>/dev/null
[ -f "$BIN_DIR/cc-switch" ] && xattr -dr com.apple.quarantine "$BIN_DIR/cc-switch" 2>/dev/null

# ═══════════════════════════════════════════
# 单实例锁（原子 mkdir 持锁，避免 [-f] 检查 + 写 PID 的 TOCTOU 竞态）
# ═══════════════════════════════════════════
RUN_LOCK="$SCRIPT_DIR/data/.running"
mkdir -p "$SCRIPT_DIR/data"
if [ -d "$RUN_LOCK" ]; then
    PREV_PID=""
    [ -f "$RUN_LOCK/pid" ] && PREV_PID=$(cat "$RUN_LOCK/pid" 2>/dev/null | tr -d '[:space:]')
    if [ -n "${PREV_PID:-}" ] && kill -0 "$PREV_PID" 2>/dev/null; then
        echo "  [info] 已有另一个实例正在运行 (PID $PREV_PID)。"
        echo "  如果错误，请删除：$RUN_LOCK"
        exit 1
    fi
    rm -rf "$RUN_LOCK" 2>/dev/null
fi
if ! mkdir "$RUN_LOCK" 2>/dev/null; then
    echo "  [info] 已有另一个实例正在运行 (并发启动)。"
    echo "  如果错误，请删除：$RUN_LOCK"
    exit 1
fi
echo $$ > "$RUN_LOCK/pid"

# ═══════════════════════════════════════════
# 便携目录设置
# ═══════════════════════════════════════════
PORTABLE_DATA="$SCRIPT_DIR/data"
PORTABLE_CCS="$PORTABLE_DATA/.cc-switch"
PORTABLE_CODEX="$PORTABLE_DATA/.codex"
SYS_CCS="$HOME/.cc-switch"
SYS_CODEX="$HOME/.codex"
LIB_DIR="$SCRIPT_DIR/lib"
LOCK_FILE="$PORTABLE_DATA/.lock"
LOCK_FILE2="$PORTABLE_CCS/.bind"

mkdir -p "$PORTABLE_CCS" "$PORTABLE_CODEX"

# ═══════════════════════════════════════════
# 设备绑定校验（双 lock）
# ═══════════════════════════════════════════
LOCK_PRESENT=0
[ -f "$LOCK_FILE" ] && LOCK_PRESENT=1
[ -f "$LOCK_FILE2" ] && LOCK_PRESENT=1

if [ "$LOCK_PRESENT" = "1" ] && [ -f "$LIB_DIR/binding.sh" ]; then
    chmod +x "$LIB_DIR/binding.sh" 2>/dev/null
    # 校验所有存在的 lock。两个文件应同 hash；任一 mismatch 即拒绝。
    # 这样篡改其中一个也会被另一个抓到（真正的双 lock 防绕过）。
    bind_failed=0
    bind_warned=0
    for active_lock in "$LOCK_FILE" "$LOCK_FILE2"; do
        [ -f "$active_lock" ] || continue
        bash "$LIB_DIR/binding.sh" check "$SCRIPT_DIR" "$active_lock"
        r=$?
        case $r in
            1) bind_failed=1; break ;;
            3) bind_warned=1 ;;
        esac
    done
    if [ "$bind_failed" = "1" ]; then
        echo ""
        echo "  ============================================================"
        echo "  [ERROR] 此便携包已绑定到原始设备。"
        echo "  ============================================================"
        echo ""
        echo "  当前位置与绑定设备不匹配。这是防复制保护机制。"
        echo "  此便携包不能被复制到其他设备运行。"
        echo ""
        echo "  原始所有者解绑命令："
        echo "    ./CodexPortable.command --unlock"
        echo ""
        exit 1
    fi
    if [ "$bind_warned" = "1" ]; then
        echo "  [warn] 无法验证设备绑定（继续运行）。"
    fi
fi

# 创建符号链接：~/.cc-switch → 便携包/data/.cc-switch
# 单路径处理迁移 + 链接（之前 migrate_dir 与 ensure_symlink 重复迁移，
# 且 ensure_symlink 对真目录直接 rm -rf，cp 失败时会永久丢用户数据）。
ensure_symlink() {
    local link="$1" target="$2"
    if [ -L "$link" ]; then
        local current="$(readlink "$link")"
        [ "$current" = "$target" ] && return 0
        rm "$link" 2>/dev/null
    elif [ -d "$link" ]; then
        # 真目录 — 用户有预装的系统版本。绝不 rm -rf 用户数据。
        if [ -n "$(ls -A "$link" 2>/dev/null)" ]; then
            if [ -z "$(ls -A "$target" 2>/dev/null)" ]; then
                echo "  [migrate] $link → $target"
                # cp 失败时绝不删源数据（磁盘满/权限/锁 → 永久丢失）。
                local cp_err
                cp_err=$(mktemp -t codex-cp.XXXXXX 2>/dev/null) || cp_err="/tmp/codex-cp.$$"
                if cp -a "$link/." "$target/" 2>"$cp_err"; then
                    rm -f "$cp_err"
                else
                    echo "  [ERROR] 迁移失败，保留系统目录不删除：$link"
                    [ -s "$cp_err" ] && sed 's/^/    /' "$cp_err" >&2
                    rm -f "$cp_err"
                    return 1
                fi
            else
                # 便携包已有数据 → 备份系统目录而不是删除
                echo "  [warn] 便携包已有数据，备份系统目录: $link"
                local backup="${link}.before-portable.$(date +%Y%m%d-%H%M%S)"
                mv "$link" "$backup" 2>/dev/null && echo "  [info] 系统数据已备份到: $backup"
                ln -s "$target" "$link" 2>/dev/null
                return 0
            fi
        fi
        # 源目录空 或 cp 已成功 → 删除腾位置
        rm -rf "$link" 2>/dev/null
    fi
    ln -s "$target" "$link" 2>/dev/null
}
ensure_symlink "$SYS_CCS" "$PORTABLE_CCS"
ensure_symlink "$SYS_CODEX" "$PORTABLE_CODEX"

# 退出清理
cleanup() {
    # 配置中心已在前台运行并自行退出，无需 kill
    [ -L "$SYS_CCS" ] && rm "$SYS_CCS" 2>/dev/null
    [ -L "$SYS_CODEX" ] && rm "$SYS_CODEX" 2>/dev/null
    [ -d "$RUN_LOCK" ] && rm -rf "$RUN_LOCK"
}
trap cleanup EXIT INT TERM

# ═══════════════════════════════════════════
# 检查 Codex 配置（auth.json 有 OPENAI_API_KEY）
# ═══════════════════════════════════════════
has_valid_config() {
    local auth_file="$PORTABLE_CODEX/auth.json"
    [ -f "$auth_file" ] || return 1
    # 文件大小至少 20 字节（防止空文件 {} 通过）
    local size
    size=$(stat -f%z "$auth_file" 2>/dev/null || stat -c%s "$auth_file" 2>/dev/null || echo 0)
    [ "$size" -lt 20 ] && return 1
    # 用 python3 精确校验
    if PY3=$(resolve_python3); then
        AUTH_FILE="$auth_file" "$PY3" - <<'PYEOF' 2>/dev/null
import os, json, sys
try:
    with open(os.environ['AUTH_FILE'], 'r') as f:
        data = json.load(f)
    key = data.get('OPENAI_API_KEY', '')
    tokens = data.get('tokens', {})
    # 有 OPENAI_API_KEY (BYOK) 或 ChatGPT OAuth tokens 都算有效
    if (key and len(key) > 5) or (tokens and tokens.get('access_token')):
        sys.exit(0)
except Exception:
    pass
sys.exit(1)
PYEOF
        return $?
    fi
    # 无 python3 时退化到 grep 校验（codex auth.json 是 JSON）。
    # 之前直接 return 0 会让任何 >=20 字节的文件都通过（含无效配置）。
    if grep -qE '"OPENAI_API_KEY"[[:space:]]*:[[:space:]]*"[^"]{6,}"' "$auth_file" 2>/dev/null; then
        return 0
    fi
    if grep -qE '"access_token"[[:space:]]*:[[:space:]]*"[^"]+"' "$auth_file" 2>/dev/null; then
        return 0
    fi
    return 1
}

if ! has_valid_config; then
    echo "═══════════════════════════════════════════"
    echo "  首次运行 - 配置 API"
    echo "═══════════════════════════════════════════"
    echo ""
    CONFIG_SERVER="$LIB_DIR/config_server.py"
    if PY3=$(resolve_python3) && [ -f "$CONFIG_SERVER" ]; then
        echo "  正在打开配置中心 http://127.0.0.1:17590 ..."
        echo "  按引导选供应商、填 Key、测试、保存，然后点击「启动 Codex CLI」。"
        echo ""
        # 前台运行配置中心（阻塞），等待用户点击"启动"后退出
        "$PY3" "$CONFIG_SERVER"
        echo "  配置中心已关闭，继续启动 Codex CLI..."
        echo ""
    else
        echo "  [!] 未找到 python3，配置中心无法启动。"
        echo "  请安装 python3 后重试。"
        echo ""
    fi
else
    # 已有配置，启动配置中心（前台阻塞），方便随时修改 Key
    CONFIG_SERVER="$LIB_DIR/config_server.py"
    if PY3=$(resolve_python3) && [ -f "$CONFIG_SERVER" ]; then
        echo "  配置中心: http://127.0.0.1:17590"
        echo "  修改 Key 后点击「启动 Codex CLI」即可。"
        "$PY3" "$CONFIG_SERVER"
        echo "  配置中心已关闭，继续启动 Codex CLI..."
    fi
fi

# ═══════════════════════════════════════════
# 创建/修复绑定锁
# ═══════════════════════════════════════════
if [ -f "$LIB_DIR/binding.sh" ]; then
    if [ ! -f "$LOCK_FILE" ]; then
        bash "$LIB_DIR/binding.sh" create "$SCRIPT_DIR" "$LOCK_FILE" 2>/dev/null
        [ -f "$LOCK_FILE" ] && echo "  [ok] 已绑定到当前设备。解绑：./CodexPortable.command --unlock"
    fi
    [ ! -f "$LOCK_FILE2" ] && bash "$LIB_DIR/binding.sh" create "$SCRIPT_DIR" "$LOCK_FILE2" 2>/dev/null
fi

# ═══════════════════════════════════════════
# 启动 Codex CLI
# ═══════════════════════════════════════════
echo "  架构: $ARCH | 数据: 便携包内"
echo ""

# 设置 CODEX_HOME 环境变量（让 codex 显式使用便携目录，更可靠）
export CODEX_HOME="$PORTABLE_CODEX"

# 从 auth.json 读取 API Key 并 export 为环境变量
# Codex CLI 通过 env_key 指定的环境变量名读取 Key
AUTH_FILE="$PORTABLE_CODEX/auth.json"
if [ -f "$AUTH_FILE" ] && command -v python3 &>/dev/null; then
    while IFS='=' read -r key val; do
        [ -n "$key" ] && export "$key"="$val"
    done < <(python3 -c "
import json, sys
try:
    with open('$AUTH_FILE') as f:
        d = json.load(f)
    for k, v in d.items():
        if isinstance(v, str) and v:
            print(f'{k}={v}')
except: pass
" 2>/dev/null)
fi

"$BIN_DIR/codex" "$@"
CODEX_EXIT=$?

# 提前清理 symlink + run lock（不依赖 trap 在 read 之后才跑）。
# 即便用户在 read 等待时拔 U 盘，主目录也已干净。
[ -L "$SYS_CCS" ] && rm "$SYS_CCS" 2>/dev/null
[ -L "$SYS_CODEX" ] && rm "$SYS_CODEX" 2>/dev/null
[ -d "$RUN_LOCK" ] && rm -rf "$RUN_LOCK"

if [ $CODEX_EXIT -ne 0 ]; then
    echo ""
    echo "  Codex 退出码: $CODEX_EXIT"
    read -p "  按回车关闭窗口... " _
fi
exit $CODEX_EXIT
