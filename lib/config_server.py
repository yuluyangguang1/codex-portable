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

def _read_version():
    vf = PORTABLE_ROOT / "VERSION"
    try:
        return vf.read_text(encoding="utf-8").strip()
    except Exception:
        return "dev"

VERSION = _read_version()

PORT = 17590          # config-center port (distinct from cc-switch GUI)
APP_TYPE = "codex"    # which cc-switch app_type this panel manages

# Per-process CSRF token (same design as claude-portable + openclaw).
SERVER_TOKEN = secrets.token_hex(32)

# ── Provider catalog ────────────────────────────────────────────────
# Codex CLI talks the OpenAI wire protocol (responses API or chat
# completions). Third-party providers must expose an OpenAI-compatible
# endpoint. The key is stored in auth.json as OPENAI_API_KEY, and the
# base_url + model go into config.toml.
# Models updated 2026-06-09 (verified via OpenRouter + official APIs).
PROVIDERS = [
    # ── 海外主流 ──
    {"id": "openai", "name": "OpenAI 官方", "base_url": "https://api.openai.com/v1",
     "models": ["gpt-5.5-pro", "gpt-5.5", "gpt-5.4-pro", "gpt-5.4",
                "gpt-5.4-mini", "gpt-5.4-nano", "gpt-5.1-codex-max",
                "gpt-5.1-codex", "gpt-5.1", "gpt-5-mini", "gpt-5-nano",
                "o4-mini-high", "o4-mini", "o3", "o3-mini",
                "gpt-4.1", "gpt-4.1-mini"],
     "key_hint": "sk-...", "note": "官方直连，GPT-5.5 / Codex / o4 最新",
     "tags": ["hot"]},
    {"id": "anthropic", "name": "Anthropic (Claude)", "base_url": "https://api.anthropic.com/v1",
     "models": ["claude-opus-4-8", "claude-opus-4-7-fast", "claude-opus-4-7",
                "claude-opus-4-6-fast", "claude-opus-4-6", "claude-opus-4-5",
                "claude-sonnet-4-6", "claude-opus-4", "claude-haiku-4-5"],
     "key_hint": "sk-ant-...", "note": "Claude Opus 4.8 最新，需 Anthropic API Key",
     "tags": ["hot"]},
    {"id": "openrouter", "name": "OpenRouter (聚合)", "base_url": "https://openrouter.ai/api/v1",
     "models": ["openai/gpt-5.5-pro", "openai/gpt-5.5",
                "anthropic/claude-opus-4.8", "anthropic/claude-opus-4.7",
                "google/gemini-3.5-flash", "google/gemini-3.1-pro-preview",
                "deepseek/deepseek-v4-pro", "deepseek/deepseek-v4-flash",
                "x-ai/grok-4.3", "x-ai/grok-4.20",
                "qwen/qwen3.7-max", "qwen/qwen3.7-plus",
                "meta-llama/llama-4-maverick", "meta-llama/llama-4-scout",
                "moonshotai/kimi-k2.6", "z-ai/glm-5.1",
                "minimax/minimax-m3", "mistral/mistral-large-3"],
     "key_hint": "sk-or-...", "note": "聚合 100+ 模型，一个 Key 通用",
     "tags": ["hot", "cheap"]},
    {"id": "google", "name": "Google (Gemini)", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
     "models": ["gemini-3.5-flash", "gemini-3.1-pro-preview", "gemini-3.1-flash-lite",
                "gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite"],
     "key_hint": "粘贴 Google AI API Key", "note": "Gemini 3.5 最新，支持 OpenAI 兼容端点",
     "tags": ["hot", "free"]},
    {"id": "xai", "name": "xAI (Grok)", "base_url": "https://api.x.ai/v1",
     "models": ["grok-4.3", "grok-4.20", "grok-4.20-multi-agent"],
     "key_hint": "xai-...", "note": "Grok 4.3 最新，多智能体模式",
     "tags": ["hot"]},
    {"id": "mistral", "name": "Mistral", "base_url": "https://api.mistral.ai/v1",
     "models": ["mistral-large-3", "mistral-large-latest", "mistral-medium-latest",
                "mistral-small-latest", "codestral-latest", "pixtral-large-latest",
                "ministral-8b-latest"],
     "key_hint": "粘贴 Mistral API Key", "note": "Mistral Large 3 最新，Codestral 代码专精",
     "tags": ["hot"]},
    {"id": "deepseek", "name": "DeepSeek", "base_url": "https://api.deepseek.com/v1",
     "models": ["deepseek-v4-pro", "deepseek-v4-flash", "deepseek-r1",
                "deepseek-r1-0528", "deepseek-chat", "deepseek-reasoner"],
     "key_hint": "sk-...", "note": "V4 系列 + R1 推理，性价比极高",
     "tags": ["hot", "cn", "cheap"]},
    {"id": "groq", "name": "Groq", "base_url": "https://api.groq.com/openai/v1",
     "models": ["llama-4-scout-17b-16e-instruct", "llama-4-maverick",
                "llama-3.3-70b-versatile", "deepseek-r1-distill-llama-70b",
                "qwen/qwen3-32b", "gemma2-9b-it"],
     "key_hint": "gsk_...", "note": "超快推理，Llama 4 / DeepSeek R1 蒸馏",
     "tags": ["fast", "free"]},
    {"id": "perplexity", "name": "Perplexity", "base_url": "https://api.perplexity.ai",
     "models": ["sonar-pro", "sonar-reasoning-pro", "sonar-deep-research",
                "sonar-reasoning", "sonar"],
     "key_hint": "pplx-...", "note": "联网搜索增强，Deep Research 深度研究",
     "tags": ["hot"]},
    {"id": "cohere", "name": "Cohere", "base_url": "https://api.cohere.com/v2",
     "models": ["command-a", "command-r-plus", "command-r"],
     "key_hint": "粘贴 Cohere API Key", "note": "Command A 最新，企业级 RAG",
     "tags": ["free"]},
    {"id": "amazon", "name": "Amazon (Nova)", "base_url": "https://bedrock-runtime.us-east-1.amazonaws.com/v1",
     "models": ["nova-premier-v1", "nova-pro-v1", "nova-lite-v1", "nova-micro-v1"],
     "key_hint": "粘贴 AWS Bedrock API Key", "note": "Amazon Nova 系列，AWS 原生",
     "tags": ["free"]},
    # ── 开源聚合 / 高速推理 ──
    {"id": "together", "name": "Together", "base_url": "https://api.together.xyz/v1",
     "models": ["meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
                "deepseek-ai/DeepSeek-V4-Pro", "Qwen/Qwen3-Coder-480B-A35B-Instruct",
                "moonshotai/Kimi-K2.6", "zai-org/GLM-5.1",
                "MiniMaxAI/MiniMax-M3"],
     "key_hint": "粘贴 Together API Key", "note": "开源模型托管，Llama 4 / V4 Pro",
     "tags": ["cheap"]},
    {"id": "fireworks", "name": "Fireworks", "base_url": "https://api.fireworks.ai/inference/v1",
     "models": ["accounts/fireworks/models/llama4-maverick-instruct-basic",
                "accounts/fireworks/models/llama4-scout-instruct-basic",
                "accounts/fireworks/models/deepseek-v4-pro",
                "accounts/fireworks/models/qwen3-coder-480b-a35b-instruct"],
     "key_hint": "粘贴 Fireworks API Key", "note": "高速推理，Llama 4 / V4 Pro",
     "tags": ["fast", "cheap"]},
    {"id": "deepinfra", "name": "DeepInfra", "base_url": "https://api.deepinfra.com/v1/openai",
     "models": ["deepseek-ai/DeepSeek-V4-Pro",
                "meta-llama/Llama-4-Maverick-17B-128E-Instruct",
                "Qwen/Qwen3-Coder", "zai-org/GLM-5.1",
                "moonshotai/Kimi-K2.6"],
     "key_hint": "粘贴 DeepInfra API Key", "note": "极低价格开源模型",
     "tags": ["cheap"]},
    {"id": "cerebras", "name": "Cerebras", "base_url": "https://api.cerebras.ai/v1",
     "models": ["llama-4-scout-17b-16e-instruct", "llama-4-maverick-17b-128e-instruct",
                "llama3.3-70b", "qwen-3-coder-480b", "qwen-3-32b",
                "deepseek-r1-distill-llama-70b"],
     "key_hint": "粘贴 Cerebras API Key", "note": "1500 tok/s 极速推理，免费额度",
     "tags": ["fast", "free"]},
    # ── 国产模型 ──
    {"id": "dashscope", "name": "通义千问 / 阿里", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
     "models": ["qwen3.7-max", "qwen3.7-plus", "qwen3.6-max", "qwen3.6-plus",
                "qwen3-coder-plus", "qwen3-coder", "qwen-max-latest", "qwen-plus-latest"],
     "key_hint": "sk-...", "note": "阿里云，Qwen 3.7 最新，Coder 代码专精",
     "tags": ["cn", "hot"]},
    {"id": "zhipu", "name": "智谱 GLM", "base_url": "https://open.bigmodel.cn/api/paas/v4",
     "models": ["glm-5.1", "glm-5-turbo", "glm-5", "glm-4.7", "glm-4.7-flash",
                "glm-4.6", "glm-4.5-air"],
     "key_hint": "粘贴智谱 API Key", "note": "GLM-5.1 最新，全系列 OpenAI 兼容",
     "tags": ["cn", "hot"]},
    {"id": "kimi", "name": "Kimi / Moonshot", "base_url": "https://api.moonshot.cn/v1",
     "models": ["kimi-k2.6", "kimi-k2.5", "kimi-k2-thinking", "kimi-k2",
                "moonshot-v1-128k"],
     "key_hint": "sk-...", "note": "K2.6 最新，思考模式 + 长上下文",
     "tags": ["cn", "hot"]},
    {"id": "doubao", "name": "豆包 / 火山引擎", "base_url": "https://ark.cn-beijing.volces.com/api/v3",
     "models": ["doubao-seed-1.6", "doubao-seed-1.6-thinking", "doubao-1.5-pro-256k",
                "doubao-1.5-lite-32k"],
     "key_hint": "粘贴火山引擎 API Key", "note": "字节跳动，Seed 1.6 最新",
     "tags": ["cn", "cheap"]},
    {"id": "minimax", "name": "MiniMax (海螺)", "base_url": "https://api.minimaxi.com/v1",
     "models": ["MiniMax-M3", "MiniMax-M2.7", "MiniMax-M2.7-highspeed", "MiniMax-M2.5"],
     "key_hint": "粘贴 MiniMax API Key", "note": "M3 最新，OpenAI 兼容",
     "tags": ["cn"]},
    {"id": "stepfun", "name": "阶跃星辰 (Step)", "base_url": "https://api.stepfun.com/v1",
     "models": ["step-3.7-flash", "step-3.5-flash", "step-2-16k", "step-2-mini"],
     "key_hint": "粘贴阶跃星辰 API Key", "note": "Step 3.7 最新，速度快",
     "tags": ["cn", "fast"]},
    {"id": "baichuan", "name": "百川", "base_url": "https://api.baichuan-ai.com/v1",
     "models": ["Baichuan4-Turbo", "Baichuan4-Air", "Baichuan4", "Baichuan3-Turbo"],
     "key_hint": "粘贴百川 API Key", "note": "百川 AI，Baichuan4 最新",
     "tags": ["cn"]},
    {"id": "yi", "name": "零一万物", "base_url": "https://api.lingyiwanwu.com/v1",
     "models": ["yi-lightning", "yi-large", "yi-large-turbo", "yi-medium", "yi-vision"],
     "key_hint": "粘贴零一万物 API Key", "note": "Yi-Lightning 极速，yi-large 强推理",
     "tags": ["cn", "fast"]},
    {"id": "spark", "name": "讯飞星火", "base_url": "https://spark-api-open.xf-yun.com/v1",
     "models": ["4.0Ultra", "generalv3.5", "generalv3", "lite"],
     "key_hint": "粘贴讯飞 API Key", "note": "科大讯飞，4.0Ultra 最新",
     "tags": ["cn"]},
    {"id": "hunyuan", "name": "腾讯混元", "base_url": "https://api.hunyuan.cloud.tencent.com/v1",
     "models": ["hunyuan-turbo", "hunyuan-large", "hunyuan-pro",
                "hunyuan-standard", "hunyuan-lite"],
     "key_hint": "粘贴腾讯混元 API Key", "note": "腾讯混元，Turbo 最新",
     "tags": ["cn"]},
    {"id": "ernie", "name": "文心一言 / 百度", "base_url": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat",
     "models": ["ernie-4.5-turbo-128k", "ernie-x1-turbo", "ernie-4.0-turbo",
                "ernie-4.0-8k", "ernie-3.5-8k"],
     "key_hint": "粘贴百度 API Key", "note": "百度文心，ERNIE 4.5 最新",
     "tags": ["cn"]},
    {"id": "siliconflow", "name": "SiliconFlow (硅基流动)", "base_url": "https://api.siliconflow.cn/v1",
     "models": ["deepseek-ai/DeepSeek-V4-Pro", "Qwen/Qwen3.7-Max",
                "moonshotai/Kimi-K2.6", "THUDM/GLM-5.1",
                "deepseek-ai/DeepSeek-R1"],
     "key_hint": "sk-...", "note": "国产聚合，多模型一站式",
     "tags": ["cn", "cheap"]},
    # ── 小米 MiMo ──
    {"id": "xiaomi", "name": "小米 MiMo", "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
     "models": ["mimo-v2.5-pro", "mimo-v2.5", "mimo-v2-pro"],
     "key_hint": "tp-...", "note": "小米 MiMo 推理模型，tp- 开头的 Key",
     "tags": ["cn"]},
    # ── 自定义 ──
    {"id": "custom", "name": "自定义 / 中转站", "base_url": "",
     "models": [], "custom": True,
     "key_hint": "粘贴中转站 API Key", "note": "填写中转站/自建网关的 base_url",
     "tags": []},
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
    """Return the currently-active codex provider as a dict, or None."""
    if not CCS_DB.exists():
        return None
    db = _connect()
    try:
        row = db.execute(
            "SELECT id, name, settings_config FROM providers "
            "WHERE app_type=? AND is_current=1 LIMIT 1", (APP_TYPE,)
        ).fetchone()
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
    finally:
        db.close()


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
    # Always write config.toml completely (overwrite) to prevent stale
    # provider config from a previous save lingering in the file.
    toml_lines = []
    if base_url != "https://api.openai.com/v1":
        # Codex v0.136+ only supports wire_api = "responses".
        # The "chat" mode was removed.
        toml_lines.append('model_provider = "custom"')
        toml_lines.append(f'model = "{_toml_escape(model or "gpt-5.5")}"')
        toml_lines.append("")
        toml_lines.append("[model_providers.custom]")
        toml_lines.append(f'name = "{_toml_escape(name or "Custom")}"')
        toml_lines.append(f'base_url = "{_toml_escape(base_url)}"')
        toml_lines.append('wire_api = "responses"')
        toml_lines.append('env_key = "OPENAI_API_KEY"')
    elif model:
        toml_lines.append(f'model = "{_toml_escape(model)}"')
    # If neither custom provider nor custom model, write empty config
    # to clear any stale config.toml from a previous provider.
    _atomic_write(codex_dir / "config.toml", "\n".join(toml_lines) + ("\n" if toml_lines else ""))

    return pid


def _toml_escape(s):
    """Escape a string for a TOML double-quoted value. Without this, a
    backslash or quote in a model/provider name or base_url would produce
    invalid TOML and codex would fail to start."""
    return (str(s).replace("\\", "\\\\").replace('"', '\\"')
            .replace("\n", "").replace("\r", ""))


BACKUP_DIR = DATA_DIR / ".backups"
BACKUP_MAX = 5  # rolling backup count


def _atomic_write(path, content):
    """Write file atomically via tmp+fsync+rename with rolling backups."""
    from pathlib import Path
    import shutil
    p = Path(path)
    was_first_write = not p.exists()

    # Cleanup stale uuid tmp files (>1 hour old) from prior crashes
    try:
        import time as _time
        for stale in p.parent.glob(p.stem + ".*.tmp"):
            try:
                if stale.stat().st_mtime < _time.time() - 3600:
                    stale.unlink(missing_ok=True)
            except Exception:
                pass
    except Exception:
        pass

    # Rolling backup: copy current file before overwriting
    if p.exists() and p.stat().st_size > 0:
        try:
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = BACKUP_DIR / f"{p.name}.{ts}"
            shutil.copy2(str(p), str(backup))
            # Prune old backups (keep newest BACKUP_MAX)
            backups = sorted(BACKUP_DIR.glob(f"{p.name}.*"),
                             key=lambda f: f.stat().st_mtime, reverse=True)
            for old in backups[BACKUP_MAX:]:
                old.unlink(missing_ok=True)
        except Exception:
            pass  # backup failure should not block writes

    import uuid as _uuid
    tmp = p.with_suffix("." + _uuid.uuid4().hex[:8] + p.suffix + ".tmp")
    # Write with fsync (critical for USB/exFAT)
    # Prevent symlink following (#22: avoid overwriting arbitrary files)
    if p.is_symlink():
        p.unlink()
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, content.encode("utf-8"))
        try:
            os.fsync(fd)
        except OSError as e:
            import sys
            print(f"[config] fsync failed (eject safely): {e}", file=sys.stderr)
    finally:
        os.close(fd)
    try:
        os.replace(str(tmp), str(p))
    except Exception:
        try:
            tmp.unlink()
        except Exception:
            pass
        raise

    # Seed backup on first write so USB yank recovery has a baseline
    if was_first_write:
        try:
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = BACKUP_DIR / f"{p.name}.{ts}"
            shutil.copy2(str(p), str(backup))
        except Exception:
            pass


