"""
Anthropic Messages API Adapter
Converts Responses API format to Anthropic Messages API format.
Based on OpenCodex's anthropic adapter.
"""

import json
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple


# Anthropic thinking model families that use adaptive thinking
ADAPTIVE_THINKING_MINIMUMS = {
    "sonnet": (5, 0),
    "opus": (4, 7),
    "fable": (0, 0),
}

DEFAULT_MAX_TOKENS = 8192
REASONING_MAX_TOKENS_CEILING = 32000
MIN_THINKING_BUDGET = 1024
OUTPUT_HEADROOM = 8192
OUTPUT_FLOOR = 4096


def uses_adaptive_thinking(model_id: str) -> bool:
    """Check if a Claude model uses adaptive thinking."""
    match = re.match(r"claude-([a-z]+)-(\d+)(?:-(\d{1,2}))?(?!\d)", model_id)
    if not match:
        return False
    family = match.group(1)
    major = int(match.group(2))
    minor = int(match.group(3)) if match.group(3) else 0
    minimum = ADAPTIVE_THINKING_MINIMUMS.get(family)
    if not minimum:
        return False
    return major > minimum[0] or (major == minimum[0] and minor >= minimum[1])


def reasoning_budget(effort: str) -> int:
    """Map reasoning effort to Anthropic thinking budget tokens."""
    budgets = {
        "minimal": 1024,
        "low": 4096,
        "medium": 8192,
        "high": 16384,
        "xhigh": 24576,
        "max": 32000,
    }
    return budgets.get(effort, 8192)


def adaptive_effort(effort: str) -> str:
    """Map effort for adaptive thinking."""
    return "low" if effort == "minimal" else effort


def messages_to_anthropic_format(
    messages: List[Dict[str, Any]],
    system_prompt: Optional[List[str]] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Convert Responses API messages to Anthropic Messages format.
    Returns (messages, system_blocks).
    """
    out = []
    system_blocks = []
    
    # Convert system prompt
    if system_prompt:
        system_text = "\n\n".join(system_prompt)
        system_blocks.append({"type": "text", "text": system_text})
    
    for msg in messages:
        role = msg.get("role")
        
        if role in ("user", "developer"):
            content = msg.get("content", "")
            
            if isinstance(content, list):
                parts = []
                for part in content:
                    if part.get("type") == "text":
                        parts.append({"type": "text", "text": part.get("text", "")})
                    elif part.get("type") == "image":
                        image_url = part.get("imageUrl", "")
                        # Handle data URLs
                        if image_url.startswith("data:"):
                            media_type, base64_data = _parse_data_url(image_url)
                            parts.append({
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": base64_data,
                                },
                            })
                        else:
                            parts.append({
                                "type": "image",
                                "source": {"type": "url", "url": image_url},
                            })
                out.append({"role": "user", "content": parts})
            else:
                out.append({"role": "user", "content": content})
        
        elif role == "assistant":
            text_parts = []
            thinking_parts = []
            tool_calls = []
            
            for part in msg.get("content", []):
                ptype = part.get("type")
                if ptype == "text":
                    text_parts.append(part.get("text", ""))
                elif ptype == "thinking":
                    thinking_parts.append({
                        "type": "thinking",
                        "thinking": part.get("thinking", ""),
                        **({"signature": part["signature"]} if "signature" in part else {}),
                    })
                elif ptype == "toolCall":
                    tool_calls.append(part)
            
            content_blocks = []
            
            # Add thinking blocks
            for thinking in thinking_parts:
                content_blocks.append(thinking)
            
            # Add text blocks
            if text_parts:
                content_blocks.append({"type": "text", "text": "".join(text_parts)})
            
            # Add tool use blocks
            for tc in tool_calls:
                tc_id = tc.get("id") or f"toolu_{uuid.uuid4().hex[:24]}"
                name = tc.get("name", "unknown")
                namespace = tc.get("namespace")
                if namespace:
                    name = f"{namespace}__{name}"
                content_blocks.append({
                    "type": "tool_use",
                    "id": tc_id,
                    "name": name,
                    "input": tc.get("arguments", {}),
                })
            
            # Skip empty assistant messages
            if not content_blocks:
                continue
            
            out.append({"role": "assistant", "content": content_blocks})
        
        elif role == "toolResult":
            tool_call_id = msg.get("toolCallId", "")
            content = msg.get("content", "")
            
            if isinstance(content, list):
                # Convert content parts
                parts = []
                for part in content:
                    if part.get("type") == "text":
                        text = part.get("text", "")
                        if text:
                            parts.append({"type": "text", "text": text})
                    elif part.get("type") == "image":
                        image_url = part.get("imageUrl", "")
                        if image_url.startswith("data:"):
                            media_type, base64_data = _parse_data_url(image_url)
                            parts.append({
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": base64_data,
                                },
                            })
                content = parts if parts else "(empty tool output)"
            else:
                content = content or "(empty tool output)"
            
            out.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": tool_call_id,
                    "content": content,
                }],
            })
    
    return out, system_blocks


def tools_to_anthropic_format(
    tools: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Convert tools to Anthropic format."""
    result = []
    for tool in tools:
        name = tool.get("name", "unknown")
        namespace = tool.get("namespace")
        if namespace:
            name = f"{namespace}__{name}"
        
        result.append({
            "name": name,
            "description": tool.get("description", ""),
            "input_schema": tool.get("parameters", {"type": "object", "properties": {}}),
        })
    
    return result


def build_anthropic_request(
    model: str,
    messages: List[Dict[str, Any]],
    system_blocks: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    stream: bool = True,
    reasoning_effort: Optional[str] = None,
) -> Dict[str, Any]:
    """Build Anthropic Messages API request body."""
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens or DEFAULT_MAX_TOKENS,
        "stream": stream,
    }
    
    if system_blocks:
        body["system"] = system_blocks
    if tools:
        body["tools"] = tools
    if temperature is not None:
        body["temperature"] = temperature
    
    # Add thinking configuration
    if reasoning_effort:
        budget = reasoning_budget(reasoning_effort)
        if uses_adaptive_thinking(model):
            body["thinking"] = {
                "type": "adaptive",
                "budget_tokens": budget,
            }
            body["max_tokens"] = max(
                body["max_tokens"],
                budget + OUTPUT_HEADROOM,
            )
        else:
            body["thinking"] = {
                "type": "enabled",
                "budget_tokens": budget,
            }
            body["max_tokens"] = max(
                body["max_tokens"],
                budget + OUTPUT_HEADROOM,
            )
    
    return body


