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

from abc import ABC, abstractmethod
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert
import os

class IdempotencyConflictError(Exception):
    """Raised when idempotency key is reused with different request parameters."""
    pass

@dataclass
class IdempotencyRecord:
    """Record of a completed tool execution for idempotency."""
    server_id: str
    tool_name: str
    idempotency_key: str
    principal_id: str
    request_digest: str
    tool_effect_id: str
    tool_effect_digest: str
    tool_effect_payload: Dict[str, Any]
    
    def compute_key(self) -> str:
        """Compute cache key from (principal_id, server_id, tool_name, idempotency_key)."""
        key_str = f"{self.principal_id}:{self.server_id}:{self.tool_name}:{self.idempotency_key}"
        return hashlib.sha256(key_str.encode("utf-8")).hexdigest()


class IdempotencyCache(ABC):
    """Abstract base class for idempotency cache."""
    
    @abstractmethod
    async def get(
        self,
        server_id: str,
        tool_name: str,
        idempotency_key: str,
        principal_id: str
    ) -> Optional[IdempotencyRecord]:
        pass

    @abstractmethod
    async def put(self, record: IdempotencyRecord) -> None:
        pass


class InMemoryIdempotencyCache(IdempotencyCache):
    """In-memory implementation for development."""
    
    def __init__(self):
        self._cache: Dict[str, IdempotencyRecord] = {}
    
    async def get(
        self, 
        server_id: str, 
        tool_name: str, 
        idempotency_key: str,
        principal_id: str
    ) -> Optional[IdempotencyRecord]:
        cache_key = self._compute_key(server_id, tool_name, idempotency_key, principal_id)
        return self._cache.get(cache_key)
    
    async def put(self, record: IdempotencyRecord) -> None:
        cache_key = record.compute_key()
        self._cache[cache_key] = record
        logger.debug(f"Stored idempotency record (mem): {cache_key[:16]}...")
    
    def _compute_key(self, server_id: str, tool_name: str, idempotency_key: str, principal_id: str) -> str:
        key_str = f"{principal_id}:{server_id}:{tool_name}:{idempotency_key}"
        return hashlib.sha256(key_str.encode("utf-8")).hexdigest()


class PostgresIdempotencyCache(IdempotencyCache):
    """PostgreSQL implementation for production."""

    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def get(
        self, 
        server_id: str, 
        tool_name: str, 
        idempotency_key: str,
        principal_id: str
    ) -> Optional[IdempotencyRecord]:
        # Create session
        with self.session_factory() as session:
            result = session.execute(
                text("""
                    SELECT server_id, tool_name, idempotency_key, principal_id, request_digest,
                           tool_effect_id, tool_effect_digest, tool_effect_payload
                    FROM mcp_idempotency
                    WHERE server_id = :server_id 
                      AND tool_name = :tool_name 
                      AND idempotency_key = :key
                      AND principal_id = :principal_id
                """),
                {
                    "server_id": server_id, 
                    "tool_name": tool_name, 
                    "key": idempotency_key,
                    "principal_id": principal_id
                }
            ).fetchone()
            
            if not result:
                return None
                
            return IdempotencyRecord(
                server_id=result.server_id,
                tool_name=result.tool_name,
                idempotency_key=result.idempotency_key,
                principal_id=result.principal_id,
                request_digest=result.request_digest,
                tool_effect_id=result.tool_effect_id,
                tool_effect_digest=result.tool_effect_digest,
                tool_effect_payload=result.tool_effect_payload
            )

    async def put(self, record: IdempotencyRecord) -> None:
        with self.session_factory() as session:
            try:
                session.execute(
                    text("""
                        INSERT INTO mcp_idempotency (
                            server_id, tool_name, idempotency_key, principal_id, request_digest,
                            tool_effect_id, tool_effect_digest, tool_effect_payload
                        ) VALUES (
                            :server_id, :tool_name, :key, :principal_id, :req_digest,
                            :effect_id, :digest, :payload
                        )
                    """),
                    {
                        "server_id": record.server_id,
                        "tool_name": record.tool_name,
                        "key": record.idempotency_key,
                        "principal_id": record.principal_id,
                        "req_digest": record.request_digest,
                        "effect_id": record.tool_effect_id,
                        "digest": record.tool_effect_digest,
                        "payload": json.dumps(record.tool_effect_payload)
                    }
                )
                session.commit()
                logger.debug(f"Stored idempotency record (db): {record.server_id}:{record.tool_name}...")
            except Exception as e:
                logger.error(f"Failed to persist idempotency record: {e}")
                session.rollback()
                raise


