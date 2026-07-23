# OpenCodex Provider 配置 & 适配器逻辑 — 深度研究报告

> 用于集成到 codex-portable (config_server.py)
> 研究日期: 2026-07-23

---

## 一、架构总览

OpenCodex 是一个 **Responses API 代理服务器**，核心功能是：
1. 接收 OpenAI Responses API 格式的请求（来自 Codex CLI）
2. 根据 provider 配置，将请求转换为对应的上游 API 格式
3. 将上游响应转换回 Responses API 格式返回给客户端

```
Codex CLI ──(Responses API)──> OpenCodex ──(适配器转换)──> 各上游 Provider
                                    │
                                    ├── openai-responses → 直通 OpenAI Responses API
                                    ├── openai-chat      → 转换为 Chat Completions API
                                    ├── anthropic         → 转换为 Anthropic Messages API
                                    ├── google            → 转换为 Gemini generateContent API
                                    ├── kiro              → 转换为 Kiro (CodeWhisperer) 格式
                                    ├── azure-openai      → Azure OpenAI Responses API
                                    ├── cursor            → Cursor 专有 WebSocket 协议
                                    └── mimo-free         → MiMo Free (JWT 认证 + openai-chat)
```

---

## 二、适配器注册表（adapter-resolve.ts）

```typescript
switch (providerConfig.adapter) {
  case "openai-chat":      → createOpenAIChatAdapter(providerConfig)
  case "anthropic":        → createAnthropicAdapter(providerConfig, cacheRetention)
  case "openai-responses": → createResponsesPassthroughAdapter(providerConfig)
  case "google":           → createGoogleAdapter(providerConfig)
  case "kiro":             → createKiroAdapter(providerConfig)
  case "azure":
  case "azure-openai":     → createAzureAdapter(providerConfig)
  case "cursor":           → createCursorAdapter(providerConfig)
  case "mimo-free":        → createMimoFreeAdapter(providerConfig)
}
```

共 **8 种适配器**，覆盖 55 个 Provider。

---

## 三、Provider 完整清单（55 个）

### 3.1 按适配器分类

| 适配器 | Provider 数量 | Provider IDs |
|--------|-------------|-------------|
| `openai-responses` | 2 | openai (Codex login), openai-apikey |
| `openai-chat` | 35 | xai, kimi, opencode-go, neuralwatt, openrouter, orcarouter, groq, deepseek, cerebras, together, fireworks, firepass, moonshot, huggingface, nvidia, venice, zai, nanogpt, synthetic, qwen-cloud, qianfan, alibaba, alibaba-token-plan, alibaba-token-plan-intl, parallel, zenmux, litellm, ollama-cloud, mistral, minimax, minimax-cn, kimi-code, opencode-zen, vercel-ai-gateway, opencode-free, kilo, ollama, vllm, lm-studio, github-copilot, gitlab-duo, cloudflare-workers-ai |
| `anthropic` | 4 | anthropic (OAuth), anthropic-apikey, umans, xiaomi, cloudflare-ai-gateway |
| `google` | 3 | google (AI Studio), google-vertex, google-antigravity |
| `kiro` | 1 | kiro |
| `azure-openai` | 1 | azure-openai |
| `cursor` | 1 | cursor |
| `mimo-free` | 1 | mimo-free |

### 3.2 完整 Provider 配置表

#### openai-responses 适配器

| id | label | baseUrl | authKind | defaultModel | 备注 |
|----|-------|---------|----------|-------------|------|
| openai | OpenAI (Codex login) | https://chatgpt.com/backend-api/codex | forward | - | Codex login 账号池 |
| openai-apikey | OpenAI API | https://api.openai.com/v1 | key | gpt-5.5 | API Key 直连 |

#### anthropic 适配器

