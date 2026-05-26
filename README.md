# Codex Portable

把 [OpenAI Codex CLI](https://github.com/openai/codex)（终端编程 AI Agent）打包成便携版。插上 U 盘即可在任意电脑上运行，无需安装任何依赖。

Pack [OpenAI Codex CLI](https://github.com/openai/codex) into a portable edition. Plug in a USB drive and run on any computer with zero dependencies.

---

## 特性

- **零安装** — 不需要 Node.js、Rust 或任何运行时（Codex CLI 是 Rust 编译的单二进制）
- **零痕迹** — 拔走 U 盘后电脑上不留任何数据
- **跨平台** — macOS (Apple Silicon + Intel) / Linux x64 / Windows x64
- **CC Switch 集成** — GUI 配置第三方 OpenAI 兼容 API（中转站、one-api、Azure、DeepSeek 等）
- **设备绑定** — 防复制保护，便携包只能在原始 U 盘上运行
- **数据随身** — 对话历史、配置全部存在便携包内
- **`CODEX_HOME` 隔离** — 启动时显式指向便携目录，与系统 `~/.codex` 隔离

---

## 快速开始

### 使用发布包（推荐）

从 [Releases](https://github.com/yuluyangguang1/codex-portable/releases) 下载 zip，解压到 U 盘或任意目录。

| 平台 | 启动方式 |
|------|----------|
| macOS | 双击 `CodexPortable.command` |
| Windows | 双击 `CodexPortable.bat` |
| Linux | 运行 `./CodexPortable.sh` |

启动后 CC Switch GUI 自动打开 → 在 Codex 标签添加供应商 → 保存 → Codex CLI 启动。

### macOS 首次运行

macOS 可能提示"无法验证开发者"。解决方法：

1. 右键点击 `CodexPortable.command` → 选择"打开" → 弹窗中点"打开"
2. 或终端执行：`xattr -cr /path/to/codex-portable`

---

## 目录结构

```
codex-portable/
  CodexPortable.command    macOS 启动器
  CodexPortable.bat        Windows 启动器
  CodexPortable.sh         Linux 启动器
  bin/                     各平台二进制（CI 构建时下载）
    macos-arm64/codex
    macos-x64/codex
    linux-x64/codex
    windows-x64/codex.exe
  data/                    用户数据（gitignore）
    .cc-switch/            CC Switch 数据库
    .codex/                Codex CLI 配置和历史（auth.json + config.toml）
    .lock                  设备绑定锁
  lib/
    binding.sh             设备绑定（macOS/Linux）
    binding.ps1            设备绑定（Windows）
    check-config.ps1       配置检查（Windows）
  .github/workflows/
    build.yml              CI 构建 + 发布
```

---

## API 配置

Codex CLI 通过 `~/.codex/auth.json` + `~/.codex/config.toml` 两个文件管理配置。CC Switch 自动写入这两个文件。

### 通过 CC Switch（推荐）

启动后 CC Switch GUI 打开，切换到 **Codex** 标签：

- **OpenAI 官方** — 直接填 API Key
- **第三方中转站** — 填 base_url + API Key
- **DeepSeek / Kimi / GLM** — 选择对应模板
- **Azure OpenAI** — 填 endpoint + key + deployment 名

CC Switch 会自动生成 `auth.json` 和 `config.toml`。

### 手动配置

如果不用 CC Switch，可直接编辑：

`data/.codex/auth.json`：
```json
{
  "OPENAI_API_KEY": "sk-..."
}
```

`data/.codex/config.toml`：
```toml
model_provider = "custom"
model = "gpt-5.4"
model_reasoning_effort = "high"

[model_providers.custom]
name = "Custom Provider"
base_url = "https://your-provider/v1"
wire_api = "responses"
env_key = "OPENAI_API_KEY"
```

---

## 设备绑定

首次成功运行后自动绑定到当前 U 盘。复制到其他设备将无法运行。

解绑（原始所有者）：
```bash
# macOS
./CodexPortable.command --unlock

# Linux
./CodexPortable.sh --unlock

# Windows
CodexPortable.bat --unlock
```

---

## 构建

CI 自动从 [openai/codex releases](https://github.com/openai/codex/releases) 下载预编译二进制，从本仓库的 `cc-switch-assets` release 下载 cc-switch GUI。

手动触发构建：
```
GitHub → Actions → Build Codex Portable → Run workflow
```

打 tag 自动发布：
```bash
git tag v0.1.0
git push --tags
```

本地构建：
```bash
bash setup.sh             # 当前平台
bash setup.sh --all       # 所有平台（U 盘版）
```

会自动下载 codex 二进制 + cc-switch GUI 到对应的 `bin/` 目录。

---

## 上游项目

- **Codex CLI**：[openai/codex](https://github.com/openai/codex) — Rust 编写的终端编程 Agent，MIT 协议
- **CC Switch**：[farion1231/cc-switch](https://github.com/farion1231/cc-switch) — 跨平台 AI CLI 配置管理工具，原生支持 Codex
- **姊妹项目**：[claude-portable](https://github.com/yuluyangguang1/claude-portable) · [openclaw-portable](https://github.com/yuluyangguang1/openclaw-portable) · [hermes-portable](https://github.com/yuluyangguang1/hermes-portable)

Portable 版本的工作：
- 打包 Rust 编译的 codex 二进制（每个平台独立）
- 集成 CC Switch 自动写入 `auth.json` + `config.toml`
- 适配 U 盘便携场景（`CODEX_HOME` 重定向、符号链接、数据隔离）
- 设备绑定防复制

---

## License

MIT
