"""Tests for Idempotency Cache (Phase 9.3.3)."""
import pytest
from talos_mcp.idempotency import (
    IdempotencyCache,
    IdempotencyRecord,
    IdempotentToolExecutor,
)


class TestIdempotencyCache:
    """Test IdempotencyCache behavior."""

    @pytest.mark.asyncio
    async def test_get_nonexistent(self):
        """Get on empty cache should return None."""
        cache = IdempotencyCache()
        result = await cache.get("server", "tool", "key-123")
        assert result is None

    @pytest.mark.asyncio
    async def test_put_and_get(self):
        """Put then get should return the record."""
        cache = IdempotencyCache()
        record = IdempotencyRecord(
            server_id="mcp-github",
            tool_name="create-pr",
            idempotency_key="idem-key-001",
            tool_effect_id="01936a8b-4c2d-7000-8000-000000000001",
            tool_effect_digest="a" * 64,
            tool_effect_payload={"status": "SUCCESS"}
        )
        
        await cache.put(record)
        
        result = await cache.get("mcp-github", "create-pr", "idem-key-001")
        assert result is not None
        assert result.tool_effect_id == record.tool_effect_id
        assert result.tool_effect_payload == {"status": "SUCCESS"}

    @pytest.mark.asyncio
    async def test_exists(self):
        """Exists should return True after put."""
        cache = IdempotencyCache()
        record = IdempotencyRecord(
            server_id="mcp-github",
            tool_name="create-issue",
            idempotency_key="idem-key-002",
            tool_effect_id="01936a8b-4c2d-7000-8000-000000000002",
            tool_effect_digest="b" * 64,
            tool_effect_payload={"status": "SUCCESS"}
        )
        
        assert await cache.exists("mcp-github", "create-issue", "idem-key-002") is False
        await cache.put(record)
        assert await cache.exists("mcp-github", "create-issue", "idem-key-002") is True


class TestIdempotentToolExecutor:
    """Test IdempotentToolExecutor behavior."""

    @pytest.mark.asyncio
    async def test_first_execution_calls_fn(self):
        """First execution should call the execute function."""
        cache = IdempotencyCache()
        executor = IdempotentToolExecutor(cache)
        call_count = 0
        
        async def mock_execute():
            nonlocal call_count
            call_count += 1
            return {"tool_effect_id": "effect-001", "status": "SUCCESS"}
        
        result = await executor.execute(
            "mcp-github",
            "create-pr",
            "idem-first-001",
            mock_execute
        )
        
        assert call_count == 1
        assert result["status"] == "SUCCESS"

    @pytest.mark.asyncio
    async def test_repeat_execution_uses_cache(self):
        """Repeat execution should NOT call the execute function."""
        cache = IdempotencyCache()
        executor = IdempotentToolExecutor(cache)
        call_count = 0
        
        async def mock_execute():
            nonlocal call_count
            call_count += 1
            return {"tool_effect_id": "effect-002", "status": "SUCCESS"}
        
        # First call
        result1 = await executor.execute(
            "mcp-github",
            "create-pr",
            "idem-repeat-001",
            mock_execute
        )
        
        # Second call with same key
        result2 = await executor.execute(
            "mcp-github",
            "create-pr",
            "idem-repeat-001",
            mock_execute
        )
        
        assert call_count == 1  # Only called once
        assert result1 == result2  # Same result returned
