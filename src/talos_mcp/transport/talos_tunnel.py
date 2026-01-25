import requests
import os
from typing import Dict, Any, List, Optional
from talos_mcp.transport.base import McpTransport
from talos_mcp.config import McpResourceConfig

class TalosTunnelTransport(McpTransport):
    def connect(self):
        pass

    def close(self):
        pass

    def _get_headers(self) -> Dict[str, str]:
        # Use Shared Secret or configured Token
        token = os.getenv("TALOS_API_TOKEN") or os.getenv("AUTH_SECRET")
        if not token:
             # Fallback for local dev only
             token = "dev-" + "stub"
             
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

    def _send_request(self, method: str, path: str, payload: Optional[Dict] = None) -> Dict:
        if not self.config.endpoint:
            raise ValueError("No endpoint configured for Talos Tunnel")

        # Config endpoint should be base URL of gateway, e.g., http://localhost:8080/v1/mcp
        base_url = self.config.endpoint.rstrip("/")
        url = f"{base_url}/{path}"

        try:
            if method == "GET":
                resp = requests.get(url, headers=self._get_headers(), params=payload, timeout=30)
            else:
                resp = requests.post(url, headers=self._get_headers(), json=payload, timeout=30)
            
            resp.raise_for_status()
            return resp.json()
            
        except requests.exceptions.RequestException as e:
            # Try to read error body
            error_msg = str(e)
            if e.response is not None:
                try:
                    error_msg = e.response.json().get("details", error_msg)
                except:
                    error_msg = e.response.text
            raise RuntimeError(f"Talos Tunnel failed: {error_msg}")

    def list_tools(self) -> List[Dict[str, Any]]:
        # GET /servers/{id}/tools
        # Note: The tunnel config represents a REMOTE SERVER referenced by ID.
        # But the Gateway API structure is /servers/{server_id}/tools.
        # If this transport instance represents ONE server, we need that server's REMOTE ID.
        # We can use self.config.metadata.get("remote_server_id") or similar, 
        # OR assume self.config.id maps to the remote server ID.
        
        server_id = self.config.id
        # Map local ID to remote ID if needed, for now assume 1:1
        
        response = self._send_request("GET", f"servers/{server_id}/tools")
        return response.get("tools", [])

    def get_tool_schema(self, tool_name: str) -> Dict[str, Any]:
        # GET /servers/{id}/tools/{tool}/schema
        server_id = self.config.id
        response = self._send_request("GET", f"servers/{server_id}/tools/{tool_name}/schema")
        return response.get("json_schema", {})

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        # POST /servers/{id}/tools/{tool}:call
        server_id = self.config.id
        response = self._send_request("POST", f"servers/{server_id}/tools/{tool_name}:call", {
            "input": arguments
        })
        return response.get("output", {})
