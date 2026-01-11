import json
import os
import subprocess
import threading
import uuid
import select
from typing import Dict, Any, List, Optional
from talos_mcp.transport.base import McpTransport
from talos_mcp.config import McpResourceConfig

class StdioMcpTransport(McpTransport):
    def __init__(self, config: McpResourceConfig):
        super().__init__(config)
        self.process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        
    def connect(self):
        if self.process:
            return

        cmd = [self.config.command] + (self.config.args or [])
        env = os.environ.copy()
        if self.config.env:
            env.update(self.config.env)

        try:
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                bufsize=0 # Unbuffered for direct interaction
            )
            # Verify it started
            # We might want to perform an initialize handshake here per MCP spec
            # For MVP let's assume valid connection on start
        except Exception as e:
            raise RuntimeError(f"Failed to start stdio transport for {self.config.id}: {e}")

    def close(self):
        if self.process:
            self.process.terminate()
            self.process = None

    def _send_request(self, method: str, params: Optional[Dict] = None) -> Dict:
        """Send JSON-RPC request and wait for response."""
        if not self.process:
            self.connect()
            
        request_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": request_id
        }
        
        with self._lock:
            if not self.process or self.process.poll() is not None:
                raise RuntimeError("Process is not running")
                
            json_str = json.dumps(payload) + "\n"
            self.process.stdin.write(json_str)
            self.process.stdin.flush()
            
            # Read response
            # Note: This is a synchronous blocking read for MVP. 
            # In production, this needs a reader thread to correlate IDs.
            # Assuming simple request-response lockstep for MVP.
            
            while True:
                line = self.process.stdout.readline()
                if not line:
                    stderr = self.process.stderr.read() if self.process.stderr else ""
                    raise RuntimeError(f"Process ended unexpectedly. Stderr: {stderr}")
                
                try:
                    response = json.loads(line)
                    if response.get("id") == request_id:
                        if "error" in response:
                            raise RuntimeError(f"MCP Error: {response['error']}")
                        return response.get("result", {})
                    # Ignore notifications or other ID mismatches for now (risky but MVP)
                except json.JSONDecodeError:
                    continue

    def list_tools(self) -> List[Dict[str, Any]]:
        result = self._send_request("tools/list")
        return result.get("tools", [])

    def get_tool_schema(self, tool_name: str) -> Dict[str, Any]:
        # Typically MCP 'tools/list' returns the schema in the listing.
        # If we need to fetch specifically, maybe the schema was returned in list.
        # We'll first check if we need a separate call. Standard MCP `tools/list` includes `inputSchema`.
        # So we listing all and filtering.
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
