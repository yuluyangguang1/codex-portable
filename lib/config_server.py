#!/usr/bin/env python3
"""
Codex CLI Portable — 配置中心 (Config Center)

A self-contained, dependency-free (stdlib-only) local web config panel,
styled consistently with the OpenClaw / Hermes / Claude portable config centers.

It reads and writes the cc-switch SQLite database at data/.cc-switch/cc-switch.db
AND the codex-native auth.json + config.toml at data/.codex/. Both stores stay
in sync so the launcher, cc-switch GUI, and this panel are interoperable.

Usage:
  python3 lib/config_server.py            # serve on 127.0.0.1:17590
"""
import json
import secrets
import os
import sqlite3
import sys
import threading
import time
import uuid
import urllib.request
import urllib.error
import webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
PORTABLE_ROOT = SCRIPT_DIR.parent if SCRIPT_DIR.name == "lib" else SCRIPT_DIR
DATA_DIR = PORTABLE_ROOT / "data"
CCS_DIR = DATA_DIR / ".cc-switch"
CCS_DB = CCS_DIR / "cc-switch.db"

PORT = 17590          # config-center port (distinct from cc-switch GUI)
APP_TYPE = "codex"    # which cc-switch app_type this panel manages

# Per-process CSRF token (same design as claude-portable + openclaw).
SERVER_TOKEN = secrets.token_hex(32)

# ── Provider catalog ────────────────────────────────────────────────
# Codex CLI talks the OpenAI wire protocol (responses API or chat
# completions). Third-party providers must expose an OpenAI-compatible
# endpoint. The key is stored in auth.json as OPENAI_API_KEY, and the
# base_url + model go into config.toml.
# Models updated 2026-05-31.
PROVIDERS = [
    {"id": "openai", "name": "OpenAI 官方", "base_url": "https://api.openai.com/v1",
     "models": ["gpt-5.5", "gpt-5.5-codex", "gpt-5.1", "gpt-5.1-mini", "o4", "o4-mini"],
     "key_hint": "sk-...", "note": "官方直连，GPT-5.5 / Codex 最新"},
    {"id": "openrouter", "name": "OpenRouter", "base_url": "https://openrouter.ai/api/v1",
     "models": ["openai/gpt-5.5", "anthropic/claude-opus-4.8",
                "google/gemini-3.1-pro-preview", "deepseek/deepseek-v4-pro",
                "x-ai/grok-4.3", "qwen/qwen3.6-max"],
     "key_hint": "sk-or-...", "note": "聚合平台，一个 Key 用所有模型"},
    {"id": "deepseek", "name": "DeepSeek", "base_url": "https://api.deepseek.com/v1",
     "models": ["deepseek-v4-pro", "deepseek-v4-flash", "deepseek-chat", "deepseek-reasoner"],
     "key_hint": "sk-...", "note": "国产，性价比极高，V4 系列最新"},
    {"id": "minimax", "name": "MiniMax (海螺)", "base_url": "https://api.minimaxi.com/v1",
     "models": ["MiniMax-M2.7", "MiniMax-M2.7-highspeed", "MiniMax-M2.5"],
     "key_hint": "粘贴 MiniMax API Key", "note": "国产，OpenAI 兼容，速度快"},
    {"id": "zhipu", "name": "智谱 GLM", "base_url": "https://open.bigmodel.cn/api/paas/v4",
     "models": ["glm-5.1", "glm-5", "glm-4.6", "glm-4.5-air", "glm-4.5-flash"],
     "key_hint": "粘贴智谱 API Key", "note": "国产，GLM-5 系列最新"},
    {"id": "kimi", "name": "Kimi / Moonshot", "base_url": "https://api.moonshot.cn/v1",
     "models": ["kimi-k2.6", "kimi-k2.5", "kimi-k2-thinking-turbo", "moonshot-v1-128k"],
     "key_hint": "sk-...", "note": "国产，K2.6 最新，长上下文"},
    {"id": "doubao", "name": "豆包 / 火山引擎", "base_url": "https://ark.cn-beijing.volces.com/api/v3",
     "models": ["doubao-seed-1.6", "doubao-seed-1.6-thinking", "doubao-1.5-pro-256k"],
     "key_hint": "粘贴火山引擎 API Key", "note": "字节跳动，Seed 1.6 最新"},
    {"id": "dashscope", "name": "通义千问 / 阿里", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
     "models": ["qwen3.6-max", "qwen3.6-plus", "qwen3-coder-plus", "qwen-max-latest"],
     "key_hint": "sk-...", "note": "阿里云，Qwen 3.6 最新"},
    {"id": "siliconflow", "name": "SiliconFlow (硅基流动)", "base_url": "https://api.siliconflow.cn/v1",
     "models": ["deepseek-ai/DeepSeek-V4-Pro", "Qwen/Qwen3.6-Max", "moonshotai/Kimi-K2.6"],
     "key_hint": "sk-...", "note": "国产聚合，多模型一站式"},
    {"id": "groq", "name": "Groq", "base_url": "https://api.groq.com/openai/v1",
     "models": ["llama-4-scout-17b-16e-instruct", "llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
     "key_hint": "gsk_...", "note": "超快推理，免费额度"},
    {"id": "custom", "name": "自定义 / 中转站", "base_url": "",
     "models": [], "custom": True,
     "key_hint": "粘贴中转站 API Key", "note": "填写中转站/自建网关的 base_url"},
]


# ═══════════════════════════════════════════════════════════════
#  cc-switch DB read / write
# ═══════════════════════════════════════════════════════════════
def _connect():
    CCS_DIR.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(CCS_DB), timeout=5.0)


