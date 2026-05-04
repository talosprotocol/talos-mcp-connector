"""Security Hardening Tests for MCP Connector."""
import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from main import app
from talos_mcp.config import McpResourceConfig
from talos_mcp.domain.tool_policy import ToolClass, ToolPolicy
from talos_mcp.transport.stdio import StdioMcpTransport

client = TestClient(app)

def test_auth_headers_required():
    """Verify that X-Talos-Client-Id and X-Talos-Principal are required."""
    response = client.post(
        "/servers/test-server/tools/any-tool/call",
        json={"args": {}}
    )
    assert response.status_code == 401
    assert "Missing Talos Auth Headers" in response.text

def test_auth_headers_valid():
    """Verify that requests with headers are accepted."""
    with patch("main.state") as mock_state:
        mock_state.config.mcpServers = {
            "test-server": McpResourceConfig(id="test-server", name="T", transport="stdio")
        }
        mock_state.policy_engine.resolve_policy.return_value = ToolPolicy(
            tool_name="tool", tool_class=ToolClass.READ, is_document_op=False, requires_idempotency_key=False
        )
        
        with patch("main.create_transport") as mock_create:
            mock_transport = MagicMock()
            mock_transport.call_tool.return_value = {"ok": True}
            mock_create.return_value = mock_transport
            
            response = client.post(
                "/servers/test-server/tools/tool/call",
                headers={
                    "X-Talos-Client-Id": "client-1",
                    "X-Talos-Principal": "user-1"
                },
                json={"args": {}}
            )
            assert response.status_code == 200

def test_sandboxing_consent_denied():
    """Verify that local execution is denied without consent."""
    config = McpResourceConfig(
        id="unsafe-tool",
        name="Unsafe",
        transport="stdio",
        command="ls",
        allow_local_execution=False
    )
    transport = StdioMcpTransport(config)
    
    # Ensure env var is not set
    if "TALOS_ALLOW_LOCAL_TOOLS" in os.environ:
        del os.environ["TALOS_ALLOW_LOCAL_TOOLS"]
        
    with pytest.raises(RuntimeError) as excinfo:
        transport.connect()
    assert "Local execution denied" in str(excinfo.value)

def test_sandboxing_consent_allowed_via_config():
    """Verify that local execution is allowed with config consent."""
    config = McpResourceConfig(
        id="safe-tool",
        name="Safe",
        transport="stdio",
        command="echo",
        args=["hello"],
        allow_local_execution=True
    )
    transport = StdioMcpTransport(config)
    
    with patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value = MagicMock()
        transport.connect()
        assert mock_popen.called
        # Verify env sanitization
        env = mock_popen.call_args[1]["env"]
        assert "PATH" in env
        # Sensitive vars from os.environ should be missing if they were there
        # We can't easily check what's NOT there without knowing what was there, 
        # but we know the 'env' dict should only have allowed keys.
        allowed = {"PATH", "HOME", "USER", "LANG", "LC_ALL"}
        for k in env:
            assert k in allowed or k in (config.env or {})

def test_sandboxing_consent_allowed_via_env():
    """Verify that local execution is allowed with env var consent."""
    config = McpResourceConfig(
        id="safe-tool",
        name="Safe",
        transport="stdio",
        command="echo",
        args=["hello"],
        allow_local_execution=False
    )
    transport = StdioMcpTransport(config)
    
    os.environ["TALOS_ALLOW_LOCAL_TOOLS"] = "true"
    try:
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock()
            transport.connect()
            assert mock_popen.called
    finally:
        del os.environ["TALOS_ALLOW_LOCAL_TOOLS"]
