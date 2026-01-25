import os
import re
import yaml
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, ValidationError

class McpResourceConfig(BaseModel):
    id: str
    name: str
    transport: str = Field(pattern='^(stdio|http|talos_tunnel)$')
    endpoint: Optional[str] = None
    command: Optional[str] = None
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None
    metadata: Optional[Dict[str, str]] = None

class TalosMcpConfig(BaseModel):
    mcpServers: Dict[str, McpResourceConfig]

    @classmethod
    def load(cls, path: Optional[str] = None) -> "TalosMcpConfig":
        from talos_config import ConfigurationLoader
        import os
        import re

        loader = ConfigurationLoader("talos-mcp")
        # Load using standard precedence, with optional file override
        data = loader.load(config_file=path, env_prefix="TALOS_MCP__")

        # Legacy Support: Recursive Regex Substitution for ${VAR}
        def substitute_env_vars(obj):
            if isinstance(obj, dict):
                return {k: substitute_env_vars(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [substitute_env_vars(i) for i in obj]
            elif isinstance(obj, str):
                def sub(match):
                    var_name = match.group(1)
                    val = os.getenv(var_name)
                    if val is None:
                        # Keep original if not set, or raise? Original raised ValueError.
                        # For shim, better to warn and keep or raise. Original raised.
                        raise ValueError(f"Environment variable '{var_name}' is not set")
                    return val
                return re.sub(r'\$\{([A-Z0-9_]+)\}', sub, obj)
            return obj

        data = substitute_env_vars(data)
        
        # Ensure mcpServers exists
        if "mcpServers" not in data:
            data["mcpServers"] = {}

        servers = {}
        for s_id, s_config in data.get("mcpServers", {}).items():
            # Auto-fill id and name if missing
            s_config["id"] = s_id
            if "name" not in s_config:
                s_config["name"] = s_id
            
            # Infer transport if not specified
            if "transport" not in s_config:
                if "command" in s_config:
                    s_config["transport"] = "stdio"
                elif "url" in s_config:
                    s_config["transport"] = "http"
                    s_config["endpoint"] = s_config.pop("url") # normalize
            
            servers[s_id] = McpResourceConfig(**s_config)

        # Inject version info for logging context if needed, though mostly used by CLI
        config = cls(mcpServers=servers)
        # Store loader instance/digest if we want to expose it
        config._loader = loader
        return config