| id | label | baseUrl | authKind | defaultModel | models |
|----|-------|---------|----------|-------------|--------|
| anthropic | Anthropic Claude | https://api.anthropic.com | oauth | claude-sonnet-5 | claude-fable-5, claude-sonnet-5, claude-opus-4-8/7/6, claude-sonnet-4-6, claude-haiku-4-5 |
| anthropic-apikey | Anthropic (API key) | https://api.anthropic.com | key | claude-sonnet-5 | 同上 + liveModels |
| umans | Umans AI Coding Plan | https://api.code.umans.ai | key | umans-coder | umans-coder, umans-kimi-k2.7, umans-flash, umans-glm-5.2/5.1, umans-qwen3.6-35b-a3b |
| xiaomi | Xiaomi MiMo | https://api.xiaomimimo.com/anthropic | key | mimo-v2.5-pro | - |
| cloudflare-ai-gateway | Cloudflare AI Gateway | https://gateway.ai.cloudflare.com/v1/{account-id}/{gateway}/anthropic | key | - | - |

#### google 适配器

| id | label | baseUrl | authKind | googleMode | defaultModel |
|----|-------|---------|----------|-----------|-------------|
| google | Google Gemini | https://generativelanguage.googleapis.com | key | ai-studio (default) | gemini-3.5-flash |
| google-vertex | Google Vertex AI | https://aiplatform.googleapis.com | key | vertex | gemini-3-pro |
| google-antigravity | Google Antigravity | https://daily-cloudcode-pa.googleapis.com | oauth | cloud-code-assist | gemini-3.6-flash |

#### openai-chat 适配器（精选关键 Provider）

| id | baseUrl | authKind | defaultModel | 特殊配置 |
|----|---------|----------|-------------|---------|
| xai | https://api.x.ai/v1 | oauth | grok-4.5 | parallelToolCalls, preserveReasoningContent |
| kimi | https://api.kimi.com/coding/v1 | oauth | kimi-k2.7-code | modelSuffixBracketStrip, reasoningEffortMap |
| deepseek | https://api.deepseek.com | key | deepseek-v4-flash | thinkingEffortMap, preserveReasoningContent |
| openrouter | https://openrouter.ai/api/v1 | key | - | - |
| groq | https://api.groq.com/openai/v1 | key | - | - |
| ollama | http://localhost:11434/v1 | local | - | allowPrivateNetwork, allowBaseUrlOverride |
| vllm | http://localhost:8000/v1 | local | - | 同上 |
| lm-studio | http://localhost:1234/v1 | local | - | 同上 |
| cerebras | https://api.cerebras.ai/v1 | key | gpt-oss-120b | - |
| mistral | https://api.mistral.ai/v1 | key | codestral-latest | - |
| minimax | https://api.minimax.io/v1 | key | MiniMax-M3 | case-insensitive model id |
| minimax-cn | https://api.minimaxi.com/v1 | key | MiniMax-M3 | 中国区 |
| zai | https://api.z.ai/api/coding/paas/v4 | key | glm-5.2 | modelSuffixBracketStrip |
| nvidia | https://integrate.api.nvidia.com/v1 | key | - | freeTier, parallelToolCalls=false |
| opencode-go | https://opencode.ai/zen/go/v1 | key | kimi-k2.7-code | thinkingToggle, thinkingBudget |
| opencode-free | https://opencode.ai/zen/v1 | key | - | keyOptional, freeTier |
| alibaba-token-plan | https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1 | key | qwen3.8-max-preview | - |
| alibaba-token-plan-intl | (Singapore) | key | qwen3.7-max | - |
| qwen-cloud | (configurable) | key | - | baseUrlChoices |
| cloudflare-workers-ai | https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1 | key | @cf/meta/llama-3.3-70b-instruct-fp8-fast | freeTier |
| github-copilot | https://api.githubcopilot.com | oauth | gpt-4o | liveModels |

---

## 四、适配器转换逻辑详解

### 4.1 openai-chat 适配器（最核心，覆盖 35+ Provider）

**输入**: `OcxParsedRequest` (Responses API 解析后的内部格式)
**输出**: OpenAI Chat Completions API

#### 4.1.1 消息转换 (`messagesToChatFormat`)

```
Responses API 消息格式 → Chat Completions 消息格式
```

| Responses 角色 | Chat 角色 | 转换规则 |
|---------------|----------|---------|
| user | user | content 直接传递；图片转 image_url 格式 |
| developer | system | 角色重映射 |
| assistant | assistant | text 部分拼接为 content；toolCall 转为 tool_calls 数组 |
| toolResult | tool | 与 assistant tool_calls 配对；孤立的 toolResult 合成 assistant+tool 对 |