def parse_anthropic_stream_line(line: str) -> Optional[Dict[str, Any]]:
    """Parse a single SSE line from Anthropic stream."""
    if not line or line.strip() == "":
        return None
    
    if not line.startswith("data: "):
        return None
    
    data_str = line[6:]
    
    try:
        data = json.loads(data_str)
    except json.JSONDecodeError:
        return None
    
    event_type = data.get("type")
    
    if event_type == "message_start":
        message = data.get("message", {})
        return {
            "type": "message_start",
            "id": message.get("id"),
            "model": message.get("model"),
            "usage": _parse_anthropic_usage(message.get("usage")),
        }
    
    elif event_type == "content_block_start":
        block = data.get("content_block", {})
        return {
            "type": "content_block_start",
            "index": data.get("index", 0),
            "block_type": block.get("type"),
            "tool_use_id": block.get("id"),
            "tool_name": block.get("name"),
        }
    
    elif event_type == "content_block_delta":
        delta = data.get("delta", {})
        delta_type = delta.get("type")
        
        if delta_type == "text_delta":
            return {
                "type": "text_delta",
                "index": data.get("index", 0),
                "text": delta.get("text", ""),
            }
        elif delta_type == "thinking_delta":
            return {
                "type": "thinking_delta",
                "index": data.get("index", 0),
                "thinking": delta.get("thinking", ""),
            }
        elif delta_type == "input_json_delta":
            return {
                "type": "input_json_delta",
                "index": data.get("index", 0),
                "json": delta.get("partial_json", ""),
            }
    
    elif event_type == "content_block_stop":
        return {
            "type": "content_block_stop",
            "index": data.get("index", 0),
        }
    
    elif event_type == "message_delta":
        delta = data.get("delta", {})
        return {
            "type": "message_delta",
            "stop_reason": delta.get("stop_reason"),
            "usage": _parse_anthropic_usage(data.get("usage")),
        }
    
    elif event_type == "message_stop":
        return {"type": "message_stop"}
    
    elif event_type == "ping":
        return {"type": "ping"}
    
    return None


def _parse_anthropic_usage(usage: Optional[Dict[str, int]]) -> Optional[Dict[str, int]]:
    """Parse Anthropic usage format."""
    if not usage:
        return None
    return {
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "cache_read_input_tokens": usage.get("cache_read_input_tokens", 0),
        "cache_creation_input_tokens": usage.get("cache_creation_input_tokens", 0),
    }


def _parse_data_url(data_url: str) -> Tuple[str, str]:
    """Parse a data URL into media_type and base64 data."""
    # data:image/png;base64,iVBOR...
    match = re.match(r"data:([^;]+);base64,(.+)", data_url)
    if match:
        return match.group(1), match.group(2)
    return "image/png", ""
