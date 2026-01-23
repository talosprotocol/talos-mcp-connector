# Talos MCP Connector - Claude Integration Guide

**Repo Role**: Secure bridge enabling existing MCP servers to join the Talos Network without code modification, providing encrypted tool invocation for AI agents.

## Component Overview

The Talos MCP Connector acts as a sidecar proxy that wraps local MCP servers in a secure Double Ratchet tunnel. It translates between standard MCP protocols (JSON-RPC over Stdio/SSE) and Talos-encrypted communication channels, allowing legacy tools to participate in the Talos Network securely.

Key capabilities:
- Transparent proxying of MCP tool calls through encrypted tunnels
- Stdio and HTTP transport support for diverse MCP server types
- Integration with Talos Gateway for network-wide tool discovery
- Automatic capability verification and access control enforcement

## Key Features

### Transport Adapters

#### Stdio Transport (`stdio.py`)
- Executes local MCP servers as subprocesses
- Manages stdin/stdout communication with JSON-RPC protocol
- Handles process lifecycle and error management
- Supports environment variable injection for server configuration

#### Talos Tunnel Transport (`talos_tunnel.py`)
- Bridges local MCP servers to the Talos Network
- Communicates with Gateway service via REST APIs
- Implements authentication with Talos API tokens
- Provides encrypted communication channel

### Configuration Management (`config.py`)
- YAML-based server configuration with environment variable substitution
- Support for multiple MCP server definitions in a single config
- Automatic transport inference based on configuration properties
- Pydantic-based validation for configuration integrity

### Core Abstractions (`base.py`)
- Abstract transport interface defining MCP operations
- Consistent API for tool listing, schema retrieval, and invocation
- Foundation for extending to new transport mechanisms

## Technical Architecture

### Framework Stack
- **Python 3.9+**: Primary implementation language
- **Pydantic**: Configuration validation and modeling
- **Requests**: HTTP client for Talos Tunnel transport
- **PyYAML**: Configuration file parsing
- **Subprocess**: Stdio transport process management

### Core Components

1. **Transport Layer**
   - StdioMcpTransport: Local process execution and communication
   - TalosTunnelTransport: Encrypted network communication
   - McpTransport: Abstract base for transport implementations

2. **Configuration System**
   - McpResourceConfig: Individual server configuration model
   - TalosMcpConfig: Aggregate configuration container
   - Environment variable substitution for dynamic values

3. **Dependency Injection**
   - Bootstrap module for SDK adapter registration
   - Container-based service locator pattern
   - Integration with Talos SDK for audit and hashing

### Data Flow

1. **Server Registration**
   - Configuration file defines MCP server properties
   - Transport adapter selected based on configuration
   - Local or remote server connection established

2. **Tool Discovery**
   - List available tools via transport-specific methods
   - Retrieve JSON schemas for tool parameter validation
   - Cache tool metadata for performance optimization

3. **Tool Invocation**
   - Validate tool arguments against JSON schema
   - Route calls through appropriate transport mechanism
   - Apply capability verification and access control
   - Return structured results to calling agent

## Dependencies

### Python Packages
- `pydantic>=2.0.0`: Data validation and settings management
- `PyYAML>=6.0`: YAML parsing for configuration files
- `requests>=2.31.0`: HTTP client for Talos Tunnel transport
- `talos-sdk-py`: Core SDK for audit trails and integrity

### Internal Dependencies
- `talos-contracts`: Canonical contract implementations
- `talos-sdk-py`: Audit storage, hashing, and identity services

## Deployment

### Docker Configuration
- Single-stage build process optimized for Python applications
- Non-root user execution for enhanced security
- Health check endpoints for orchestration
- Environment variable configuration support

### Environment Variables
- `TALOS_API_TOKEN`: Authentication token for Talos Gateway
- `CONFIG_PATH`: Path to MCP server configuration file
- `LOG_LEVEL`: Logging verbosity (DEBUG, INFO, WARNING, ERROR)

## Integration Points

### Upstream Services
- **Talos Gateway**: Tool discovery and routing coordination
- **Identity Service**: Authentication and authorization provider
- **Audit Service**: Immutable audit trail storage

### Downstream Services
- **Legacy MCP Servers**: Existing tools integrated via Stdio transport
- **Remote MCP Endpoints**: HTTP-based MCP server integration
- **AI Agents**: Tool consumers accessing capabilities through Talos Network

## Monitoring and Observability

### Audit Trail
- Immutable record of all tool invocations
- Cryptographic hashing for tamper detection
- Integration with centralized audit storage

### Logging
- Structured logging with correlation IDs
- Error reporting with context preservation
- Performance metrics for invocation latency

## Development Workflow

### Quickstart
```bash
# Install dependencies
pip install -r requirements.txt

# Run with sample configuration
python -m talos_mcp.connector ./config/sample.yaml
```

### Testing
```bash
make test
./scripts/test.sh
```

### Common Operations
1. **Add New MCP Server**: Update configuration YAML with server definition
2. **Invoke Tool**: Use transport adapter's `call_tool` method
3. **Check Capabilities**: Call `list_tools` to discover available functions

## Security Considerations

### Threat Model
- Compromise of local MCP server processes
- Unauthorized tool invocation through network exposure
- Credential leakage in configuration files

### Security Guarantees
- **Encrypted Communication**: All network traffic secured with Double Ratchet
- **Capability Verification**: Access control enforced at invocation time
- **Process Isolation**: Subprocess execution with restricted permissions
- **Audit Logging**: Immutable record of all tool interactions

## Future Enhancements

### Planned Improvements
- WebSocket transport support for real-time MCP servers
- Advanced caching mechanisms for improved performance
- Enhanced error handling with automatic retry logic
- Extended configuration options for fine-grained control

## References

1. [Model Context Protocol](https://github.com/modelcontextprotocol/specification)
2. [Talos Wiki](https://github.com/talosprotocol/talos/wiki)
3. [MCP Integration Guide](https://github.com/talosprotocol/talos/wiki/MCP-Integration)
4. [Pydantic Documentation](https://docs.pydantic.dev/)

## License

Licensed under the Apache License 2.0. See [LICENSE](LICENSE).