**关键逻辑**:
- **悬挂工具调用修复**: 如果 assistant 的 tool_calls 没有对应的 toolResult，自动合成缺失的 tool 消息
- **reasoning_content 保留**: 对于 `preserveReasoningContentModels` 中的模型，将 thinking 内容作为 `reasoning_content` 字段附加到 assistant 消息
- **空 assistant 消息处理**: 严格后端（如 xAI）拒绝无 content 的 assistant 消息，自动填充 `""`

#### 4.1.2 工具转换 (`toolsToChatFormat`)

```
Responses API tools → Chat Completions tools (function calling)
```

```json
{
  "type": "function",
  "function": {
    "name": "namespace__toolname",  // MCP 命名空间展平
    "description": "...",
    "parameters": { ... }
  }
}
```

**特殊处理**:
- **xAI**: 展开 oneOf/anyOf 根级组合 schema 为独立变体
- **Kimi**: 强制根级 `type: "object"`
- **Zen (opencode)**: 清理 `encrypted` 标记、规范化 type 数组

#### 4.1.3 推理控制

三种推理模式：
1. **reasoning_effort**: 直接发送 `reasoning_effort` 字段 (OpenAI, xAI, DeepSeek 等)
2. **thinking_budget**: 发送 `thinking_budget` 字段 (Qwen 系列)
3. **thinking toggle**: 发送 `thinking: {type: "enabled"|"disabled"}` (MiMo, GLM 5/5.1)

```typescript
if (thinkingBudgetModels) → body.thinking_budget = budget
else if (thinkingToggleModels) → body.thinking = { type: "enabled"|"disabled" }
else → body.reasoning_effort = effort
```

#### 4.1.4 流式解析 (`parseStream`)

解析 SSE `data:` 行，处理：
- `choices[0].delta.content` → `text_delta`
- `choices[0].delta.reasoning_content` → `reasoning_raw_delta`
- `choices[0].delta.tool_calls` → 缓冲后批量发射 `tool_call_start/delta/end`
- `choices[0].finish_reason` → 终止信号
- `usage` → token 统计
- `[DONE]` → 完成

**工具调用缓冲**: 流式工具调用按 `index` 键缓冲，直到 finish_reason 才批量发射（避免交叉问题）。

---

### 4.2 anthropic 适配器

**输入**: `OcxParsedRequest`
**输出**: Anthropic Messages API (`/v1/messages`)

#### 4.2.1 消息转换 (`messagesToAnthropicFormat`)

| Responses | Anthropic | 转换规则 |
|-----------|-----------|---------|
| user/developer | user | content 转换为 Anthropic content blocks |
| assistant (text) | assistant | `{type: "text", text: "..."}` |
| assistant (thinking) | assistant | `{type: "thinking", thinking: "...", signature: "..."}` + redacted_thinking |
| assistant (toolCall) | assistant | `{type: "tool_use", id: "...", name: "...", input: {...}}` |
| toolResult | user | `{type: "tool_result", tool_use_id: "...", content: "..."}` |

**关键差异**:
- Anthropic 要求 tool_result 紧跟在 assistant tool_use 后面（同一 user 消息中）
- 空历史或 assistant 结尾自动追加 `(continue)` 用户消息
- system prompt 作为顶层 `system` 字段传递（非消息数组）

#### 4.2.2 工具转换

```json
{
  "name": "toolname",
  "description": "...",
  "input_schema": { "type": "object", "properties": {...} }
}
```

**特殊处理**:
- 根级 schema 必须是 `type: "object"`（展平 oneOf/anyOf/allOf）
- OAuth 模式下工具名添加 `cc_` 前缀
- 兼容模式添加 `cx_` 前缀

#### 4.2.3 推理（Extended Thinking）

两种模式：
1. **传统 thinking**: `{type: "enabled", budget_tokens: N}` — 旧模型 (Haiku 4.5, Sonnet 4.x)
2. **adaptive thinking**: `{type: "adaptive"}` + `output_config.effort` — 新模型 (Sonnet 5, Fable 5, Opus 4.7+)

```typescript
// budget 映射
minimal → 1024, low → 4096, medium → 8192, high → 16384, xhigh → 24576, max → 32000

// max_tokens 必须 > budget_tokens
max_tokens = min(32000, max(maxOutput, budget + 8192))
```

