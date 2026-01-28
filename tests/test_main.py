"""Tests for Main API with Policy Enforcement."""
import json
import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

# Set env vars before importing main
os.environ["TALOS_MCP_CONFIG"] = "tests/fixtures/mcp_config.yaml"
os.environ["TALOS_MCP_TOOL_REGISTRY_PATH"] = "tests/fixtures/tool_registry.json"

from main import app, state
from talos_mcp.config import TalosMcpConfig, McpResourceConfig
from talos_mcp.domain.tool_policy import ToolClass, ToolPolicy, DocumentSpec

client = TestClient(app)

@pytest.fixture
def mock_config():
    config = MagicMock(spec=TalosMcpConfig)
    config.mcpServers = {
        "test-server": McpResourceConfig(
            id="test-server",
            name="Test Server",
            transport="stdio",
            command="echo"
        )
    }
    return config

@pytest.fixture
def mock_policy_engine():
    engine = MagicMock()
    return engine

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "mcp-connector"}

def test_call_tool_unclassified_denied(mock_config, mock_policy_engine):
    state.config = mock_config
    state.policy_engine = mock_policy_engine
    
    # Mock Policy Engine raising error
    from talos_mcp.domain.tool_policy import ToolPolicyError
    mock_policy_engine.resolve_policy.side_effect = ToolPolicyError("Not allowed", "TOOL_UNCLASSIFIED_DENIED")
    
    response = client.post(
        "/servers/test-server/tools/unknown-tool/call",
        json={"args": {}}
    )
    assert response.status_code == 403
    assert "TOOL_UNCLASSIFIED_DENIED" in response.text

def test_call_tool_write_success(mock_config, mock_policy_engine):
    state.config = mock_config
    state.policy_engine = mock_policy_engine
    
    # Mock Policy
    policy = ToolPolicy(
        tool_name="write-tool",
        tool_class=ToolClass.WRITE,
        is_document_op=False,
        requires_idempotency_key=True,
        document_spec=None
    )
    mock_policy_engine.resolve_policy.return_value = policy
    
    # Mock Transport
    with patch("main.create_transport") as mock_create:
        mock_transport = MagicMock()
        mock_transport.call_tool.return_value = {"status": "done"}
        mock_create.return_value = mock_transport
        
        response = client.post(
            "/servers/test-server/tools/write-tool/call",
            json={
                "args": {"foo": "bar"},
                "idempotency_key": "123"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["result"] == {"status": "done"}
        assert data["tool_class"] == "write"
        
        # Verify policy checks called
        mock_policy_engine.validate_capability_match.assert_called_once()
        mock_policy_engine.validate_idempotency_key.assert_called_once()
