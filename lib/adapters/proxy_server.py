"""
Responses API Proxy Server
Converts Codex Responses API requests to Chat Completions API.
Based on OpenCodex's bridge.ts logic.
"""

import json
import os
import sys
import time
import uuid
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict, List, Optional

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.adapters import (
    messages_to_chat_format,
    tools_to_chat_format,
    parse_stream_line,
    build_request_body,
)


class ResponsesProxyHandler(BaseHTTPRequestHandler):
    """Handle Responses API requests and proxy to Chat Completions API."""
    
    timeout = 300  # 5 minute timeout for long-running requests
    
    def do_POST(self):
        if self.path == "/v1/responses":
            self._handle_responses()
        else:
            self.send_error(404, "Not Found")
    
    def do_GET(self):
        if self.path == "/v1/models":
            self._handle_models()
        elif self.path == "/health":
            self._json_response({"status": "ok"})
        else:
            self.send_error(404, "Not Found")
    
    def _handle_responses(self):
        """Convert Responses API request to Chat Completions and proxy."""
        try:
            # Read request body
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            request = json.loads(body)
            
            # Extract provider config from environment
            provider_base_url = os.environ.get("PROVIDER_BASE_URL", "")
            provider_api_key = os.environ.get("PROVIDER_API_KEY", "")
            provider_model = os.environ.get("PROVIDER_MODEL", "")
            
            if not provider_base_url or not provider_api_key:
                self._json_response(
                    {"error": "Provider not configured. Set PROVIDER_BASE_URL and PROVIDER_API_KEY."},
                    status=500,
                )
                return
            
            # Parse Responses API request
            model = request.get("model", provider_model)
            input_messages = request.get("input", [])
            system_prompt = request.get("instructions", "")
            tools = request.get("tools", [])
            tool_choice = request.get("tool_choice")
            max_tokens = request.get("max_output_tokens") or request.get("max_tokens")
            temperature = request.get("temperature")
            stream = request.get("stream", True)
            reasoning = request.get("reasoning", {})
            
            # Convert system prompt
            system_parts = [system_prompt] if system_prompt else []
            
            # Convert messages
            chat_messages = messages_to_chat_format(
                input_messages,
                system_prompt=system_parts,
                tools=tools,
            )
            
            # Convert tools
            chat_tools = tools_to_chat_format(tools, tool_choice)
            
            # Build request body
            chat_body = build_request_body(
                model=model,
                messages=chat_messages,
                tools=chat_tools,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=stream,
                reasoning_effort=reasoning.get("effort"),
            )
            
            # Proxy to upstream
            upstream_url = f"{provider_base_url.rstrip('/')}/chat/completions"
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {provider_api_key}",
            }
            
            req = urllib.request.Request(
                upstream_url,
                data=json.dumps(chat_body).encode(),
                headers=headers,
                method="POST",
            )
            
            if stream:
                self._proxy_stream(req, model)
            else:
                self._proxy_non_stream(req, model)
        
        except Exception as e:
            self._json_response(
                {"error": {"message": str(e), "type": "proxy_error"}},
                status=500,
            )
    
    def _proxy_stream(self, req: urllib.request.Request, model: str):
        """Proxy streaming response, converting Chat Completions SSE to Responses SSE."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        
        response_id = f"resp_{uuid.uuid4().hex[:24]}"
        output_index = 0
        content_index = 0
        tool_call_buffers = {}  # index -> {id, name, arguments}
        
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                buffer = ""
                for chunk in iter(lambda: resp.read(4096), b""):
                    buffer += chunk.decode("utf-8", errors="replace")
                    
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        
                        if not line:
                            continue
                        
                        parsed = parse_stream_line(line, model)
                        if not parsed:
                            continue
                        
                        if parsed["type"] == "done":
                            # Send final response.completed event
                            self._send_sse("response.completed", {
                                "id": response_id,
                                "object": "response",
                                "status": "completed",
                            })
                            continue
                        
                        if parsed["type"] == "usage":
                            # Send usage event
                            self._send_sse("response.usage", {
                                "response_id": response_id,
                                "usage": parsed["usage"],
                            })
                            continue
                        
                        # Text delta
                        if "text" in parsed:
                            self._send_sse("response.output_text.delta", {
                                "response_id": response_id,
                                "output_index": output_index,
                                "content_index": content_index,
                                "delta": parsed["text"],
                            })
                        
                        # Reasoning delta
                        if "reasoning" in parsed:
                            self._send_sse("response.reasoning_text.delta", {
                                "response_id": response_id,
                                "output_index": output_index,
                                "content_index": content_index,
                                "delta": parsed["reasoning"],
                            })
                        
                        # Tool calls
                        if "tool_calls" in parsed:
                            for tc in parsed["tool_calls"]:
                                idx = tc["index"]
                                if idx not in tool_call_buffers:
                                    tool_call_buffers[idx] = {
                                        "id": tc.get("id") or f"call_{uuid.uuid4().hex[:24]}",
                                        "name": tc.get("name", ""),
                                        "arguments": "",
                                    }
                                    # Send tool call start
                                    self._send_sse("response.function_call.start", {
                                        "response_id": response_id,
                                        "output_index": output_index,
                                        "call_id": tool_call_buffers[idx]["id"],
                                        "name": tool_call_buffers[idx]["name"],
                                    })
                                
                                if tc.get("arguments"):
                                    tool_call_buffers[idx]["arguments"] += tc["arguments"]
                                    # Send tool call arguments delta
                                    self._send_sse("response.function_call.arguments.delta", {
                                        "response_id": response_id,
                                        "output_index": output_index,
                                        "call_id": tool_call_buffers[idx]["id"],
                                        "delta": tc["arguments"],
                                    })
                        
                        # Finish reason
                        if "finish_reason" in parsed:
                            # Send tool call done events
                            for idx, buf in tool_call_buffers.items():
                                self._send_sse("response.function_call.done", {
                                    "response_id": response_id,
                                    "output_index": output_index,
                                    "call_id": buf["id"],
                                    "name": buf["name"],
                                    "arguments": buf["arguments"],
                                })
                            tool_call_buffers.clear()
                            
                            # Send output item done
                            self._send_sse("response.output_item.done", {
                                "response_id": response_id,
                                "output_index": output_index,
                            })
                            output_index += 1
        
        except Exception as e:
            self._send_sse("error", {"message": str(e)})
    
    def _proxy_non_stream(self, req: urllib.request.Request, model: str):
        """Proxy non-streaming response."""
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read())
            
            # Convert Chat Completions response to Responses format
            choices = data.get("choices", [])
            if not choices:
                self._json_response({"error": "No choices in response"}, status=500)
                return
            
            choice = choices[0]
            message = choice.get("message", {})
            
            response_id = f"resp_{uuid.uuid4().hex[:24]}"
            
            output = []
            
            # Text content
            if message.get("content"):
                output.append({
                    "type": "message",
                    "id": f"msg_{uuid.uuid4().hex[:24]}",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": message["content"]}],
                })
            
            # Tool calls
            if message.get("tool_calls"):
                for tc in message["tool_calls"]:
                    output.append({
                        "type": "function_call",
                        "id": f"msg_{uuid.uuid4().hex[:24]}",
                        "call_id": tc.get("id", f"call_{uuid.uuid4().hex[:24]}"),
                        "name": tc["function"]["name"],
                        "arguments": tc["function"]["arguments"],
                    })
            
            # Usage
            usage = data.get("usage", {})
            
            response = {
                "id": response_id,
                "object": "response",
                "status": "completed",
                "model": model,
                "output": output,
                "usage": {
                    "input_tokens": usage.get("prompt_tokens", 0),
                    "output_tokens": usage.get("completion_tokens", 0),
                },
            }
            
            self._json_response(response)
        
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            self._json_response(
                {"error": {"message": f"Upstream error: {error_body}", "type": "upstream_error"}},
                status=e.code,
            )
    
    def _handle_models(self):
        """Return available models."""
        model = os.environ.get("PROVIDER_MODEL", "gpt-5.5")
        self._json_response({
            "object": "list",
            "data": [{"id": model, "object": "model", "owned_by": "proxy"}],
        })
    
    def _send_sse(self, event: str, data: Dict[str, Any]):
        """Send a Server-Sent Event."""
        try:
            self.wfile.write(f"event: {event}\n".encode())
            self.wfile.write(f"data: {json.dumps(data)}\n\n".encode())
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
    
    def _json_response(self, data: Dict[str, Any], status: int = 200):
        """Send JSON response."""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def log_message(self, format, *args):
        """Suppress default logging."""
        pass


def start_proxy(
    port: int = 18900,
    base_url: str = "",
    api_key: str = "",
    model: str = "",
):
    """Start the Responses API proxy server."""
    os.environ["PROVIDER_BASE_URL"] = base_url
    os.environ["PROVIDER_API_KEY"] = api_key
    os.environ["PROVIDER_MODEL"] = model
    
    server = HTTPServer(("127.0.0.1", port), ResponsesProxyHandler)
    print(f"  Responses API Proxy listening on http://127.0.0.1:{port}")
    print(f"  Upstream: {base_url}")
    print(f"  Model: {model}")
    server.serve_forever()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Responses API Proxy")
    parser.add_argument("--port", type=int, default=18900)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--model", default="")
    
    args = parser.parse_args()
    start_proxy(args.port, args.base_url, args.api_key, args.model)