#### 4.2.4 认证

- **OAuth**: `Authorization: Bearer <token>` + `anthropic-beta` + Claude Code 指纹头
- **API Key**: `x-api-key: <key>`

#### 4.2.5 Prompt Caching

在以下位置放置 `cache_control: {type: "ephemeral"}` 断点（最多 4 个）：
1. tools 最后一个块
2. system 最后一个块
3. 倒数第二个 user 消息
4. 最后一个 user 消息

#### 4.2.6 流式解析

SSE 事件类型：
- `message_start` → 提取 usage
- `content_block_start` → 识别 tool_use/redacted_thinking
- `content_block_delta` → text_delta/thinking_delta/signature_delta/input_json_delta
- `content_block_stop` → tool_call_end
- `message_delta` → 累积 usage + stop_reason
- `message_stop` → done

---

### 4.3 google 适配器

**输入**: `OcxParsedRequest`
**输出**: Gemini generateContent API

#### 4.3.1 消息转换 (`messagesToGeminiFormat`)

| Responses | Gemini | 转换规则 |
|-----------|--------|---------|
| user | user | parts: [{text: "..."}] 或 [{inline_data: {mime_type, data}}] |
| assistant (text) | model | parts: [{text: "..."}] |
| assistant (toolCall) | model | parts: [{functionCall: {name, args, id}}] |
| toolResult | user | parts: [{functionResponse: {name, response: {result}}}] + inline_data 图片 |

**关键差异**:
- system prompt 作为 `systemInstruction` 顶层字段
- Gemini 角色是 `"user"` / `"model"`（不是 `"assistant"`）
- 图片通过 `inline_data` (base64) 传递，不支持 URL

#### 4.3.2 工具转换

```json
{
  "functionDeclarations": [{
    "name": "toolname",
    "description": "...",
    "parameters": { ... }
  }]
}
```

#### 4.3.3 三种 Google 模式

1. **ai-studio** (默认): `generativelanguage.googleapis.com/v1beta/models/{model}:{method}` + `x-goog-api-key`
2. **vertex**: `aiplatform.googleapis.com/v1/projects/{project}/locations/{location}/publishers/google/models/{model}:{method}` + GCP ADC token
3. **cloud-code-assist** (Antigravity): `daily-cloudcode-pa.googleapis.com/v1internal:{method}` + CCA 信封包装

#### 4.3.4 推理

Gemini Flash 模型支持 `thinkingConfig: {thinkingLevel: "low"|"medium"|"high"}`。

---

### 4.4 openai-responses 适配器（直通）

直接转发 Responses API 请求到 OpenAI，不做格式转换。用于：
- `openai` (Codex login): 转发到 `chatgpt.com/backend-api/codex`
- `openai-apikey`: 转发到 `api.openai.com/v1`

仅做清理：
- 去除 reasoning 输入中的原始 content（保留 summary）
- 去除无效 item ID 前缀
- 去除 proxy 生成的 compaction items

---

### 4.5 azure-openai 适配器

包装 openai-responses，差异：
- 使用 `api-key` 头代替 `Authorization`
- 不支持 forward auth mode

---

### 4.6 kiro 适配器

Kiro (AWS CodeWhisperer) 专有协议，不通用。

---

### 4.7 cursor 适配器

Cursor 专有 WebSocket 协议，不通用。

---

### 4.8 mimo-free 适配器

包装 openai-chat，额外：
- JWT 自动引导（bootstrap endpoint）+ 缓存
- 注入 MiMo 防滥用系统标记
- 401/403 时刷新 JWT 重试

---

## 五、Bridge（Responses API 桥接层）

`bridge.ts` 将适配器的 `AdapterEvent` 流转换回 Responses API SSE 格式：

```
AdapterEvent 流 → bridgeToResponsesSSE() → Responses API SSE 流
```

| AdapterEvent | Responses API SSE 事件 |
|-------------|----------------------|
| text_delta | response.output_text.delta |
| thinking_delta | response.reasoning_text.delta |
| thinking_signature | 存入 reasoning envelope |
| tool_call_start | response.output_item.added (function_call) |
| tool_call_delta | response.function_call_arguments.delta |
| tool_call_end | response.output_item.done |
| reasoning_raw_delta | response.reasoning_text.delta |
| done | response.completed |
| error | response.failed |

