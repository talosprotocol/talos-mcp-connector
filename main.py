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
    # Placeholder implementation
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
