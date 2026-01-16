"""Idempotency Cache for Phase 9.3.3 - Connector.

This module implements durable idempotency for write-class tool executions.
Prevents double-execution during crash recovery per LOCKED spec.
"""
import hashlib
import json
import logging
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class IdempotencyRecord:
    """Record of a completed tool execution for idempotency."""
    server_id: str
    tool_name: str
    idempotency_key: str
    tool_effect_id: str
    tool_effect_digest: str
    tool_effect_payload: Dict[str, Any]
    
    def compute_key(self) -> str:
        """Compute cache key from (server_id, tool_name, idempotency_key)."""
        key_str = f"{self.server_id}:{self.tool_name}:{self.idempotency_key}"
        return hashlib.sha256(key_str.encode("utf-8")).hexdigest()


class IdempotencyCache:
    """
    Durable idempotency cache for write-class tool executions.
    
    Security invariants:
    - Same {server_id, tool_name, idempotency_key} MUST NOT re-execute
    - Returns cached tool_effect on repeat execution
    - Prevents double-execution during crash recovery
    """
    
    def __init__(self):
        # In-memory for development (replace with durable storage in production)
        self._cache: Dict[str, IdempotencyRecord] = {}
    
    async def get(
        self,
        server_id: str,
        tool_name: str,
        idempotency_key: str
    ) -> Optional[IdempotencyRecord]:
        """
        Check if a tool execution already exists.
        
        Returns:
            IdempotencyRecord if exists, None otherwise
        """
        cache_key = self._compute_key(server_id, tool_name, idempotency_key)
        return self._cache.get(cache_key)
    
    async def put(self, record: IdempotencyRecord) -> None:
        """
        Store an idempotency record.
        
        MUST be called atomically with tool execution completion.
        """
        cache_key = record.compute_key()
        self._cache[cache_key] = record
        logger.debug(f"Stored idempotency record: {cache_key[:16]}...")
    
    async def exists(
        self,
        server_id: str,
        tool_name: str,
        idempotency_key: str
    ) -> bool:
        """Check if an idempotency key exists."""
        cache_key = self._compute_key(server_id, tool_name, idempotency_key)
        return cache_key in self._cache
    
    def _compute_key(
        self,
        server_id: str,
        tool_name: str,
        idempotency_key: str
    ) -> str:
        """Compute cache key from tuple."""
        key_str = f"{server_id}:{tool_name}:{idempotency_key}"
        return hashlib.sha256(key_str.encode("utf-8")).hexdigest()


class IdempotentToolExecutor:
    """
    Wrapper for tool execution with idempotency enforcement.
    
    On first execution:
    - Execute tool
    - Persist idempotency record
    - Return tool_effect
    
    On repeat execution:
    - Return cached tool_effect
    - MUST NOT call tool server
    """
    
    def __init__(self, cache: IdempotencyCache):
        self.cache = cache
    
    async def execute(
        self,
        server_id: str,
        tool_name: str,
        idempotency_key: str,
        execute_fn,  # Callable that returns tool_effect
    ) -> Dict[str, Any]:
        """
        Execute tool with idempotency enforcement.
        
        Args:
            server_id: MCP server identifier
            tool_name: Tool name
            idempotency_key: Idempotency key from tool_call
            execute_fn: Async callable that executes the tool and returns effect
        
        Returns:
            Tool effect (cached or fresh)
        """
        # Check cache first
        existing = await self.cache.get(server_id, tool_name, idempotency_key)
        
        if existing is not None:
            logger.info(
                f"Idempotency hit: {server_id}:{tool_name}:{idempotency_key[:8]}..."
            )
            return existing.tool_effect_payload
        
        # Execute tool (first time)
        tool_effect = await execute_fn()
        
        # Compute digest for the effect
        canonical = json.dumps(tool_effect, sort_keys=True, separators=(",", ":"))
        effect_digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        
        # Store idempotency record
        record = IdempotencyRecord(
            server_id=server_id,
            tool_name=tool_name,
            idempotency_key=idempotency_key,
            tool_effect_id=tool_effect.get("tool_effect_id", ""),
            tool_effect_digest=effect_digest,
            tool_effect_payload=tool_effect
        )
        await self.cache.put(record)
        
        return tool_effect


# Singleton instance
_cache_instance: Optional[IdempotencyCache] = None


def get_idempotency_cache() -> IdempotencyCache:
    """Get or create the idempotency cache singleton."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = IdempotencyCache()
    return _cache_instance
