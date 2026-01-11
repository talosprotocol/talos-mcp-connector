import json
import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock
from talos_mcp.cli import main, create_transport

@pytest.fixture
def runner():
    return CliRunner()

@pytest.fixture
def mock_config(tmp_path):
    config_file = tmp_path / "mcp_servers.json"
    config_file.write_text(json.dumps({
        "mcpServers": {
            "test": {
                "command": "echo",
                "args": ["hello"],
                "env": {}
            }
        }
    }))
    return str(config_file)

def test_ls_command(runner, mock_config):
    result = runner.invoke(main, ['--config', mock_config, 'ls', '--json'])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data['servers']) == 1
    assert data['servers'][0]['id'] == 'test'

@patch('talos_mcp.cli.create_transport')
def test_tools_command(mock_create, runner, mock_config):
    # Mock transport
    mock_transport = MagicMock()
    mock_transport.list_tools.return_value = [
        {"name": "tool1", "description": "desc1"}
    ]
    mock_create.return_value = mock_transport
    
    result = runner.invoke(main, ['--config', mock_config, 'tools', 'test', '--json'])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data['server_id'] == 'test'
    assert len(data['tools']) == 1
    assert data['tools'][0]['name'] == 'tool1'

@patch('talos_mcp.cli.create_transport')
def test_call_command(mock_create, runner, mock_config):
    mock_transport = MagicMock()
    mock_transport.call_tool.return_value = {"result": "ok"}
    mock_create.return_value = mock_transport
    
    result = runner.invoke(main, ['--config', mock_config, 'call', 'test', 'tool1', '--input', '{"arg":"val"}', '--json'])
    # Note: call command output is direct JSON, check if click wraps it or prints it
    # My implementation prints json.dumps(result)
    
    assert result.exit_code == 0
    # Output might contain newline
    data = json.loads(result.output.strip())
    assert data['result'] == "ok"
    
    mock_transport.call_tool.assert_called_with("tool1", {"arg": "val"})
