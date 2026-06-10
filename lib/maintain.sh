#!/bin/bash
# ═══════════════════════════════════════════
# Maintenance menu for Codex/Claude Portable
# Source this from launchers: source "$LIB_DIR/maintain.sh"
# ═══════════════════════════════════════════

show_menu() {
    local app_name="${1:-codex}"
    echo ""
    echo "  ╔══════════════════════════════════════╗"
    echo "  ║        ${app_name^} Portable Menu          ║"
    echo "  ╠══════════════════════════════════════╣"
    echo "  ║  [1] 打开配置中心                    ║"
    echo "  ║  [2] 查看当前配置                    ║"
    echo "  ║  [3] 导出/导入配置                   ║"
    echo "  ║  [4] 诊断检查                        ║"
    echo "  ║  [5] 查看日志                        ║"
    echo "  ║  [6] 解除绑定                        ║"
    echo "  ║  [7] 系统信息                        ║"
    echo "  ║  [8] 清理残留进程                    ║"
    echo "  ║  [9] 重置数据                        ║"
    echo "  ║  [0] 退出                            ║"
    echo "  ╚══════════════════════════════════════╝"
    echo ""
}

do_config_center() {
    local lib_dir="$1"
    local bin_dir="$2"
    local config_server="$lib_dir/config_server.py"
    local py=""

    if [ -x "$bin_dir/python3" ]; then
        py="$bin_dir/python3"
    elif command -v python3 &>/dev/null; then
        py="python3"
    elif command -v python &>/dev/null; then
        py="python"
    fi

    if [ -n "$py" ] && [ -f "$config_server" ]; then
        echo "  正在打开配置中心..."
        "$py" "$config_server"
    else
        echo "  [!] 未找到 python3 或 config_server.py"
    fi
}

do_show_config() {
    local data_dir="$1"
    local db="$data_dir/.cc-switch/cc-switch.db"
    if [ ! -f "$db" ]; then
        echo "  [!] 未找到配置文件"
        return
    fi
    if command -v python3 &>/dev/null; then
        python3 -c "
import sqlite3, json
db = sqlite3.connect('$db')
row = db.execute('SELECT settings_config FROM providers WHERE is_current=1 LIMIT 1').fetchone()
db.close()
if row:
    cfg = json.loads(row[0])
    env = cfg.get('env', {})
    url = env.get('ANTHROPIC_BASE_URL', '') or env.get('OPENAI_BASE_URL', '')
    key = (env.get('ANTHROPIC_AUTH_TOKEN', '') or env.get('ANTHROPIC_API_KEY', '')
           or env.get('OPENAI_API_KEY', ''))
    model = env.get('ANTHROPIC_MODEL', '') or env.get('OPENAI_MODEL', '')
    print(f'  Base URL: {url}')
    print(f'  API Key:  {key[:8]}...{key[-4:]}' if len(key) > 12 else f'  API Key:  [set]')
    print(f'  Model:    {model}')
else:
    print('  [!] 未找到当前 Provider')
"
    else
        echo "  [!] 需要 python3 来读取配置"
    fi
}

do_export_config() {
    local data_dir="$1"
    local db="$data_dir/.cc-switch/cc-switch.db"
    local ts=$(date +%Y%m%d_%H%M%S)
    local backup="$data_dir/config-backup-${ts}.db"
    if [ -f "$db" ]; then
        cp "$db" "$backup"
        echo "  [ok] 配置已导出: $backup"
    else
        echo "  [!] 未找到配置文件"
    fi
}

do_diagnose() {
    local bin_dir="$1"
    local data_dir="$2"
    local lib_dir="$3"
    local app_name="${4:-codex}"

    echo "  诊断检查..."
    echo ""

    # Binary
    local bin_file="$bin_dir/$app_name"
    [ "$(uname -s)" = "MINGW"* ] && bin_file="${bin_file}.exe"
    if [ -f "$bin_file" ]; then
        echo "  [ok] $app_name 二进制文件存在"
    else
        echo "  [FAIL] $app_name 二进制文件缺失"
    fi

    # cc-switch
    local ccswitch="$bin_dir/cc-switch"
    [ "$(uname -s)" = "MINGW"* ] && ccswitch="${ccswitch}.exe"
    if [ -f "$ccswitch" ]; then
        echo "  [ok] cc-switch 存在"
    else
        echo "  [WARN] cc-switch 缺失"
    fi

    # Config
    local db="$data_dir/.cc-switch/cc-switch.db"
    if [ -f "$db" ]; then
        local sz=$(wc -c < "$db" 2>/dev/null | tr -d ' ')
        echo "  [ok] 配置文件存在 (${sz} bytes)"
    else
        echo "  [WARN] 配置文件不存在"
    fi

    # Data dir writable
    if [ -w "$data_dir" ]; then
        echo "  [ok] 数据目录可写"
    else
        echo "  [FAIL] 数据目录不可写"
    fi

    # Disk space
    local free_mb=$(df -m "$data_dir" 2>/dev/null | awk 'NR==2{print $4}')
    if [ -n "$free_mb" ]; then
        if [ "$free_mb" -lt 500 ] 2>/dev/null; then
            echo "  [WARN] 磁盘空间不足: ${free_mb}MB"
        else
            echo "  [ok] 磁盘空间充足: ${free_mb}MB"
        fi
    fi

    # Python
    if [ -x "$bin_dir/python3" ] || command -v python3 &>/dev/null; then
        echo "  [ok] Python 可用"
    else
        echo "  [WARN] Python 不可用"
    fi

    echo ""
}

do_system_info() {
    local bin_dir="$1"
    local data_dir="$2"
    local app_name="${3:-codex}"

    echo "  系统信息"
    echo "  ──────────────────────────"
    echo "  OS:       $(uname -s) $(uname -m)"
    echo "  Shell:    $SHELL"

    local bin_file="$bin_dir/$app_name"
    [ "$(uname -s)" = "MINGW"* ] && bin_file="${bin_file}.exe"
    if [ -f "$bin_file" ]; then
        local sz=$(wc -c < "$bin_file" 2>/dev/null | tr -d ' ')
        echo "  Binary:   ${sz} bytes"
    fi

    if command -v python3 &>/dev/null; then
        echo "  Python:   $(python3 --version 2>&1)"
    fi

    local db="$data_dir/.cc-switch/cc-switch.db"
    if [ -f "$db" ]; then
        echo "  Config:   $db"
    fi

    echo "  Data:     $data_dir"
    echo "  ──────────────────────────"
    echo ""
}

do_kill_residual() {
    local app_name="${1:-codex}"
    echo "  清理残留进程..."
    if command -v pkill &>/dev/null; then
        pkill -f "$app_name" 2>/dev/null
        pkill -f "cc-switch" 2>/dev/null
        pkill -f "config_server.py" 2>/dev/null
    fi
    echo "  [ok] 已清理"
}

do_factory_reset() {
    local data_dir="$1"
    local ts=$(date +%Y%m%d_%H%M%S)
    local backup="$data_dir/../data-backup-${ts}.tar.gz"

    echo "  ⚠️  重置将删除所有配置和数据！"
    echo "  正在备份到: $backup"
    tar czf "$backup" -C "$data_dir/.." data 2>/dev/null

    echo "  备份完成。是否继续重置？(y/N)"
    read -r confirm
    if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
        rm -rf "$data_dir/.cc-switch" "$data_dir/.codex" "$data_dir/.claude" 2>/dev/null
        echo "  [ok] 数据已重置。备份在: $backup"
    else
        echo "  已取消。备份保留: $backup"
    fi
}

run_menu() {
    local lib_dir="$1"
    local bin_dir="$2"
    local data_dir="$3"
    local app_name="${4:-codex}"

    while true; do
        show_menu "$app_name"
        echo -n "  选择: "
        read -r choice
        case "$choice" in
            1) do_config_center "$lib_dir" "$bin_dir" ;;
            2) do_show_config "$data_dir" ;;
            3) do_export_config "$data_dir" ;;
            4) do_diagnose "$bin_dir" "$data_dir" "$lib_dir" "$app_name" ;;
            5) echo "  日志功能开发中..." ;;
            6) echo "  解除绑定: 删除 $data_dir/.lock 和 .bind 文件" ;;
            7) do_system_info "$bin_dir" "$data_dir" "$app_name" ;;
            8) do_kill_residual "$app_name" ;;
            9) do_factory_reset "$data_dir" ;;
            0) break ;;
            *) echo "  无效选择" ;;
        esac
    done
}