关键功能：
- **心跳**: 2s 间隔发送 `response.heartbeat` 防止客户端超时
- **停滞超时**: 上游无响应时发送 `response.incomplete`
- **reasoning envelope**: Anthropic thinking signature 和 redacted blocks 编码为 `ocxr1:` 前缀的 encrypted_content
- **compaction**: 远程压缩请求转换为合成 compaction output item

---

## 六、类型系统（types.ts 核心类型）

```typescript
// 解析后的请求
interface OcxParsedRequest {
  modelId: string;
  context: {
    systemPrompt?: string[];
    messages: OcxMessage[];
    tools?: OcxTool[];
  };
  stream: boolean;
  options: {
    maxOutputTokens?: number;
    temperature?: number;
    topP?: number;
    stopSequences?: string[];
    toolChoice?: OcxToolChoice;
    parallelToolCalls?: boolean;
    reasoning?: string;        // "none" | "minimal" | "low" | "medium" | "high" | "xhigh" | "max"
    presencePenalty?: number;
    frequencyPenalty?: number;
  };
}

// 统一的适配器事件流
type AdapterEvent =
  | { type: "text_delta"; text: string }
  | { type: "thinking_delta"; thinking: string }
  | { type: "thinking_signature"; signature: string }
  | { type: "redacted_thinking"; data: string }
  | { type: "reasoning_raw_delta"; text: string }
  | { type: "tool_call_start"; id: string; name: string }
  | { type: "tool_call_delta"; arguments: string }
  | { type: "tool_call_end" }
  | { type: "done"; usage?: OcxUsage; stopReason?: string }
  | { type: "error"; message: string; usage?: OcxUsage };

// Provider 配置
interface ProviderRegistryEntry {
  id: string;
  label: string;
  adapter: string;            // "openai-chat" | "anthropic" | "google" | ...
  baseUrl: string;
  authKind: "forward" | "oauth" | "key" | "local";
  models?: string[];
  defaultModel?: string;
  liveModels?: boolean;
  modelContextWindows?: Record<string, number>;
  modelReasoningEfforts?: Record<string, string[]>;
  modelReasoningEffortMap?: Record<string, Record<string, string>>;
  noVisionModels?: string[];
  noReasoningModels?: string[];
  noTemperatureModels?: string[];
  // ... 更多元数据
}
```

---

## 七、集成方案（codex-portable config_server.py）

### 7.1 当前状态

codex-portable 有 22 个 Provider，全部使用 OpenAI Chat Completions 格式：
- 所有 Provider 的 `wire_api = "responses"` 或 `"chat"`
- 通过 `OPENAI_BASE_URL` + `OPENAI_API_KEY` 环境变量传递
- config.toml 使用 `[model_providers.custom]` 配置节

### 7.2 需要新增的 Provider（从 OpenCodex 提取）

#### 第一优先级：高价值 Provider（直接可用 OpenAI 兼容格式）

