import requests
import uuid
from typing import Dict, Any, List, Optional
from talos_mcp.transport.base import McpTransport
from talos_mcp.config import McpResourceConfig

class HttpMcpTransport(McpTransport):
    def connect(self):
        # Stateless
        pass

    def close(self):
        # Stateless
        pass

    def _send_request(self, method: str, params: Optional[Dict] = None) -> Dict:
        if not self.config.endpoint:
            raise ValueError("No endpoint configured for HTTP transport")

        request_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": request_id
        }

        # Assuming standard JSON-RPC over HTTP POST
        try:
            resp = requests.post(self.config.endpoint, json=payload, timeout=30)
            resp.raise_for_status()
            response = resp.json()
            
            if "error" in response:
                raise RuntimeError(f"MCP Error: {response['error']}")
            return response.get("result", {})
            
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"HTTP Transport failed: {e}")

    def list_tools(self) -> List[Dict[str, Any]]:
        result = self._send_request("tools/list")
        return result.get("tools", [])

    def get_tool_schema(self, tool_name: str) -> Dict[str, Any]:
        tools = self.list_tools()
        for t in tools:
            if t["name"] == tool_name:
                return t.get("inputSchema", {})
        raise ValueError(f"Tool {tool_name} not found")

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })
