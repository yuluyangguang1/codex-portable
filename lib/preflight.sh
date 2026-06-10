#!/bin/bash
# ═══════════════════════════════════════════
# Pre-flight self-check for Codex/Claude Portable
# Source this from launchers: source "$LIB_DIR/preflight.sh"
# ═══════════════════════════════════════════

preflight_check() {
    local bin_dir="${1:-$BIN_DIR}"
    local data_dir="${2:-$SCRIPT_DIR/data}"
    local app_name="${3:-codex}"
    local errors=0
    local warnings=0

    # 1. Binary present and executable
    local bin_file="$bin_dir/$app_name"
    [ "$app_name" = "claude" ] && bin_file="$bin_dir/claude"
    [ "$(uname -s)" = "MINGW"* ] && bin_file="${bin_file}.exe"

    if [ ! -f "$bin_file" ]; then
        echo "  [ERROR] Binary not found: $bin_file"
        errors=$((errors + 1))
    elif [ ! -x "$bin_file" ] && [ "$(uname -s)" != "MINGW"* ]; then
        echo "  [WARN]  Binary not executable: $bin_file"
        chmod +x "$bin_file" 2>/dev/null
        warnings=$((warnings + 1))
    fi

    # 2. cc-switch present
    local ccswitch="$bin_dir/cc-switch"
    [ "$(uname -s)" = "MINGW"* ] && ccswitch="${ccswitch}.exe"
    if [ ! -f "$ccswitch" ]; then
        echo "  [WARN]  cc-switch not found: $ccswitch"
        warnings=$((warnings + 1))
    fi

    # 3. Data directory writable
    if [ ! -d "$data_dir" ]; then
        mkdir -p "$data_dir" 2>/dev/null
    fi
    if [ ! -w "$data_dir" ]; then
        echo "  [ERROR] Data directory not writable: $data_dir"
        errors=$((errors + 1))
    fi

    # 4. Disk free space (>500MB)
    local free_mb
    if command -v df &>/dev/null; then
        free_mb=$(df -m "$data_dir" 2>/dev/null | awk 'NR==2{print $4}')
        if [ -n "$free_mb" ] && [ "$free_mb" -lt 500 ] 2>/dev/null; then
            echo "  [WARN]  Low disk space: ${free_mb}MB free (< 500MB)"
            warnings=$((warnings + 1))
        fi
    fi

    # 5. Python available (for config center)
    local has_python=0
    if [ -x "$bin_dir/python3" ] || [ -x "$bin_dir/python/python.exe" ]; then
        has_python=1
    elif command -v python3 &>/dev/null || command -v python &>/dev/null; then
        has_python=1
    fi
    if [ "$has_python" = "0" ]; then
        echo "  [WARN]  No Python found — config center will not start"
        warnings=$((warnings + 1))
    fi

    # 6. Port range available (17590-17599)
    local port_busy=0
    for p in $(seq 17590 17599); do
        if command -v ss &>/dev/null; then
            ss -tlnp 2>/dev/null | grep -q ":$p " && port_busy=$((port_busy + 1))
        elif command -v lsof &>/dev/null; then
            lsof -i :$p &>/dev/null && port_busy=$((port_busy + 1))
        elif command -v netstat &>/dev/null; then
            netstat -an 2>/dev/null | grep -q ":$p.*LISTEN" && port_busy=$((port_busy + 1))
        fi
    done
    if [ "$port_busy" -ge 10 ]; then
        echo "  [WARN]  Ports 17590-17599 all occupied"
        warnings=$((warnings + 1))
    fi

    # Summary
    if [ "$errors" -gt 0 ]; then
        echo "  [FAIL] $errors error(s), $warnings warning(s)"
        return 1
    fi
    if [ "$warnings" -gt 0 ]; then
        echo "  [ok] Pre-flight passed with $warnings warning(s)"
    fi
    return 0
}