```python
# 以下 Provider 使用 openai-chat 适配器，codex-portable 可直接支持
NEW_OPENAI_COMPAT_PROVIDERS = [
    {"id": "xai", "name": "xAI (Grok)", "base_url": "https://api.x.ai/v1",
     "models": ["grok-4.5", "grok-4.3", "grok-4.20-0309-reasoning", "grok-4.20-0309-non-reasoning"],
     "key_hint": "xai-...", "note": "Grok 4.5 最新，支持推理"},
    
    {"id": "nvidia", "name": "NVIDIA NIM", "base_url": "https://integrate.api.nvidia.com/v1",
     "models": ["moonshotai/kimi-k2.6", "moonshotai/kimi-k2.5", "moonshotai/kimi-k2-thinking"],
     "key_hint": "nvapi-...", "note": "免费额度，需 API Key", "tags": ["free"]},
    
    {"id": "zai", "name": "Z.AI (GLM Coding)", "base_url": "https://api.z.ai/api/coding/paas/v4",
     "models": ["glm-5.2", "glm-5.2[1m]", "glm-5.1", "glm-5", "glm-4.6"],
     "key_hint": "粘贴 Z.AI API Key", "note": "GLM-5.2 编程订阅", "tags": ["cn"]},
    
    {"id": "venice", "name": "Venice", "base_url": "https://api.venice.ai/api/v1",
     "models": [], "key_hint": "粘贴 Venice API Key", "note": "隐私优先 AI"},
    
    {"id": "opencode-free", "name": "OpenCode Free", "base_url": "https://opencode.ai/zen/v1",
     "models": [], "key_hint": "无需 Key", "note": "免费桌面版，约200次/5小时", "tags": ["free"]},
    
    {"id": "opencode-go", "name": "OpenCode Go", "base_url": "https://opencode.ai/zen/go/v1",
     "models": ["kimi-k2.7-code", "glm-5.2", "deepseek-v4-pro", "qwen3.7-max"],
     "key_hint": "粘贴 OpenCode API Key", "note": "GLM/DeepSeek/Kimi/Qwen/MiMo"},
    
    {"id": "litellm", "name": "LiteLLM (自建)", "base_url": "http://localhost:4000/v1",
     "models": [], "key_hint": "可留空", "note": "自建代理，Key 可选", "tags": ["custom"]},
    
    {"id": "ollama-cloud", "name": "Ollama Cloud", "base_url": "https://ollama.com/v1",
     "models": ["glm-5.2", "deepseek-v4-pro", "qwen3-coder:480b", "gpt-oss:120b"],
     "key_hint": "粘贴 Ollama Cloud Key", "note": "云端 Ollama"},
    
    {"id": "orcarouter", "name": "OrcaRouter", "base_url": "https://api.orcarouter.ai/v1",
     "models": ["openai/gpt-5.5", "anthropic/claude-opus-4.8", "google/gemini-3.5-flash",
                "deepseek/deepseek-v4-pro", "orcarouter/auto"],
     "key_hint": "粘贴 OrcaRouter Key", "note": "自适应路由"},
    
    {"id": "zenmux", "name": "ZenMux", "base_url": "https://zenmux.ai/api/v1",
     "models": ["moonshotai/kimi-k3-free", "moonshotai/kimi-k3"],
     "key_hint": "粘贴 ZenMux Key"},
    
    {"id": "kilo", "name": "Kilo", "base_url": "https://api.kilo.ai/api/gateway",
     "models": [], "key_hint": "粘贴 Kilo API Key"},
    
    {"id": "vercel-ai-gateway", "name": "Vercel AI Gateway", 
     "base_url": "https://ai-gateway.vercel.sh/v1",
     "models": [], "key_hint": "粘贴 Vercel Key"},
    
    {"id": "gitlab-duo", "name": "GitLab Duo",
     "base_url": "https://cloud.gitlab.com/ai/v1/proxy/openai/v1",
     "models": [], "key_hint": "粘贴 GitLab PAT"},
    
    {"id": "cloudflare-workers-ai", "name": "Cloudflare Workers AI",
     "base_url": "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1",
     "models": ["@cf/meta/llama-3.3-70b-instruct-fp8-fast", "@cf/qwen/qwq-32b",
                "@cf/deepseek-ai/deepseek-r1-distill-qwen-32b", "@cf/moonshotai/kimi-k2.7-code",
                "@cf/zai-org/glm-5.2"],
     "key_hint": "粘贴 Cloudflare API Token", "note": "免费额度", "tags": ["free"]},
    
    {"id": "huggingface", "name": "Hugging Face",
     "base_url": "https://router.huggingface.co/v1",
     "models": [], "key_hint": "hf_...", "note": "HF Inference API"},
    
    {"id": "moonshot", "name": "Moonshot (Kimi API)",
     "base_url": "https://api.moonshot.ai/v1",
     "models": ["kimi-k3", "kimi-k2.7-code", "kimi-k2.6", "kimi-k2.5"],
     "key_hint": "粘贴 Moonshot API Key", "note": "Kimi K3 最新", "tags": ["cn"]},
    
    {"id": "kimi-code", "name": "Kimi Coding",
     "base_url": "https://api.kimi.com/coding/v1",
     "models": ["k3", "k3[1m]", "kimi-k2.7-code", "kimi-k2.6", "kimi-k2.5"],
     "key_hint": "粘贴 Kimi API Key", "note": "Kimi 编程版", "tags": ["cn"]},
    
    {"id": "nanogpt", "name": "NanoGPT",
     "base_url": "https://nano-gpt.com/api/v1",
     "models": [], "key_hint": "粘贴 NanoGPT Key"},
    
    {"id": "synthetic", "name": "Synthetic",
     "base_url": "https://api.synthetic.new/openai/v1",
     "models": [], "key_hint": "粘贴 Synthetic Key"},
    
    {"id": "parallel", "name": "Parallel",
     "base_url": "https://platform.parallel.ai",
     "models": [], "key_hint": "粘贴 Parallel Key"},
    
    {"id": "opencode-zen", "name": "OpenCode Zen",
     "base_url": "https://opencode.ai/zen/v1",
     "models": [], "key_hint": "粘贴 OpenCode Key"},
    
    {"id": "github-copilot", "name": "GitHub Copilot",
     "base_url": "https://api.githubcopilot.com",
     "models": ["gpt-4o", "gpt-4.1", "gpt-4.1-mini", "claude-sonnet-4", "gemini-2.5-pro"],
     "key_hint": "GitHub Copilot Token", "note": "实验性非官方桥接"},
]
```

