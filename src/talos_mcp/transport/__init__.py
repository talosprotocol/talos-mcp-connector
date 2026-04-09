from typing import Dict, Type
from talos_mcp.config import McpResourceConfig
from talos_mcp.transport.base import McpTransport
from talos_mcp.transport.stdio import StdioMcpTransport
from talos_mcp.transport.http import HttpMcpTransport
from talos_mcp.transport.talos_tunnel import TalosTunnelTransport
from talos_mcp.transport.secure import SecureTalosTunnelTransport

def create_transport(config: McpResourceConfig) -> McpTransport:
    if config.transport == "stdio":
        return StdioMcpTransport(config)
    elif config.transport == "http":
        return HttpMcpTransport(config)
    elif config.transport == "talos_tunnel":
        return TalosTunnelTransport(config)
    elif config.transport == "secure_tunnel":
        return SecureTalosTunnelTransport(config)
    else:
        raise ValueError(f"Unsupported transport: {config.transport}")