def _ensure_schema(db):
    """Create the providers table if the DB is brand new, matching the
    cc-switch column layout so the GUI stays interoperable."""
    db.execute("""
        CREATE TABLE IF NOT EXISTS providers (
            id TEXT NOT NULL,
            app_type TEXT NOT NULL,
            name TEXT NOT NULL,
            settings_config TEXT NOT NULL,
            website_url TEXT,
            category TEXT,
            created_at INTEGER,
            sort_index INTEGER,
            notes TEXT,
            icon TEXT,
            icon_color TEXT,
            meta TEXT NOT NULL DEFAULT '{}',
            is_current BOOLEAN NOT NULL DEFAULT 0,
            in_failover_queue BOOLEAN NOT NULL DEFAULT 0,
            PRIMARY KEY (id, app_type)
        )
    """)
    db.commit()


def read_current():
    """Return the currently-active claude provider as a dict, or None."""
    if not CCS_DB.exists():
        return None
    try:
        db = _connect()
        row = db.execute(
            "SELECT id, name, settings_config FROM providers "
            "WHERE app_type=? AND is_current=1 LIMIT 1", (APP_TYPE,)
        ).fetchone()
        db.close()
        if not row:
            return None
        cfg = json.loads(row[2])
        env = cfg.get("env", {})
        return {
            "id": row[0], "name": row[1],
            "base_url": (env.get("OPENAI_BASE_URL") or "").strip(),
            "api_key": (env.get("OPENAI_API_KEY") or "").strip(),
            "model": (env.get("CODEX_MODEL") or "").strip(),
        }
    except Exception:
        return None


def list_providers():
    out = []
    if not CCS_DB.exists():
        return out
    try:
        db = _connect()
        try:
            rows = db.execute(
                "SELECT id, name, is_current FROM providers WHERE app_type=? "
                "ORDER BY is_current DESC, name", (APP_TYPE,)
            ).fetchall()
            for r in rows:
                out.append({"id": r[0], "name": r[1], "active": bool(r[2])})
        finally:
            db.close()
    except Exception:
        pass
    return out


