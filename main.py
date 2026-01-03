"""
Talos MCP Connector - FastAPI Application
Bridge between MCP Protocol and Talos secure messaging.
"""

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
import time
import os

app = FastAPI(
    title="Talos MCP Connector",
    description="MCP Protocol bridge for Talos secure messaging",
    version="0.1.0",
)


class MCPRequest(BaseModel):
    """MCP request envelope."""

    method: str
    params: Optional[dict] = None
    id: Optional[str] = None


class MCPResponse(BaseModel):
    """MCP response envelope."""

    result: Optional[dict] = None
    error: Optional[dict] = None
    id: Optional[str] = None


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "mcp-connector",
        "timestamp": time.time(),
    }


@app.get("/api/mcp/status")
def mcp_status():
    """MCP connector status for integration tests."""
    return {
        "status": "healthy",
        "version": "0.1.0",
        "env": os.getenv("TALOS_ENV", "production"),
        "run_id": os.getenv("TALOS_RUN_ID", "default"),
        "supported_methods": ["tools/list", "tools/call", "resources/list"],
    }


@app.post("/api/mcp/invoke")
def invoke_mcp(request: MCPRequest):
    """Invoke an MCP method through Talos secure channel."""

    if request.method == "tools/call":
        tool_name = request.params.get("name")
        args = request.params.get("arguments", {})

        if tool_name == "chat":
            import json
            import requests
            import jsonschema
            from pathlib import Path

            # Load Schema (Contract-First)
            # Assuming repo structure: deploy/repos/talos-mcp-connector/main.py -> ../talos-contracts/schemas/mcp/chat_tool.schema.json
            # Relative path: ../talos-contracts/schemas/mcp/chat_tool.schema.json
            schema_path = (
                Path(__file__).parent.parent / "talos-contracts/schemas/mcp/chat_tool.schema.json"
            )

            try:
                if not schema_path.exists():
                    # Fallback during dev if paths differ, but fail safe
                    raise FileNotFoundError(f"Schema not found at {schema_path}")

                with open(schema_path) as f:
                    schema = json.load(f)

                jsonschema.validate(instance=args, schema=schema)

            except jsonschema.ValidationError as e:
                return MCPResponse(
                    error={
                        "code": "TALOS_CHAT_SCHEMA_INVALID",
                        "message": f"Schema validation failed: {e.message}",
                    },
                    id=request.id,
                )
            except Exception as e:
                return MCPResponse(
                    error={"code": "TALOS_CHAT_INTERNAL", "message": f"Setup error: {str(e)}"},
                    id=request.id,
                )

            # Proxy to Ollama
            ollama_url = "http://localhost:11434/api/chat"
            payload = {
                "model": args.get("model", "llama3.2:latest"),
                "messages": args.get("messages"),
                "options": {
                    "temperature": args.get("temperature", 0.7),
                    # map max_tokens to num_predict? Ollama uses num_predict.
                    "num_predict": args.get("max_tokens", 512),
                },
                "stream": False,
            }

            # Enforce timeout
            timeout_ms = args.get("timeout_ms", 60000)

            try:
                # requests.post timeout is in seconds
                resp = requests.post(ollama_url, json=payload, timeout=timeout_ms / 1000.0)

                if resp.status_code == 200:
                    ollama_data = resp.json()
                    # Transform to MCP result
                    # Response: messages[], usage, model, finish_reason
                    # Ollama returns: message { role, content }, done_reason, eval_count, etc.

                    response_message = ollama_data.get("message", {})

                    result_content = {
                        "messages": [response_message],
                        "model": ollama_data.get("model"),
                        "finish_reason": ollama_data.get("done_reason"),
                        "usage": {
                            "prompt_tokens": ollama_data.get("prompt_eval_count", 0),
                            "completion_tokens": ollama_data.get("eval_count", 0),
                        },
                    }

                    return MCPResponse(result=result_content, id=request.id)
                elif resp.status_code == 404:
                    return MCPResponse(
                        error={
                            "code": "TALOS_CHAT_OLLAMA_UNAVAILABLE",
                            "message": "Ollama model not found or endpoint invalid",
                        },
                        id=request.id,
                    )
                else:
                    return MCPResponse(
                        error={
                            "code": "TALOS_CHAT_UPSTREAM_ERROR",
                            "message": f"Ollama returned {resp.status_code}: {resp.text}",
                        },
                        id=request.id,
                    )

            except requests.exceptions.ConnectionError:
                return MCPResponse(
                    error={
                        "code": "TALOS_CHAT_OLLAMA_UNAVAILABLE",
                        "message": "Could not connect to Ollama (Connection Refused)",
                    },
                    id=request.id,
                )
            except requests.exceptions.Timeout:
                return MCPResponse(
                    error={"code": "TALOS_CHAT_OLLAMA_TIMEOUT", "message": "Request timed out"},
                    id=request.id,
                )
            except Exception as e:
                return MCPResponse(
                    error={
                        "code": "TALOS_CHAT_UPSTREAM_ERROR",
                        "message": f"Unexpected error: {str(e)}",
                    },
                    id=request.id,
                )

        return MCPResponse(
            error={"code": "METHOD_NOT_FOUND", "message": f"Tool '{tool_name}' not found"},
            id=request.id,
        )

    return MCPResponse(
        result={
            "method": request.method,
            "status": "acknowledged",
            "timestamp": time.time(),
        },
        id=request.id,
    )


@app.get("/api/mcp/tools")
def list_tools():
    """List available MCP tools."""
    return {
        "tools": [
            {
                "name": "filesystem",
                "description": "Secure filesystem access",
                "inputSchema": {"type": "object"},
            },
            {
                "name": "git",
                "description": "Git repository operations",
                "inputSchema": {"type": "object"},
            },
        ]
    }