class IdempotentToolExecutor:
    """Wrapper for tool execution with idempotency enforcement."""
    
    def __init__(self, cache: IdempotencyCache):
        self.cache = cache
    
    async def execute(
        self,
        server_id: str,
        tool_name: str,
        idempotency_key: str,
        execute_fn,
        request_payload: Dict[str, Any],
        principal_id: str,
        capability_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute tool with idempotency enforcement using normative envelope hashing."""
        if not idempotency_key:
             # Phase 9.2: Spec requires idempotency_key for write tools.
             # This check should be enforced by policy before calling execute,
             # but we handle the null case for read tools here if they pass through.
             return await execute_fn()

        # Compute Request Digest (Canonical JCS SHA256 of Tool Call Envelope)
        envelope = {
            "tool_server": server_id,
            "tool_name": tool_name,
            "capability": capability_context,
            "args": request_payload
            # meta is optional and currently empty, principal_id is excluded from digest
        }
        # RFC 8785 JCS approximation (sort keys, no whitespace)
        canonical_req = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
        request_digest = hashlib.sha256(canonical_req.encode("utf-8")).hexdigest()

        # Check cache first
        existing = await self.cache.get(server_id, tool_name, idempotency_key, principal_id)
        
        if existing is not None:
            # STOP-SHIP: Deterministic Collision Check
            if existing.request_digest != request_digest:
                logger.warning(
                    f"Idempotency Conflict: Key {idempotency_key} reused with diff params. "
                    f"Stored Digest: {existing.request_digest}, New Digest: {request_digest}"
                )
                raise IdempotencyConflictError(f"Idempotency key '{idempotency_key}' reused with different request parameters.")
            
            logger.info(
                f"Idempotency hit: {server_id}:{tool_name}:{idempotency_key[:8]}..."
            )
            return existing.tool_effect_payload
        
        # Execute tool (first time)
        tool_effect = await execute_fn()
        
        # Compute digest for the effect (JCS JSON)
        canonical_effect = json.dumps(tool_effect, sort_keys=True, separators=(",", ":"))
        effect_digest = hashlib.sha256(canonical_effect.encode("utf-8")).hexdigest()
        
        # Store idempotency record
        record = IdempotencyRecord(
            server_id=server_id,
            tool_name=tool_name,
            idempotency_key=idempotency_key,
            principal_id=principal_id,
            request_digest=request_digest,
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
        db_url = os.environ.get("DATABASE_URL")
        # In Docker, we might need to wait for DB or retry. 
        # But this is usually called at runtime.
        if db_url:
             from sqlalchemy import create_engine
             from sqlalchemy.orm import sessionmaker
             engine = create_engine(db_url)
             session_factory = sessionmaker(bind=engine)
             _cache_instance = PostgresIdempotencyCache(session_factory)
        else:
            _cache_instance = InMemoryIdempotencyCache()
    return _cache_instance


class IdempotencyCache(ABC):
    """Abstract base class for idempotency cache."""
    
    @abstractmethod
    async def get(
        self,
        server_id: str,
        tool_name: str,
        idempotency_key: str
    ) -> Optional[IdempotencyRecord]:
        pass

    @abstractmethod
    async def put(self, record: IdempotencyRecord) -> None:
        pass

    @abstractmethod
    async def exists(
        self,
        server_id: str,
        tool_name: str,
        idempotency_key: str
    ) -> bool:
        pass


class InMemoryIdempotencyCache(IdempotencyCache):
    """In-memory implementation for development."""
    
    def __init__(self):
        self._cache: Dict[str, IdempotencyRecord] = {}
    
    async def get(self, server_id: str, tool_name: str, idempotency_key: str) -> Optional[IdempotencyRecord]:
        cache_key = self._compute_key(server_id, tool_name, idempotency_key)
        return self._cache.get(cache_key)
    
    async def put(self, record: IdempotencyRecord) -> None:
        cache_key = record.compute_key()
        self._cache[cache_key] = record
        logger.debug(f"Stored idempotency record (mem): {cache_key[:16]}...")
    
    async def exists(self, server_id: str, tool_name: str, idempotency_key: str) -> bool:
        cache_key = self._compute_key(server_id, tool_name, idempotency_key)
        return cache_key in self._cache
    
    def _compute_key(self, server_id: str, tool_name: str, idempotency_key: str) -> str:
        key_str = f"{server_id}:{tool_name}:{idempotency_key}"
        return hashlib.sha256(key_str.encode("utf-8")).hexdigest()


class PostgresIdempotencyCache(IdempotencyCache):
    """PostgreSQL implementation for production."""

    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def get(self, server_id: str, tool_name: str, idempotency_key: str) -> Optional[IdempotencyRecord]:
        # Create session
        with self.session_factory() as session:
            result = session.execute(
                text("""
                    SELECT server_id, tool_name, idempotency_key, tool_effect_id, 
                           tool_effect_digest, tool_effect_payload
                    FROM mcp_idempotency
                    WHERE server_id = :server_id 
                      AND tool_name = :tool_name 
                      AND idempotency_key = :key
                """),
                {"server_id": server_id, "tool_name": tool_name, "key": idempotency_key}
            ).fetchone()
            
            if not result:
                return None
                
            return IdempotencyRecord(
                server_id=result.server_id,
                tool_name=result.tool_name,
                idempotency_key=result.idempotency_key,
                tool_effect_id=result.tool_effect_id,
                tool_effect_digest=result.tool_effect_digest,
                tool_effect_payload=result.tool_effect_payload
            )

    async def put(self, record: IdempotencyRecord) -> None:
        with self.session_factory() as session:
            try:
                session.execute(
                    text("""
                        INSERT INTO mcp_idempotency (
                            server_id, tool_name, idempotency_key, tool_effect_id,
                            tool_effect_digest, tool_effect_payload
                        ) VALUES (
                            :server_id, :tool_name, :key, :effect_id,
                            :digest, :payload
                        )
                    """),
                    {
                        "server_id": record.server_id,
                        "tool_name": record.tool_name,
                        "key": record.idempotency_key,
                        "effect_id": record.tool_effect_id,
                        "digest": record.tool_effect_digest,
                        "payload": json.dumps(record.tool_effect_payload) 
                        # Note: SQLAlchemy/psycopg2 handles JSONB if we pass dict usually, 
                        # but text params might need string or explicit type.
                        # Let's try passing string for safety with text().
                    }
                )
                session.commit()
                logger.debug(f"Stored idempotency record (db): {record.server_id}:{record.tool_name}...")
            except Exception as e:
                logger.error(f"Failed to persist idempotency record: {e}")
                session.rollback()
                raise

    async def exists(self, server_id: str, tool_name: str, idempotency_key: str) -> bool:
         with self.session_factory() as session:
            result = session.execute(
                text("""
                    SELECT 1 FROM mcp_idempotency
                    WHERE server_id = :server_id 
                      AND tool_name = :tool_name 
                      AND idempotency_key = :key
                """),
                {"server_id": server_id, "tool_name": tool_name, "key": idempotency_key}
            ).fetchone()
            return result is not None


class IdempotentToolExecutor:
    """Wrapper for tool execution with idempotency enforcement."""
    
    def __init__(self, cache: IdempotencyCache):
        self.cache = cache
    
    async def execute(
        self,
        server_id: str,
        tool_name: str,
        idempotency_key: str,
        execute_fn,
    ) -> Dict[str, Any]:
        """Execute tool with idempotency enforcement."""
        if not idempotency_key:
             # No idempotency requested, just run
             return await execute_fn()

        # Check cache first
        existing = await self.cache.get(server_id, tool_name, idempotency_key)
        
        if existing is not None:
            logger.info(
                f"Idempotency hit: {server_id}:{tool_name}:{idempotency_key[:8]}..."
            )
            return existing.tool_effect_payload
        
        # Execute tool (first time)
        tool_effect = await execute_fn()
        
        # Compute digest
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
        db_url = os.environ.get("DATABASE_URL")
        if db_url:
             from sqlalchemy import create_engine
             from sqlalchemy.orm import sessionmaker
             engine = create_engine(db_url)
             session_factory = sessionmaker(bind=engine)
             _cache_instance = PostgresIdempotencyCache(session_factory)
        else:
            _cache_instance = InMemoryIdempotencyCache()
    return _cache_instance
