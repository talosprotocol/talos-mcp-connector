"""Unit tests for PostgresIdempotencyCache."""
import pytest
from unittest.mock import MagicMock, AsyncMock
from sqlalchemy import text
from talos_mcp.idempotency import PostgresIdempotencyCache, IdempotencyRecord

@pytest.mark.asyncio
async def test_put_idempotency_record():
    """Verify put generates correct INSERT."""
    mock_session = MagicMock()
    # Context manager mock
    mock_session_ctx = MagicMock()
    mock_session_ctx.__enter__.return_value = mock_session
    mock_session_ctx.__exit__.return_value = None
    
    msg_session_factory = MagicMock(return_value=mock_session_ctx)
    store = PostgresIdempotencyCache(msg_session_factory)
    
    record = IdempotencyRecord(
        server_id="s1", tool_name="t1", idempotency_key="k1",
        tool_effect_id="eff1", tool_effect_digest="d1",
        tool_effect_payload={"result": "ok"}
    )
    
    await store.put(record)
    
    # Verify INSERT execution
    calls = mock_session.execute.call_args_list
    print(f"DEBUG CALLS: {calls}")
    assert len(calls) > 0
    
    # Check SQL text
    # The first arg to execute is the text() object
    # calls[0] is (args, kwargs)
    # args is (text_obj, params_dict)
    sql_text = str(calls[0][0][0])
    assert "INSERT INTO mcp_idempotency" in sql_text
    
    # Check params
    # calls[0] is the call object.
    # calls[0][0] is the tuple of positional arguments.
    # calls[0][0][1] is the second positional argument (the params dict).
    params = calls[0][0][1]
    assert params["server_id"] == "s1"
    assert params["tool_name"] == "t1"
    assert params["key"] == "k1"
    assert params["payload"] == '{"result": "ok"}'

@pytest.mark.asyncio
async def test_get_idempotency_record_hit():
    """Verify get returns record on hit."""
    mock_session = MagicMock()
    mock_session_ctx = MagicMock()
    mock_session_ctx.__enter__.return_value = mock_session
    mock_session_ctx.__exit__.return_value = None
    
    msg_session_factory = MagicMock(return_value=mock_session_ctx)
    store = PostgresIdempotencyCache(msg_session_factory)
    
    # Mock result
    mock_row = MagicMock()
    mock_row.server_id = "s1"
    mock_row.tool_name = "t1"
    mock_row.idempotency_key = "k1"
    mock_row.tool_effect_id = "eff1"
    mock_row.tool_effect_digest = "d1"
    mock_row.tool_effect_payload = {"result": "cached"}
    
    mock_session.execute.return_value.fetchone.return_value = mock_row
    
    record = await store.get("s1", "t1", "k1")
    
    assert record is not None
    assert record.tool_effect_payload == {"result": "cached"}
    assert "SELECT server_id" in str(mock_session.execute.call_args[0][0])

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_put_idempotency_record())
    asyncio.run(test_get_idempotency_record_hit())
    print("TEST PASSED: test_idempotency")
