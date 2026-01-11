import json
import os
import time
import hashlib
from typing import Dict, Any, Optional
from pathlib import Path

class SchemaCache:
    def __init__(self, cache_dir: Optional[str] = None):
        if cache_dir:
            self.base_dir = Path(cache_dir)
        else:
            self.base_dir = Path.home() / ".cache" / "talos" / "mcp" / "schemas"
        
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(self, server_id: str, tool_name: str) -> Path:
        server_dir = self.base_dir / server_id
        server_dir.mkdir(exist_ok=True)
        return server_dir / f"{tool_name}.json"

    def get(self, server_id: str, tool_name: str, ttl_seconds: int = 3600) -> Optional[Dict[str, Any]]:
        path = self._get_path(server_id, tool_name)
        if not path.exists():
            return None
        
        try:
            with open(path, "r") as f:
                data = json.load(f)
            
            # Check TTL
            fetched_at = data.get("fetched_at", 0)
            if time.time() - fetched_at > ttl_seconds:
                return None # Expired
            
            return data.get("schema")
        except Exception:
            return None

    def put(self, server_id: str, tool_name: str, schema: Dict[str, Any], schema_hash: Optional[str] = None):
        path = self._get_path(server_id, tool_name)
        
        # Calculate hash if not provided
        if not schema_hash:
            from talos_sdk.canonical import canonical_json
            s_json = canonical_json(schema)
            schema_hash = hashlib.sha256(s_json.encode()).hexdigest()
        
        data = {
            "schema": schema,
            "schema_hash": schema_hash,
            "fetched_at": time.time()
        }
        
        with open(path, "w") as f:
            json.dump(data, f)
            
    def get_hash(self, server_id: str, tool_name: str) -> Optional[str]:
        """Get just the hash without checking TTL (useful for etag logic)"""
        path = self._get_path(server_id, tool_name)
        if not path.exists():
            return None
        try:
            with open(path, "r") as f:
                data = json.load(f)
            return data.get("schema_hash")
        except Exception:
            return None