def _safe_read(path):
    """Read config with fallback to newest backup on failure."""
    from pathlib import Path
    p = Path(path)
    try:
        if p.exists():
            return p.read_text(encoding="utf-8")
    except Exception:
        pass
    # Fallback: try newest backup
    try:
        backups = sorted(BACKUP_DIR.glob(f"{p.name}.*"),
                         key=lambda f: f.stat().st_mtime, reverse=True)
        if backups:
            return backups[0].read_text(encoding="utf-8")
    except Exception:
        pass
    return None


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
    # If data/.codex is a symlink or junction (active session), refuse to
    # traverse the target — it's the system ~/.codex, which holds auth.json
    # with the API key. Surfacing its contents in the panel would be a leak.
    # Python's is_symlink() does NOT detect Windows junctions, so check
    # reparse point attribute explicitly.
    _is_link = codex_dir.is_symlink()
    if not _is_link and os.name == "nt":
        try:
            _is_link = bool(os.stat(codex_dir).st_file_attributes & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT
        except Exception:
            pass
    if _is_link:
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


def reset_config():
    """Delete all codex providers from cc-switch DB and remove config files.
    Also regenerates the CSRF token so the old token is invalidated."""
    global SERVER_TOKEN
    SERVER_TOKEN = secrets.token_hex(32)
    removed = 0
    if CCS_DB.exists():
        try:
            db = _connect()
            cur = db.execute("DELETE FROM providers WHERE app_type=?", (APP_TYPE,))
            removed = cur.rowcount
            db.commit()
            db.close()
        except Exception:
            pass
    codex_dir = DATA_DIR / ".codex"
    for f in ("auth.json", "config.toml"):
        try:
            p = codex_dir / f
            if p.exists():
                p.unlink()
        except Exception:
            pass
    return removed


def launch_ccswitch():
    """Launch the bundled cc-switch GUI as a detached background process.

    The config center is the primary onboarding path, but cc-switch is a
    full native GUI with extra features. Users who prefer it can start it
    from here. Returns (ok, message). Never blocks; uses list-form args
    (no shell=True)."""
    # Check if already running (#30: prevent duplicate spawns)
    import subprocess as _sp
    try:
        if os.name == "nt":
            chk = _sp.run(["tasklist", "/fi", "ImageName eq cc-switch.exe"],
                          capture_output=True, text=True, timeout=5)
            if "cc-switch.exe" in chk.stdout:
                return True, "CC Switch 已在运行"
        else:
            chk = _sp.run(["pgrep", "-f", "cc-switch"],
                          capture_output=True, text=True, timeout=5)
            if chk.returncode == 0:
                return True, "CC Switch 已在运行"
    except Exception:
        pass
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
    # macOS Homebrew/system Python often lacks root certs in the OpenSSL
    # bundle.  Try loading from the macOS System keychain via Security
    # framework, then fall back to an unverified context as last resort.
    try:
        import platform
        if platform.system() == "Darwin":
            import subprocess, tempfile
            pem = subprocess.check_output(
                ["security", "find-certificate", "-a", "-p",
                 "/System/Library/Keychains/SystemRootCertificates.keychain"],
                timeout=5, stderr=subprocess.DEVNULL)
            with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f:
                f.write(pem)
                mac_ca = f.name
            ctx = ssl.create_default_context(cafile=mac_ca)
            contexts.append(ctx)
            os.unlink(mac_ca)
    except Exception:
        pass
    # Do NOT fall back to CERT_NONE — leaking an API key over an
    # unauthenticated connection is worse than failing the test.

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
        html = _UI_FILE.read_text(encoding="utf-8")
        return html.replace("__VERSION__", VERSION)
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
                         "default-src 'self' 'unsafe-inline'; img-src 'self' data:")
        self.end_headers()
        self.wfile.write(body)

    def _csrf_ok(self):
        tok = self.headers.get("X-CC-Token", "")
        return secrets.compare_digest(tok, SERVER_TOKEN)

    def log_message(self, *a):
        pass

    def parse_request(self):
        """Override to check raw request line BEFORE path normalization.
        Only blocks null bytes and backslashes here — '..' traversal is
        handled by _path_safe() which checks the normalized path portion
        (after query string is stripped), avoiding false positives on
        query parameter values that happen to contain '..'.
        """
        raw = getattr(self, 'raw_requestline', b'')
        if isinstance(raw, bytes):
            raw = raw.decode('utf-8', 'replace')
        if '\\' in raw or '\x00' in raw:
            self.requestline = raw.strip()
            self.request_version = 'HTTP/1.1'
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"invalid path"}')
            return False
        return super().parse_request()

    def _path_safe(self):
        """Defense-in-depth: also check normalized path."""
        p = self.path.split("?")[0]
        if ".." in p or "\\" in p or "\0" in p:
            self._json({"error": "invalid path"}, 400)
            return False
        return True

    def do_GET(self):
        if self._reject_host():
            return
        if not self._path_safe():
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
        if not self._path_safe():
            return
        if not self._csrf_ok():
            self._json({"ok": False, "error": "missing or invalid token"}, 403)
            return
        # Layer 3: require JSON Content-Type on writes (defense-in-depth)
        ct = (self.headers.get("Content-Type", "")).split(";")[0].strip().lower()
        if ct != "application/json":
            self._json({"ok": False, "error": "Unsupported Media Type"}, 415)
            return
        try:
            n = min(int(self.headers.get("Content-Length", 0)), 65_536)
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
                # SSRF protection: validate URL before testing
                import urllib.parse
                _url = data.get("base_url", "")
                _parsed = urllib.parse.urlparse(_url)
                _ok = True
                if _parsed.scheme not in ("https", "http"):
                    _ok = False
                else:
                    _host = (_parsed.hostname or "").lower()
                    _blocked = ("127.", "0.", "localhost", "169.254.", "10.",
                                "172.16.", "172.17.", "172.18.", "172.19.",
                                "172.20.", "172.21.", "172.22.", "172.23.",
                                "172.24.", "172.25.", "172.26.", "172.27.",
                                "172.28.", "172.29.", "172.30.", "172.31.",
                                "192.168.", "0.0.0.0", "[::1]", "100.64.")
                    for b in _blocked:
                        if _host.startswith(b) or _host == b.rstrip("."):
                            _ok = False; break
                # DNS resolution check (#20+#21: IPv4-mapped IPv6 + DNS rebinding)
                if _ok and _parsed.hostname:
                    import socket
                    _ip_blocked = ("127.", "0.", "10.", "169.254.",
                                   "172.16.", "172.17.", "172.18.", "172.19.",
                                   "172.20.", "172.21.", "172.22.", "172.23.",
                                   "172.24.", "172.25.", "172.26.", "172.27.",
                                   "172.28.", "172.29.", "172.30.", "172.31.",
                                   "192.168.", "100.64.", "::ffff:", "::1", "fe80:")
                    try:
                        for fam, _, _, _, addr in socket.getaddrinfo(_parsed.hostname, None):
                            rip = addr[0]
                            for bip in _ip_blocked:
                                if rip.startswith(bip):
                                    _ok = False; break
                            if not _ok: break
                    except Exception:
                        _ok = False  # DNS failure = reject
                if not _ok:
                    self._json({"ok": False, "error": "URL not allowed (only public http/https)"}, 400)
                else:
                    ok, msg = test_key(_url, data.get("api_key", ""), data.get("model", ""))
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
            elif self.path == "/api/reset":
                removed = reset_config()
                self._json({"ok": True, "removed": removed})
            elif self.path == "/api/launch-ccswitch":
                ok, msg = launch_ccswitch()
                self._json({"ok": ok, "message": msg})
            elif self.path == "/api/export":
                self._json(export_config())
            elif self.path == "/api/shutdown":
                self._json({"ok": True, "message": "配置中心即将关闭"})
                import threading
                threading.Thread(target=self.server.shutdown, daemon=True).start()
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

    # Write runtime.json so launcher knows the actual port
    import json as _json
    runtime = {"config_port": actual, "config_url": url,
               "pid": os.getpid()}  # token excluded — never read by launchers
    try:
        _atomic_write(DATA_DIR / ".cc-switch" / "runtime.json",
                      _json.dumps(runtime, indent=2))
    except Exception:
        pass
    if not os.environ.get("CODEX_BROWSER_OPENED"):
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    print("  配置中心已关闭")


if __name__ == "__main__":
    main()
