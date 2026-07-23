"""
OpenAI Chat Completions Adapter
Converts Responses API format to Chat Completions API format.
Based on OpenCodex's openai-chat adapter.
"""

import json
from typing import Any, Dict, List, Optional, Union


def messages_to_chat_format(
    messages: List[Dict[str, Any]],
    system_prompt: Optional[List[str]] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Convert Responses API messages to Chat Completions format.
    
    Responses API roles:
      - user → user
      - developer → system
      - assistant → assistant (with tool_calls)
      - toolResult → tool (with tool_call_id)
    """
    out = []
    pending_tool_calls = []
    
    # Add system prompt
    if system_prompt:
        system_text = "\n\n".join(system_prompt)
        out.append({"role": "system", "content": system_text})
    
    for msg in messages:
        role = msg.get("role")
        
        if role in ("user", "developer"):
            # Convert developer → system
            chat_role = "system" if role == "developer" else "user"
            content = msg.get("content", "")
            
            # Handle content parts (text + images)
            if isinstance(content, list):
                parts = []
                for part in content:
                    if part.get("type") == "text":
                        parts.append({"type": "text", "text": part.get("text", "")})
                    elif part.get("type") == "image":
                        parts.append({
                            "type": "image_url",
                            "image_url": {
                                "url": part.get("imageUrl", ""),
                                **({"detail": part["detail"]} if "detail" in part else {}),
                            }
                        })
                out.append({"role": chat_role, "content": parts})
            else:
                out.append({"role": chat_role, "content": content})
        
        elif role == "assistant":
            text_parts = []
            thinking_parts = []
            tool_calls = []
            
            for part in msg.get("content", []):
                ptype = part.get("type")
                if ptype == "text":
                    text_parts.append(part.get("text", ""))
                elif ptype == "thinking":
                    thinking_parts.append(part.get("thinking", ""))
                elif ptype == "toolCall":
                    tool_calls.append(part)
            
            chat_msg = {"role": "assistant"}
            
            if text_parts:
                chat_msg["content"] = "".join(text_parts)
            
            # Add reasoning_content for supported models
            reasoning_content = "".join(thinking_parts)
            if reasoning_content:
                chat_msg["reasoning_content"] = reasoning_content
            
            # Skip empty assistant messages
            if not chat_msg.get("content") and not tool_calls and not chat_msg.get("reasoning_content"):
                continue
            
            # Flush pending tool calls
            _flush_pending_tool_calls(out, pending_tool_calls)
            
            # Convert tool calls
            if tool_calls:
                wire_tool_calls = []
                for tc in tool_calls:
                    tc_id = tc.get("id") or f"call_minted_{len(out)}"
                    name = tc.get("name", "unknown")
                    namespace = tc.get("namespace")
                    if namespace:
                        name = f"{namespace}__{name}"
                    wire_tool_calls.append({
                        "id": tc_id,
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": json.dumps(tc.get("arguments", {})),
                        },
                    })
                    pending_tool_calls.append({"id": tc_id, "name": name})
                
                chat_msg["tool_calls"] = wire_tool_calls
                if not chat_msg.get("content"):
                    chat_msg["content"] = ""
            
            out.append(chat_msg)
        
        elif role == "toolResult":
            tool_call_id = msg.get("toolCallId")
            content = msg.get("content", "")
            
            if isinstance(content, list):
                content = _content_parts_to_text(content)
            
            # Find matching pending tool call
            match_idx = -1
            if tool_call_id:
                for i, tc in enumerate(pending_tool_calls):
                    if tc["id"] == tool_call_id:
                        match_idx = i
                        break
            
            if match_idx >= 0 and tool_call_id:
                # Real result matched
                out.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": content,
                })
                pending_tool_calls.pop(match_idx)
            else:
                # Orphan tool result - synthesize assistant + tool pair
                _flush_pending_tool_calls(out, pending_tool_calls)
                if not tool_call_id:
                    tool_call_id = f"call_orphan_{len(out)}"
                name = msg.get("toolName", "tool_result")
                out.append({
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": tool_call_id,
                        "type": "function",
                        "function": {"name": name, "arguments": "{}"},
                    }],
                })
                out.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": content,
                })
    
    # Flush any remaining pending tool calls
    _flush_pending_tool_calls(out, pending_tool_calls)
    
    return out


def _flush_pending_tool_calls(out: List[Dict], pending: List[Dict]):
    """Close unresolved tool rounds with synthetic unavailable-result messages."""
    if not pending:
        return
    for call in pending:
        out.append({
            "role": "tool",
            "tool_call_id": call["id"],
            "content": f'[ocx] no tool result was recorded for "{call["name"]}"; execution status unknown.',
        })
    pending.clear()


def _content_parts_to_text(parts: List[Dict[str, Any]]) -> str:
    """Convert content parts to plain text."""
    texts = []
    for part in parts:
        if part.get("type") == "text":
            texts.append(part.get("text", ""))
    return "".join(texts)


def tools_to_chat_format(
    tools: List[Dict[str, Any]],
    tool_choice: Optional[Dict[str, Any]] = None,
) -> Optional[List[Dict[str, Any]]]:
    """
    Convert Responses API tools to Chat Completions function calling format.
    """
    if not tools:
        return None
    
    result = []
    for tool in tools:
        name = tool.get("name", "unknown")
        namespace = tool.get("namespace")
        if namespace:
            name = f"{namespace}__{name}"
        
        parameters = tool.get("parameters", {})
        
        result.append({
            "type": "function",
            "function": {
                "name": name,
                "description": tool.get("description", ""),
                "parameters": parameters,
            },
        })
    
    return result


def parse_stream_line(line: str, model_id: str = "") -> Optional[Dict[str, Any]]:
    """
    Parse a single SSE line from Chat Completions stream.
    Returns None for [DONE] or empty lines.
    """
    if not line or line.strip() == "":
        return None
    
    if line.strip() == "data: [DONE]":
        return {"type": "done"}
    
    if not line.startswith("data: "):
        return None
    
    data_str = line[6:]  # Remove "data: " prefix
    
    try:
        data = json.loads(data_str)
    except json.JSONDecodeError:
        return None
    
    choices = data.get("choices", [])
    if not choices:
        # Usage-only chunk
        usage = data.get("usage")
        if usage:
            return {
                "type": "usage",
                "usage": {
                    "input_tokens": usage.get("prompt_tokens", 0),
                    "output_tokens": usage.get("completion_tokens", 0),
                },
            }
        return None
    
    choice = choices[0]
    delta = choice.get("delta", {})
    finish_reason = choice.get("finish_reason")
    
    result = {"type": "delta"}
    
    # Text content
    if "content" in delta and delta["content"]:
        result["text"] = delta["content"]
    
    # Reasoning content
    if "reasoning_content" in delta and delta["reasoning_content"]:
        result["reasoning"] = delta["reasoning_content"]
    
    # Tool calls
    if "tool_calls" in delta:
        tool_calls = []
        for tc in delta["tool_calls"]:
            tool_call = {
                "index": tc.get("index", 0),
                "id": tc.get("id"),
                "name": tc.get("function", {}).get("name"),
                "arguments": tc.get("function", {}).get("arguments", ""),
            }
            tool_calls.append(tool_call)
        result["tool_calls"] = tool_calls
    
    # Finish reason
    if finish_reason:
        result["finish_reason"] = finish_reason
    
    # Usage
    usage = data.get("usage")
    if usage:
        result["usage"] = {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        }
    
    return result


def build_request_body(
    model: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[Dict[str, Any]] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    stream: bool = True,
    reasoning_effort: Optional[str] = None,
    thinking_budget: Optional[int] = None,
    thinking_enabled: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Build Chat Completions request body.
    """
    body = {
        "model": model,
        "messages": messages,
        "stream": stream,
    }
    
    if tools:
        body["tools"] = tools
    if tool_choice:
        body["tool_choice"] = tool_choice
    if max_tokens:
        body["max_tokens"] = max_tokens
    if temperature is not None:
        body["temperature"] = temperature
    
    # Reasoning control
    if thinking_budget is not None:
        body["thinking_budget"] = thinking_budget
    elif thinking_enabled is not None:
        body["thinking"] = {"type": "enabled" if thinking_enabled else "disabled"}
    elif reasoning_effort:
        body["reasoning_effort"] = reasoning_effort
    
    return body