#### 第二优先级：需要特殊适配的 Provider

**Anthropic 格式 Provider**（需要 Anthropic Messages API 代理）：
```python
# 这些需要在 codex-portable 中实现代理转换层
ANTHROPIC_FORMAT_PROVIDERS = [
    {"id": "xiaomi", "base_url": "https://api.xiaomimimo.com/anthropic", "adapter": "anthropic"},
    {"id": "umans", "base_url": "https://api.code.umans.ai", "adapter": "anthropic"},
]
```

**Google Gemini 格式 Provider**：
```python
GOOGLE_FORMAT_PROVIDERS = [
    {"id": "google", "base_url": "https://generativelanguage.googleapis.com", "adapter": "google"},
    {"id": "google-vertex", "base_url": "https://aiplatform.googleapis.com", "adapter": "google-vertex"},
]
```

**MiMo Free**（特殊 JWT 认证）：
```python
MIMO_FREE_PROVIDER = {
    "id": "mimo-free", "base_url": "https://api.xiaomimimo.com/api/free-ai/openai/chat",
    "adapter": "mimo-free", "note": "免费，无需 Key"
}
```

### 7.3 已有 Provider 的模型/配置更新

对比 OpenCodex 注册表，以下已有 Provider 需要更新：

| Provider | 需更新内容 |
|----------|----------|
| OpenAI | 新增 gpt-5.6-sol/terra/luna + pro 变体 |
| Anthropic | 新增 claude-fable-5, claude-opus-4-8, claude-sonnet-5 |
| DeepSeek | 新增 deepseek-v4-pro, deepseek-v4-flash |
| xAI | 新增 grok-4.5, 更新模型列表 |
| Groq | 更新为 llama-4 系列 |
| 智谱 | 新增 glm-5.2 |
| 通义千问 | 新增 qwen3.7-max, qwen3.8-max-preview |
| MiniMax | 新增 MiniMax-M3 |

### 7.4 实现建议

#### 短期（直接集成，无需代理转换）

对于使用 `openai-chat` 适配器的 35+ Provider，codex-portable 只需：
1. 将 Provider 配置添加到 `PROVIDERS` 列表
2. 设置正确的 `base_url`
3. Codex CLI 的 `wire_api = "chat"` 自动处理 Chat Completions 格式

#### 中期（实现 Responses → Chat Completions 代理）

如果需要完整兼容 OpenCodex 的 Responses API 代理模式：
1. 在 codex-portable 中实现一个轻量代理层
2. 接收 Responses API 请求，转换为 Chat Completions 格式
3. 将 Chat Completions 响应转换回 Responses API 格式

核心转换逻辑（Python 伪代码）：
```python
def responses_to_chat_completions(responses_body):
    """将 Responses API 请求转换为 Chat Completions 格式"""
    messages = []
    for item in responses_body["input"]:
        if item["type"] == "message":
            role = item["role"]
            content = extract_text(item["content"])
            messages.append({"role": role, "content": content})
        elif item["type"] == "function_call":
            # 处理工具调用
            pass
        elif item["type"] == "reasoning":
            # 保留推理内容
            pass
    
    return {
        "model": responses_body["model"],
        "messages": messages,
        "stream": responses_body.get("stream", False),
        "tools": convert_tools(responses_body.get("tools", [])),
    }
```

