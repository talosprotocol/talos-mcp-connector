# Architecture

## Overview

The MCP Connector acts as a secure bridge between Talos Agents and standard MCP servers.

## Data Flow

```mermaid
sequenceDiagram
    participant Agent as Talos Agent
    participant Gateway as Talos Gateway
    participant Connector as MCP Connector
    participant Policy as Policy Engine
    participant Server as MCP Server
    
    Agent->>Gateway: Encrypted MCP Request
    Gateway->>Connector: Authorized Request
    Connector->>Policy: Check mcp_config.yaml
    Policy-->>Connector: ALLOW/DENY
    alt Allowed
        Connector->>Server: Stdio Request
        Server-->>Connector: Response
        Connector->>Gateway: Audit Log + Response
        Gateway-->>Agent: Encrypted Response
    else Denied
        Connector->>Gateway: DENIAL (reason)
        Gateway-->>Agent: Error
    end
```

## Components

```mermaid
graph TD
    subgraph Connector
        Main[connector.py]
        Policy[Policy Engine]
        Bridge[Stdio Bridge]
        Audit[Audit Logger]
    end
    
    subgraph Config
        YAML[mcp_config.yaml]
        ENV[.env]
    end
    
    subgraph MCP Servers
        Git[local-git]
        SQLite[sqlite-db]
        Ollama[ollama-local]
    end
    
    Main --> Policy
    Policy --> YAML
    Policy --> Bridge
    Bridge --> Git & SQLite & Ollama
    Main --> Audit
```

## Capability Enforcement

| Check | Description |
|-------|-------------|
| `require_capability` | Require valid capability token |
| Scope matching | Tool/method must match capability scope |
| Expiration | Capability must not be expired |
| Revocation | Capability must not be revoked |