def save_provider(name, base_url, api_key, model):
    """Insert/replace a provider row and mark it current. Writes the
    cc-switch settings_config shape for codex (OPENAI_API_KEY +
    OPENAI_BASE_URL), so the launcher and cc-switch GUI both read it."""
    base_url = (base_url or "").strip().rstrip("/")
    api_key = (api_key or "").strip()
    model = (model or "").strip()
    if not base_url or not api_key:
        raise ValueError("base_url 和 api_key 不能为空")

    env = {
        "OPENAI_BASE_URL": base_url,
        "OPENAI_API_KEY": api_key,
    }
    if model:
        env["CODEX_MODEL"] = model
    settings = {"env": env}
    meta = {"apiFormat": "openai"}

    db = _connect()
    try:
        _ensure_schema(db)
        pid = str(uuid.uuid4())
        db.execute("UPDATE providers SET is_current=0 WHERE app_type=?", (APP_TYPE,))
        db.execute(
            "INSERT INTO providers (id, app_type, name, settings_config, "
            "created_at, sort_index, meta, is_current) "
            "VALUES (?,?,?,?,?,?,?,1)",
            (pid, APP_TYPE, name or "Custom",
             json.dumps(settings, ensure_ascii=False),
             int(time.time() * 1000), 0, json.dumps(meta)),
        )
        db.commit()
    finally:
        db.close()

    # Also write auth.json + config.toml for codex CLI direct consumption.
    # Codex reads CODEX_HOME/auth.json for the key and config.toml for
    # model/provider settings. The launcher sets CODEX_HOME=data/.codex.
    codex_dir = DATA_DIR / ".codex"
    codex_dir.mkdir(parents=True, exist_ok=True)
    auth = {"OPENAI_API_KEY": api_key}
    _atomic_write(codex_dir / "auth.json",
                  json.dumps(auth, ensure_ascii=False, indent=2))
    if model or base_url != "https://api.openai.com/v1":
        toml_lines = []
        if base_url != "https://api.openai.com/v1":
            # wire_api selection: OpenAI's own endpoint speaks the
            # Responses API, but most third-party OpenAI-compatible
            # providers (DeepSeek, Groq, Moonshot, Zhipu, MiniMax, ...)
            # only implement /chat/completions. Defaulting every custom
            # provider to "responses" breaks them with a 404. Pick "chat"
            # for non-OpenAI hosts, "responses" only for *.openai.com.
            wire_api = "responses" if "openai.com" in base_url else "chat"
            toml_lines.append('model_provider = "custom"')
            toml_lines.append(f'model = "{_toml_escape(model or "gpt-5.5")}"')
            toml_lines.append("")
            toml_lines.append("[model_providers.custom]")
            toml_lines.append(f'name = "{_toml_escape(name or "Custom")}"')
            toml_lines.append(f'base_url = "{_toml_escape(base_url)}"')
            toml_lines.append(f'wire_api = "{wire_api}"')
            toml_lines.append('env_key = "OPENAI_API_KEY"')
        else:
            toml_lines.append(f'model = "{_toml_escape(model)}"')
        _atomic_write(codex_dir / "config.toml", "\n".join(toml_lines) + "\n")

    return pid


def _toml_escape(s):
    """Escape a string for a TOML double-quoted value. Without this, a
    backslash or quote in a model/provider name or base_url would produce
    invalid TOML and codex would fail to start."""
    return (str(s).replace("\\", "\\\\").replace('"', '\\"')
            .replace("\n", "").replace("\r", ""))


def _atomic_write(path, content):
    """Write file atomically via tmp+rename."""
    from pathlib import Path
    p = Path(path)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    try:
        os.replace(str(tmp), str(p))
    except Exception:
        try:
            tmp.unlink()
        except Exception:
            pass
        raise


def activate_provider(pid):
    db = _connect()
    try:
        db.execute("UPDATE providers SET is_current=0 WHERE app_type=?", (APP_TYPE,))
        db.execute("UPDATE providers SET is_current=1 WHERE id=? AND app_type=?",
                   (pid, APP_TYPE))
        db.commit()
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════
#  Maintenance features (batch 1): export / import / view / logs /
#  diagnose / unbind
# ═══════════════════════════════════════════════════════════════
def export_config():
    out = {"version": 1, "app_type": APP_TYPE, "exported_at": int(time.time()),
           "providers": []}
    if not CCS_DB.exists():
        return out
    try:
        db = _connect()
        rows = db.execute(
            "SELECT id, name, settings_config, meta, is_current "
            "FROM providers WHERE app_type=?", (APP_TYPE,)
        ).fetchall()
        db.close()
        for r in rows:
            out["providers"].append({
                "id": r[0], "name": r[1],
                "settings_config": json.loads(r[2] or "{}"),
                "meta": json.loads(r[3] or "{}"),
                "is_current": bool(r[4]),
            })
    except Exception:
        pass
    return out


