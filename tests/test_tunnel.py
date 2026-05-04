from unittest.mock import MagicMock, AsyncMock, patch
from talos_mcp.transport.secure import SecureTalosTunnelTransport
from talos_mcp.config import McpResourceConfig

def test_secure_tunnel_init():
    config = McpResourceConfig(
        id="peer-123",
        name="Secure Peer",
        transport="secure_tunnel",
        metadata={"peer_bundle": {"key": "value"}}
    )
    client = MagicMock()
    transport = SecureTalosTunnelTransport(config, client)
    assert transport.config.id == "peer-123"
    assert transport.client == client

@patch("talos_mcp.transport.secure.SecureChannel")
def test_secure_tunnel_rpc_call(mock_channel_cls):
    mock_channel = MagicMock()
    mock_channel.connect = AsyncMock()
    mock_channel.send_json = AsyncMock()
    mock_channel.receive_json = AsyncMock(return_value={
        "jsonrpc": "2.0",
        "result": {"tools": [{"name": "test-tool"}]}
    })
    mock_channel_cls.return_value = mock_channel
    
    config = McpResourceConfig(
        id="peer-123",
        name="Secure Peer",
        transport="secure_tunnel"
    )
    client = MagicMock()
    transport = SecureTalosTunnelTransport(config, client)
    
    tools = transport.list_tools()
    
    assert len(tools) == 1
    assert tools[0]["name"] == "test-tool"
    mock_channel.send_json.assert_called_once()
    assert mock_channel.send_json.call_args[0][0]["method"] == "tools/list"
