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
    def load(cls, path: str) -> "TalosMcpConfig":
        if not os.path.exists(path):
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path, "r") as f:
            raw_content = f.read()

        # Env var substitution
        def env_sub(match):
            var_name = match.group(1)
            val = os.getenv(var_name)
            if val is None:
                raise ValueError(f"Environment variable '{var_name}' is not set")
            return val

        # Regex for ${VAR}
        content_sub = re.sub(r'\$\{([A-Z0-9_]+)\}', env_sub, raw_content)

        data = yaml.safe_load(content_sub)
        
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

        return cls(mcpServers=servers)