def import_config(blob):
    if not isinstance(blob, dict) or not isinstance(blob.get("providers"), list):
        raise ValueError("无效的配置文件格式")
    db = _connect()
    try:
        _ensure_schema(db)
        count = 0
        current_id = None
        for p in blob["providers"]:
            pid = p.get("id") or str(uuid.uuid4())
            name = p.get("name") or "Imported"
            settings = p.get("settings_config") or {}
            meta = p.get("meta") or {}
            if not settings.get("env"):
                continue
            db.execute(
                "INSERT OR REPLACE INTO providers (id, app_type, name, "
                "settings_config, created_at, sort_index, meta, is_current) "
                "VALUES (?,?,?,?,?,?,?,0)",
                (pid, APP_TYPE, name, json.dumps(settings, ensure_ascii=False),
                 int(time.time() * 1000), 0, json.dumps(meta)),
            )
            count += 1
            if p.get("is_current"):
                current_id = pid
        if current_id:
            db.execute("UPDATE providers SET is_current=0 WHERE app_type=?", (APP_TYPE,))
            db.execute("UPDATE providers SET is_current=1 WHERE id=? AND app_type=?",
                       (current_id, APP_TYPE))
        db.commit()
    finally:
        db.close()
    return count


def view_config():
    cur = read_current()
    if not cur:
        return {"configured": False}
    key = cur.get("api_key", "")
    masked = (key[:6] + "…" + key[-4:]) if len(key) > 12 else "***"
    return {
        "configured": True, "name": cur.get("name"),
        "base_url": cur.get("base_url"), "model": cur.get("model"),
        "api_key_masked": masked, "api_key_len": len(key),
    }


def read_logs(max_lines=200):
    codex_dir = DATA_DIR / ".codex"
    if not codex_dir.exists():
        return {"available": False, "text": "暂无日志（data/.codex/ 不存在）"}
    # If data/.codex is a symlink (active session), refuse to traverse the
    # target — it's the system ~/.codex, which holds auth.json with the
    # API key. Surfacing its contents in the panel would be a secret leak.
    if codex_dir.is_symlink():
        return {"available": False,
                "text": "data/.codex 是符号链接（活跃会话中），日志在终端查看更安全"}
    candidates = []
    try:
        for p in codex_dir.rglob("*"):
            # Skip symlinks inside the dir too (defense in depth).
            if p.is_symlink():
                continue
            # Never surface auth.json / config.toml — they hold secrets.
            if p.name in ("auth.json", "config.toml"):
                continue
            if p.is_file() and p.suffix in (".log", ".jsonl", ".txt"):
                try:
                    candidates.append((p.stat().st_mtime, p))
                except OSError:
                    continue
    except Exception:
        pass
    if not candidates:
        return {"available": False, "text": "暂无日志文件"}
    candidates.sort(reverse=True)
    newest = candidates[0][1]
    try:
        size = newest.stat().st_size
        with open(newest, "rb") as f:
            if size > 262144:
                f.seek(-262144, os.SEEK_END)
            data = f.read().decode("utf-8", "replace")
        lines = data.splitlines()[-max_lines:]
        return {"available": True, "file": newest.name, "text": "\n".join(lines)}
    except Exception as e:
        return {"available": False, "text": f"读取日志失败: {e}"}


def run_diagnose():
    checks = []

    def add(label, ok, detail=""):
        checks.append({"label": label, "ok": bool(ok), "detail": detail})

    cur = read_current()
    add("配置已就绪", cur is not None,
        (cur.get("name") if cur else "未配置任何供应商"))
    if cur:
        add("Base URL 有效", len(cur.get("base_url", "")) > 8, cur.get("base_url", ""))
        add("API Key 已填", len(cur.get("api_key", "")) > 5,
            f"{len(cur.get('api_key', ''))} 字符")
    plat = _platform_dir()
    codex_bin = PORTABLE_ROOT / "bin" / plat / ("codex.exe" if os.name == "nt" else "codex")
    add("Codex 二进制存在", codex_bin.exists(), str(codex_bin))
    try:
        test = DATA_DIR / ".write_test"
        test.write_text("x")
        test.unlink()
        add("数据目录可写", True, str(DATA_DIR))
    except Exception as e:
        add("数据目录可写", False, str(e))
    add("Python3 运行时", True, sys.version.split()[0])
    # Network check
    net_ok = False
    net_detail = "无法连接"
    try:
        import ssl
        ctx = None
        try:
            import certifi
            ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            pass
        u = (cur.get("base_url") if cur and cur.get("base_url") else "https://api.openai.com/v1")
        req = urllib.request.Request(u + "/models", method="HEAD",
                                     headers={"Authorization": "Bearer test"})
        kwargs = {"timeout": 5}
        if ctx:
            kwargs["context"] = ctx
        try:
            urllib.request.urlopen(req, **kwargs)
            net_ok = True
            net_detail = u
        except urllib.error.HTTPError:
            net_ok = True
            net_detail = u
        except Exception:
            pass
    except Exception:
        pass
    add("网络连通", net_ok, net_detail)
    return checks


