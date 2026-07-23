"""
Google Gemini API Adapter
Converts Responses API format to Google Gemini generateContent API format.
Based on OpenCodex's google adapter.
"""

import json
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple


def messages_to_gemini_format(
    messages: List[Dict[str, Any]],
    system_prompt: Optional[List[str]] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Convert Responses API messages to Gemini format.
    Returns (system_instruction, contents).
    """
    system_instruction = None
    contents = []
    
    # Convert system prompt
    if system_prompt:
        system_text = "\n\n".join(system_prompt)
        system_instruction = {"parts": [{"text": system_text}]}
    
    for msg in messages:
        role = msg.get("role")
        
        if role in ("user", "developer"):
            content = msg.get("content", "")
            parts = []
            
            if isinstance(content, list):
                for part in content:
                    if part.get("type") == "text":
                        parts.append({"text": part.get("text", "")})
                    elif part.get("type") == "image":
                        image_url = part.get("imageUrl", "")
                        if image_url.startswith("data:"):
                            media_type, base64_data = _parse_data_url(image_url)
                            parts.append({
                                "inline_data": {
                                    "mime_type": media_type,
                                    "data": base64_data,
                                },
                            })
                        else:
                            # Remote URL - use file_data if possible
                            parts.append({"file_data": {"file_uri": image_url}})
            else:
                parts.append({"text": content})
            
            contents.append({"role": "user", "parts": parts})
        
        elif role == "assistant":
            text_parts = []
            tool_calls = []
            
            for part in msg.get("content", []):
                ptype = part.get("type")
                if ptype == "text":
                    text_parts.append(part.get("text", ""))
                elif ptype == "toolCall":
                    tool_calls.append(part)
            
            parts = []
            
            if text_parts:
                parts.append({"text": "".join(text_parts)})
            
            for tc in tool_calls:
                name = tc.get("name", "unknown")
                namespace = tc.get("namespace")
                if namespace:
                    name = f"{namespace}__{name}"
                parts.append({
                    "functionCall": {
                        "name": name,
                        "args": tc.get("arguments", {}),
                    },
                })
            
            if parts:
                contents.append({"role": "model", "parts": parts})
        
        elif role == "toolResult":
            tool_call_id = msg.get("toolCallId", "")
            content = msg.get("content", "")
            tool_name = msg.get("toolName", "unknown")
            
            if isinstance(content, list):
                text = _content_parts_to_text(content)
            else:
                text = content or "(empty tool output)"
            
            parts = [{"text": text}]
            
            # Add inline images from tool results
            if isinstance(content, list):
                for part in content:
                    if part.get("type") == "image":
                        image_url = part.get("imageUrl", "")
                        if image_url.startswith("data:"):
                            media_type, base64_data = _parse_data_url(image_url)
                            parts.append({
                                "inline_data": {
                                    "mime_type": media_type,
                                    "data": base64_data,
                                },
                            })
            
            contents.append({
                "role": "user",
                "parts": [{
                    "functionResponse": {
                        "name": tool_name,
                        "response": {"result": text},
                    },
                }],
            })
    
    return system_instruction, contents


def tools_to_gemini_format(
    tools: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Convert tools to Gemini function declarations format."""
    result = []
    for tool in tools:
        name = tool.get("name", "unknown")
        namespace = tool.get("namespace")
        if namespace:
            name = f"{namespace}__{name}"
        
        parameters = tool.get("parameters", {})
        
        result.append({
            "functionDeclarations": [{
                "name": name,
                "description": tool.get("description", ""),
                "parameters": _sanitize_gemini_parameters(parameters),
            }],
        })
    
    return result


def build_gemini_request(
    model: str,
    contents: List[Dict[str, Any]],
    system_instruction: Optional[Dict[str, Any]] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    stream: bool = True,
    reasoning_effort: Optional[str] = None,
) -> Dict[str, Any]:
    """Build Gemini generateContent request body."""
    body = {
        "contents": contents,
        "generationConfig": {},
    }
    
    if system_instruction:
        body["systemInstruction"] = system_instruction
    if tools:
        body["tools"] = tools
    if max_tokens:
        body["generationConfig"]["maxOutputTokens"] = max_tokens
    if temperature is not None:
        body["generationConfig"]["temperature"] = temperature
    
    # Add thinking configuration
    if reasoning_effort:
        body["generationConfig"]["thinkingConfig"] = {
            "thinkingBudget": _reasoning_budget(reasoning_effort),
        }
    
    return body


def _reasoning_budget(effort: str) -> int:
    """Map reasoning effort to Gemini thinking budget."""
    budgets = {
        "minimal": 1024,
        "low": 4096,
        "medium": 8192,
        "high": 16384,
        "xhigh": 24576,
        "max": 32000,
    }
    return budgets.get(effort, 8192)


def _sanitize_gemini_parameters(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize tool parameters for Gemini."""
    if not parameters or not isinstance(parameters, dict):
        return {"type": "object", "properties": {}}
    
    result = {}
    for key, value in parameters.items():
        if key == "encrypted":
            continue
        if key == "required" and isinstance(value, list) and len(value) == 0:
            continue
        result[key] = value
    
    if "type" not in result:
        result["type"] = "object"
    
    return result


def _parse_data_url(data_url: str) -> Tuple[str, str]:
    """Parse a data URL into media_type and base64 data."""
    match = re.match(r"data:([^;]+);base64,(.+)", data_url)
    if match:
        return match.group(1), match.group(2)
    return "image/png", ""


def _content_parts_to_text(parts: List[Dict[str, Any]]) -> str:
    """Convert content parts to plain text."""
    texts = []
    for part in parts:
        if part.get("type") == "text":
            texts.append(part.get("text", ""))
    return "".join(texts)