#### 长期（完整适配器系统）

实现类似 OpenCodex 的适配器模式，支持：
- Anthropic Messages API（用于 Xiaomi MiMo、Umans）
- Google Gemini API（用于 Google Gemini、Vertex AI）
- 特殊认证流程（MiMo Free JWT、GitHub Copilot）

---

## 八、关键差异对比

| 特性 | OpenCodex | codex-portable |
|------|-----------|---------------|
| 输入协议 | Responses API | Responses API (通过 Codex CLI) |
| 适配器数量 | 8 种 | 1 种 (OpenAI 兼容) |
| Provider 数量 | 55 | 22 |
| 认证方式 | forward/oauth/key/local | key (OPENAI_API_KEY) |
| 代理转换 | 完整（Responses ↔ Chat/Anthropic/Gemini） | 无（直通 OpenAI 兼容） |
| 推理控制 | reasoning_effort/thinking_budget/thinking_toggle | 无 |
| 流式处理 | 完整 SSE 解析 + 工具调用缓冲 | Codex CLI 内置 |
| Prompt Caching | Anthropic 原生支持 | 无 |

---

## 九、OpenCodex 的 Provider 配置字段说明

| 字段 | 类型 | 说明 | codex-portable 对应 |
|------|------|------|-------------------|
| id | string | 唯一标识 | id |
| label | string | 显示名称 | name |
| adapter | string | 适配器类型 | 无（全部 openai-chat） |
| baseUrl | string | API 基础 URL | base_url |
| authKind | "forward"\|"oauth"\|"key"\|"local" | 认证方式 | 无（全部 key） |
| models | string[] | 静态模型列表 | models |
| defaultModel | string | 默认模型 | 无 |
| liveModels | boolean | 是否动态发现模型 | 无 |
| modelContextWindows | Record<string, number> | 每模型上下文窗口 | 无 |
| modelReasoningEfforts | Record<string, string[]> | 每模型推理等级 | 无 |
| modelReasoningEffortMap | Record<string, Record<string, string>> | 推理等级映射 | 无 |
| noVisionModels | string[] | 不支持视觉的模型 | 无 |
| noReasoningModels | string[] | 不支持推理的模型 | 无 |
| noTemperatureModels | string[] | 不支持温度的模型 | 无 |
| parallelToolCalls | boolean | 是否支持并行工具调用 | 无 |
| modelSuffixBracketStrip | boolean | 去除模型 ID 中的 [suffix] | 无 |
| keyOptional | boolean | API Key 是否可选 | 无 |
| freeTier | boolean | 是否免费 | 无 |
| allowBaseUrlOverride | boolean | 是否允许自定义 URL | 无 |
| preserveReasoningContentModels | string[] | 需保留推理内容的模型 | 无 |
| thinkingToggleModels | string[] | 使用 thinking toggle 的模型 | 无 |
| thinkingBudgetModels | string[] | 使用 thinking budget 的模型 | 无 |

---

## 十、总结

### 可直接集成的（无需代理转换）
- **35+ 个 openai-chat Provider** → 直接添加到 codex-portable 的 PROVIDERS 列表
- 更新现有 Provider 的模型列表

### 需要代理转换层的
- **3 个 anthropic Provider** (xiaomi, umans, cloudflare-ai-gateway)
- **3 个 google Provider** (google, google-vertex, google-antigravity)
- **1 个 mimo-free Provider** (特殊 JWT 认证)
- **1 个 kiro Provider** (专有协议)
- **1 个 cursor Provider** (专有协议)
- **1 个 azure-openai Provider** (Responses API 变体)

### 建议优先级
1. **立即**: 添加 35+ 个 OpenAI 兼容 Provider 到 config_server.py
2. **短期**: 更新现有 Provider 的模型列表
3. **中期**: 实现代理转换层支持 Anthropic/Google 格式
4. **长期**: 实现完整适配器系统
