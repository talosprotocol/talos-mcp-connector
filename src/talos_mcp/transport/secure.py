import asyncio
import logging
import json
from typing import Dict, Any, List, Optional
from talos_mcp.transport.base import McpTransport
from talos_mcp.config import McpResourceConfig

# In this project, the core Talos logic is mostly async
from talos.legacy_client import TalosClient
from talos.channel import SecureChannel

logger = logging.getLogger(__name__)

class SecureTalosTunnelTransport(McpTransport):
    """
    MCP Transport that uses a secure Talos SecureChannel.
    Provides end-to-end encryption for MCP requests.
    
    This implementation wraps async Talos SDK calls into the synchronous 
    McpTransport interface.
    """
    
    def __init__(self, config: McpResourceConfig, client: Optional[TalosClient] = None):
        super().__init__(config)
        self.client = client
        self.channel: Optional[SecureChannel] = None
        self._connected = False
        self._loop = asyncio.new_event_loop()

    def connect(self):
        if self._connected:
            return
            
        if not self.client:
            # Try to initialize a default client if not provided
            # This is just for demonstration/fallback
            from talos.config import TalosConfig
            cfg = TalosConfig()
            self.client = TalosClient(cfg)
        
        peer_id = self.config.id
        peer_bundle = self.config.metadata.get("peer_bundle") if self.config.metadata else None
        
        self.channel = SecureChannel(self.client, peer_id, peer_bundle)
        self._loop.run_until_complete(self.channel.connect())
        self._connected = True
        logger.info(f"Connected secure tunnel to {peer_id[:16]}...")

    def close(self):
        if self.channel and self._connected:
            self._loop.run_until_complete(self.channel.close())
        self._connected = False
        self._loop.close()

    def _rpc_call(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self._connected:
            self.connect()
        
        request = {
            "jsonrpc": "2.0",
            "id": f"mcp-{id(self)}-{self._loop.time()}",
            "method": method,
            "params": params
        }
        
        async def do_call():
            await self.channel.send_json(request)
            return await self.channel.receive_json(timeout=30.0)
            
        response = self._loop.run_until_complete(do_call())
        
        if "error" in response:
            raise RuntimeError(f"MCP RPC Error: {response['error']}")
        
        return response.get("result", {})

    def list_tools(self) -> List[Dict[str, Any]]:
        # GET /tools -> mapped to JSON-RPC method
        result = self._rpc_call("tools/list", {})
        return result.get("tools", [])

    def get_tool_schema(self, tool_name: str) -> Dict[str, Any]:
        result = self._rpc_call("tools/get_schema", {"name": tool_name})
        return result.get("json_schema", {})

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return self._rpc_call("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })
