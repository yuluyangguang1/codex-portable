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
    # Check if we had any port-checking tool
    if ! command -v ss &>/dev/null && ! command -v lsof &>/dev/null && ! command -v netstat &>/dev/null; then
        echo "  [WARN]  No port-checking tool found (ss/lsof/netstat)"
        warnings=$((warnings + 1))
    elif [ "$port_busy" -ge 10 ]; then
        echo "  [WARN]  Ports 17590-17599 all occupied"
        warnings=$((warnings + 1))
    fi

    # 6. Binary actually runs (--version smoke test)
    if [ -f "$bin_file" ] && [ -x "$bin_file" ]; then
        local BIN_VER=""
        if command -v timeout &>/dev/null; then
            BIN_VER=$(timeout 5 "$bin_file" --version 2>&1 || true)
        elif command -v perl &>/dev/null; then
            # macOS has perl but not timeout — use alarm
            BIN_VER=$(perl -e 'alarm 5; exec @ARGV' -- "$bin_file" --version 2>&1 || true)
        else
            # Last resort: background + manual kill after 5s
            "$bin_file" --version &>/tmp/codex-pf-$$ &
            local _pf_pid=$!
            (sleep 5 && kill "$_pf_pid" 2>/dev/null) &
            local _watchdog=$!
            wait "$_pf_pid" 2>/dev/null
            BIN_VER=$(cat /tmp/codex-pf-$$ 2>/dev/null)
            kill "$_watchdog" 2>/dev/null
            rm -f /tmp/codex-pf-$$
        fi
        if [ -z "$BIN_VER" ]; then
            echo "  [WARN]  Binary found but won't run: $bin_file"
            echo "          USB files may be corrupted"
            warnings=$((warnings + 1))
        fi
    fi

    # 7. Config file integrity
    local AUTH_FILE="$data_dir/.codex/auth.json"
    if [ -f "$AUTH_FILE" ]; then
        if command -v python3 &>/dev/null; then
            if ! python3 -c "import json, sys; json.load(open(sys.argv[1]))" "$AUTH_FILE" 2>/dev/null; then
                echo "  [WARN]  auth.json parse failed: $AUTH_FILE"
                echo "          Config center will auto-recover from backups"
                warnings=$((warnings + 1))
            fi
        fi
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