def _platform_dir():
    if os.name == "nt":
        return "windows-x64"
    import platform as _p
    if _p.system() == "Darwin":
        return "macos-arm64" if _p.machine() == "arm64" else "macos-x64"
    return "linux-x64"


def unbind_device():
    removed = 0
    for lf in (DATA_DIR / ".lock", CCS_DIR / ".bind"):
        try:
            if lf.exists():
                lf.unlink()
                removed += 1
        except Exception:
            pass
    return removed


def launch_ccswitch():
    """Launch the bundled cc-switch GUI as a detached background process.

    The config center is the primary onboarding path, but cc-switch is a
    full native GUI with extra features. Users who prefer it can start it
    from here. Returns (ok, message). Never blocks; uses list-form args
    (no shell=True)."""
    plat = _platform_dir()
    exe = "cc-switch.exe" if os.name == "nt" else "cc-switch"
    ccbin = PORTABLE_ROOT / "bin" / plat / exe
    if not ccbin.exists():
        return False, f"未找到 CC Switch 可执行文件：bin/{plat}/{exe}"
    try:
        import subprocess
        kwargs = {
            "cwd": str(ccbin.parent),
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
        }
        if os.name == "nt":
            kwargs["creationflags"] = 0x00000008 | 0x00000200
        else:
            kwargs["start_new_session"] = True
            if sys.platform == "darwin":
                try:
                    subprocess.run(["xattr", "-dr", "com.apple.quarantine",
                                    str(ccbin)], timeout=5,
                                   stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
                    os.chmod(ccbin, 0o755)
                except Exception:
                    pass
        subprocess.Popen([str(ccbin)], **kwargs)
        return True, "CC Switch 已启动"
    except Exception as e:
        return False, f"启动失败: {str(e)[:160]}"


# ═══════════════════════════════════════════════════════════════
#  API key connectivity test
# ═══════════════════════════════════════════════════════════════
def test_key(base_url, api_key, model):
    """Minimal OpenAI /v1/models probe. Returns (ok, message).

    TLS resilience: portable Pythons sometimes ship without a usable
    system trust store. Try certifi first if available, then default."""
    import ssl
    base_url = (base_url or "").strip().rstrip("/")
    api_key = (api_key or "").strip()
    if not base_url or not api_key:
        return False, "缺少 base_url 或 api_key"
    url = base_url + "/models"
    req = urllib.request.Request(url, method="GET", headers={
        "authorization": f"Bearer {api_key}",
        "user-agent": "CodexPortable/ConfigCenter",
    })
    contexts = []
    try:
        import certifi  # type: ignore
        contexts.append(ssl.create_default_context(cafile=certifi.where()))
    except Exception:
        pass
    contexts.append(None)

    last_err = "无法连接"
    for ctx in contexts:
        try:
            kwargs = {"timeout": 15}
            if ctx is not None:
                kwargs["context"] = ctx
            with urllib.request.urlopen(req, **kwargs) as resp:
                if 200 <= resp.status < 300:
                    body = resp.read(2000).decode("utf-8", "replace")
                    count = ""
                    try:
                        data = json.loads(body)
                        if isinstance(data, dict) and "data" in data:
                            count = f" ({len(data['data'])} 个模型)"
                    except Exception:
                        pass
                    return True, f"连接成功{count}"
                return False, f"HTTP {resp.status}"
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                return False, "API Key 无效或无权限 (HTTP %d)" % e.code
            if e.code in (400, 404):
                return True, "端点可达 (HTTP %d)" % e.code
            try:
                detail = e.read(300).decode("utf-8", "replace")
            except Exception:
                detail = ""
            return False, f"HTTP {e.code} {detail[:120]}"
        except Exception as e:
            last_err = f"无法连接: {str(e)[:120]}"
            continue
    return False, last_err


# ═══════════════════════════════════════════════════════════════
#  Embedded UI (rich, tabbed, onboarding wizard). Styled to match the
#  OpenClaw / Hermes portable config centers: warm dark theme, cards,
#  tabs, first-run wizard. Loaded from lib/config_ui.html.
# ═══════════════════════════════════════════════════════════════
_UI_FILE = SCRIPT_DIR / "config_ui.html"


def _load_page():
    try:
        return _UI_FILE.read_text(encoding="utf-8")
    except Exception:
        return ("<html><body style='font-family:sans-serif;padding:40px'>"
                "<h2>配置中心 UI 文件缺失</h2><p>lib/config_ui.html 未找到。"
                "请重新下载发布包。</p></body></html>")


PAGE = _load_page()


# ═══════════════════════════════════════════════════════════════
#  HTTP handler
# ═══════════════════════════════════════════════════════════════
class Handler(BaseHTTPRequestHandler):
    timeout = 30

    def _host_ok(self):
        host = self.headers.get("Host", "")
        try:
            port = self.server.server_address[1]
        except Exception:
            port = PORT
        return host in (f"127.0.0.1:{port}", f"localhost:{port}")

    def _reject_host(self):
        if self._host_ok():
            return False
        self.send_response(421)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"error":"Host mismatch"}')
        return True

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, html):
        html = html.replace("__CC_TOKEN__", SERVER_TOKEN)
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy",
                         "default-src 'self' 'unsafe-inline'")
        self.end_headers()
        self.wfile.write(body)

    def _csrf_ok(self):
        tok = self.headers.get("X-CC-Token", "")
        return secrets.compare_digest(tok, SERVER_TOKEN)

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self._reject_host():
            return
        try:
            if self.path in ("/", "/index.html"):
                self._html(PAGE)
            elif self.path == "/api/state":
                cur = read_current()
                if cur:
                    cur = {k: v for k, v in cur.items() if k != "api_key"}
                self._json({
                    "providers_catalog": PROVIDERS,
                    "current": cur,
                    "saved": list_providers(),
                    "has_config": cur is not None,
                })
            elif self.path == "/api/heartbeat":
                self._json({"alive": True})
            elif self.path == "/api/view":
                self._json(view_config())
            elif self.path == "/api/logs":
                self._json(read_logs())
            elif self.path == "/api/diagnose":
                self._json({"checks": run_diagnose()})
            else:
                self._json({"error": "not found"}, 404)
        except Exception as e:
            self._json({"error": str(e)[:200]}, 500)

    def do_POST(self):
        if self._reject_host():
            return
        if not self._csrf_ok():
            self._json({"ok": False, "error": "missing or invalid token"}, 403)
            return
        try:
            n = min(int(self.headers.get("Content-Length", 0)), 1_000_000)
            raw = self.rfile.read(n) if n else b"{}"
            data = json.loads(raw or b"{}")
        except Exception:
            self._json({"ok": False, "error": "bad request body"}, 400)
            return
        try:
            if self.path == "/api/save":
                save_provider(data.get("name", ""), data.get("base_url", ""),
                              data.get("api_key", ""), data.get("model", ""))
                self._json({"ok": True})
            elif self.path == "/api/test":
                ok, msg = test_key(data.get("base_url", ""),
                                   data.get("api_key", ""), data.get("model", ""))
                self._json({"ok": ok, "message": msg})
            elif self.path == "/api/activate":
                activate_provider(data.get("id", ""))
                self._json({"ok": True})
            elif self.path == "/api/import":
                count = import_config(data)
                self._json({"ok": True, "count": count})
            elif self.path == "/api/unbind":
                removed = unbind_device()
                self._json({"ok": True, "removed": removed})
            elif self.path == "/api/launch-ccswitch":
                ok, msg = launch_ccswitch()
                self._json({"ok": ok, "message": msg})
            elif self.path == "/api/export":
                self._json(export_config())
            else:
                self._json({"ok": False, "error": "not found"}, 404)
        except Exception as e:
            self._json({"ok": False, "error": str(e)[:200]}, 400)


def main():
    server = None
    actual = PORT
    for p in range(PORT, PORT + 10):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", p), Handler)
            actual = p
            break
        except OSError:
            continue
    if server is None:
        print(f"  [!] 端口 {PORT}-{PORT+9} 都被占用", file=sys.stderr)
        sys.exit(1)
    url = f"http://127.0.0.1:{actual}"
    print(f"  配置中心: {url}")
    if not os.environ.get("CODEX_BROWSER_OPENED"):
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
