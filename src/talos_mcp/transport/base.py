from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from talos_mcp.config import McpResourceConfig

class McpTransport(ABC):
    def __init__(self, config: McpResourceConfig):
        self.config = config

    @abstractmethod
    def connect(self):
        """Establish connection to the MCP server."""
        pass

    @abstractmethod
    def close(self):
        """Close the connection."""
        pass
    
    @abstractmethod
    def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools."""
        pass
        
    @abstractmethod
    def get_tool_schema(self, tool_name: str) -> Dict[str, Any]:
        """Get JSON schema for a tool."""
        pass
        
    @abstractmethod
    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Invoke a tool."""
        pass
