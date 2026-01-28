"""
Talos MCP Connector - Main Application
Functions as a client to multiple MCP servers, exposing them via a unified HTTP API.
Enforces Phase 9.2 Tool Policies (Read/Write separation).
"""

import os
import logging
from typing import Dict, Any, Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Body, Header, Depends
from pydantic import BaseModel

from talos_mcp.config import TalosMcpConfig
from talos_mcp.transport import create_transport
from talos_mcp.domain.tool_policy import ToolPolicyEngine, ToolPolicyError, DocumentValidator
from talos_mcp.idempotency import get_idempotency_cache, IdempotentToolExecutor, IdempotencyConflictError

# ... (imports)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp-connector")

# Global State
class AppState:
    config: Optional[TalosMcpConfig] = None
    policy_engine: Optional[ToolPolicyEngine] = None

state = AppState()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    config_path = os.getenv("TALOS_MCP_CONFIG")
    try:
        state.config = TalosMcpConfig.load(config_path)
        logger.info(f"Loaded configuration with {len(state.config.mcpServers)} servers")
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        raise

    # Initialize Policy Engine
    # Path to tool_registry.schema.json relative to service root or via env
    # Actual registry is tool_registry.json (the instance), not the schema
    # For now, we look for 'tool_registry.json' in contracts/artifacts or similar
    # or fallback to env var
    registry_path = os.getenv("TALOS_MCP_TOOL_REGISTRY_PATH")
    env = os.getenv("TALOS_ENV", "dev")
    
    state.policy_engine = ToolPolicyEngine(registry_path, env)
    
    yield
    # Shutdown

app = FastAPI(title="Talos MCP Connector", version="0.2.0", lifespan=lifespan)

class ToolCallRequest(BaseModel):
    args: Dict[str, Any] = {}
    idempotency_key: Optional[str] = None
    capability_read_only: bool = False  # Caller asserts if they are read-only scope

class ToolCallResponse(BaseModel):
    result: Any
    tool_class: str
    document_hashes: Optional[List[Dict[str, Any]]] = None

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "mcp-connector"}

@app.get("/servers")
async def list_servers():
    """List configured MCP servers."""
    if not state.config:
        return {"servers": []}
    return {
        "servers": [
            {"id": s_id, "name": s.name, "transport": s.transport}
            for s_id, s in state.config.mcpServers.items()
        ]
    }

@app.get("/servers/{server_id}/tools")
async def list_tools(server_id: str):
    """List tools available on a specific server."""
    if not state.config or server_id not in state.config.mcpServers:
        raise HTTPException(status_code=404, detail="Server not found")
    
    server_conf = state.config.mcpServers[server_id]
    try:
        transport = create_transport(server_conf)
        tools = transport.list_tools()
        transport.close()
        return {"tools": tools}
    except Exception as e:
        logger.error(f"Error listing tools for {server_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/servers/{server_id}/tools/{tool_name}/call", response_model=ToolCallResponse)
async def call_tool(
    server_id: str, 
    tool_name: str, 
    request: ToolCallRequest = Body(...),
    x_talos_principal: Optional[str] = Header(None, alias="X-Talos-Principal")
):
    """
    Execute a tool with policy enforcement.
    """
    if not state.config or server_id not in state.config.mcpServers:
        raise HTTPException(status_code=404, detail="Server not found")

    principal_id = x_talos_principal or "anonymous"
    
    # 1. Resolve Policy
    try:
        policy = state.policy_engine.resolve_policy(server_id, tool_name)
    except ToolPolicyError as e:
        raise HTTPException(status_code=403, detail=f"Policy Denied: {e.code} - {str(e)}")
    
    # 2. Enforce Pre-Execution Policies
    try:
        # Check Capability
        state.policy_engine.validate_capability_match(policy, request.capability_read_only)
        
        # Check Idempotency (Presence)
        state.policy_engine.validate_idempotency_key(policy, request.idempotency_key)
        
        # Check Document Write Constraints
        doc_hashes = []
        if policy.tool_class.value == "write" and policy.is_document_op and policy.document_spec:
            doc_hashes = DocumentValidator.validate_write_content(
                policy.document_spec,
                request.args
            )
            # Serialize for response
            doc_hashes = [
                {"pointer": h.pointer, "hash": h.hash, "size_bytes": h.size_bytes} 
                for h in doc_hashes
            ]
            
    except ToolPolicyError as e:
        raise HTTPException(status_code=400, detail=f"Policy Violation: {e.code} - {str(e)}")

    # 3. Execute Tool (with Idempotency)
    server_conf = state.config.mcpServers[server_id]
    
    async def _execute_tool_unsafe() -> Any:
        try:
            # TODO: Use async transport if available, currently synchronous
            # We strictly bind transport creation to execution to avoid persistent connection issues
            transport = create_transport(server_conf)
            result = transport.call_tool(tool_name, request.args)
            transport.close()
            return result
        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            # Re-raise as HTTPException for consistent handling
            raise HTTPException(status_code=502, detail=f"Upstream Error: {str(e)}")

    try:
        if request.idempotency_key:
            cache = get_idempotency_cache()
            executor = IdempotentToolExecutor(cache)
            # Request Payload for Digest: We use args as the payload that determines uniqueness
            # The spec says "tool_call_envelope", which implicitly includes server, tool, args.
            # But here we pass args. Since server/tool are part of the key look up, 
            # differing args for same key constitutes a conflict.
            
            result = await executor.execute(
                server_id=server_id,
                tool_name=tool_name,
                idempotency_key=request.idempotency_key,
                execute_fn=_execute_tool_unsafe,
                request_payload=request.args,
                principal_id=principal_id,
                capability_context={"read_only": request.capability_read_only}
            )
        else:
            result = await _execute_tool_unsafe()
            
    except IdempotencyConflictError as e:
        logger.warning(f"Idempotency Conflict: {e}")
        raise HTTPException(status_code=409, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Execution error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    # 4. Enforce Post-Execution Policies (Read)
    try:
        if policy.tool_class.value == "read" and policy.is_document_op and policy.document_spec:
            read_hashes = DocumentValidator.validate_read_content(
                policy.document_spec,
                result
            )
            doc_hashes.extend([
                {"pointer": h.pointer, "hash": h.hash, "size_bytes": h.size_bytes} 
                for h in read_hashes
            ])
            
    except ToolPolicyError as e:
        # If read validation fails, we must mask the result or fail the request
        # Failing request ensures bad data doesn't leak
        raise HTTPException(status_code=502, detail=f"Output Policy Violation: {e.code} - {str(e)}")

    return ToolCallResponse(
        result=result,
        tool_class=policy.tool_class.value,
        document_hashes=doc_hashes
    )


    config: Optional[TalosMcpConfig] = None
    policy_engine: Optional[ToolPolicyEngine] = None

state = AppState()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    config_path = os.getenv("TALOS_MCP_CONFIG")
    try:
        state.config = TalosMcpConfig.load(config_path)
        logger.info(f"Loaded configuration with {len(state.config.mcpServers)} servers")
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        raise

    # Initialize Policy Engine
    # Path to tool_registry.schema.json relative to service root or via env
    # Actual registry is tool_registry.json (the instance), not the schema
    # For now, we look for 'tool_registry.json' in contracts/artifacts or similar
    # or fallback to env var
    registry_path = os.getenv("TALOS_MCP_TOOL_REGISTRY_PATH")
    env = os.getenv("TALOS_ENV", "dev")
    
    state.policy_engine = ToolPolicyEngine(registry_path, env)
    
    yield
    # Shutdown

app = FastAPI(title="Talos MCP Connector", version="0.2.0", lifespan=lifespan)

class ToolCallRequest(BaseModel):
    args: Dict[str, Any] = {}
    idempotency_key: Optional[str] = None
    capability_read_only: bool = False  # Caller asserts if they are read-only scope

class ToolCallResponse(BaseModel):
    result: Any
    tool_class: str
    document_hashes: Optional[List[Dict[str, Any]]] = None

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "mcp-connector"}

@app.get("/servers")
async def list_servers():
    """List configured MCP servers."""
    if not state.config:
        return {"servers": []}
    return {
        "servers": [
            {"id": s_id, "name": s.name, "transport": s.transport}
            for s_id, s in state.config.mcpServers.items()
        ]
    }

@app.get("/servers/{server_id}/tools")
async def list_tools(server_id: str):
    """List tools available on a specific server."""
    if not state.config or server_id not in state.config.mcpServers:
        raise HTTPException(status_code=404, detail="Server not found")
    
    server_conf = state.config.mcpServers[server_id]
    try:
        transport = create_transport(server_conf)
        tools = transport.list_tools()
        transport.close()
        return {"tools": tools}
    except Exception as e:
        logger.error(f"Error listing tools for {server_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/servers/{server_id}/tools/{tool_name}/call", response_model=ToolCallResponse)
async def call_tool(
    server_id: str, 
    tool_name: str, 
    request: ToolCallRequest = Body(...)
):
    """
    Execute a tool with policy enforcement.
    """
    if not state.config or server_id not in state.config.mcpServers:
        raise HTTPException(status_code=404, detail="Server not found")
    
    # 1. Resolve Policy
    try:
        policy = state.policy_engine.resolve_policy(server_id, tool_name)
    except ToolPolicyError as e:
        raise HTTPException(status_code=403, detail=f"Policy Denied: {e.code} - {str(e)}")
    
    # 2. Enforce Pre-Execution Policies
    try:
        # Check Capability
        state.policy_engine.validate_capability_match(policy, request.capability_read_only)
        
        # Check Idempotency
        state.policy_engine.validate_idempotency_key(policy, request.idempotency_key)
        
        # Check Document Write Constraints
        doc_hashes = []
        if policy.tool_class.value == "write" and policy.is_document_op and policy.document_spec:
            doc_hashes = DocumentValidator.validate_write_content(
                policy.document_spec,
                request.args
            )
            # Serialize for response
            doc_hashes = [
                {"pointer": h.pointer, "hash": h.hash, "size_bytes": h.size_bytes} 
                for h in doc_hashes
            ]
            
    except ToolPolicyError as e:
        raise HTTPException(status_code=400, detail=f"Policy Violation: {e.code} - {str(e)}")

    # 3. Execute Tool (with Idempotency)
    server_conf = state.config.mcpServers[server_id]
    
    async def _execute_tool_unsafe() -> Any:
        try:
            # TODO: Use async transport if available, currently synchronous
            transport = create_transport(server_conf)
            result = transport.call_tool(tool_name, request.args)
            transport.close()
            return result
        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            # Re-raise as HTTPException for consistent handling
            raise HTTPException(status_code=502, detail=f"Upstream Error: {str(e)}")

    try:
        if request.idempotency_key:
            cache = get_idempotency_cache()
            executor = IdempotentToolExecutor(cache)
            result = await executor.execute(
                server_id=server_id,
                tool_name=tool_name,
                idempotency_key=request.idempotency_key,
                execute_fn=_execute_tool_unsafe
            )
        else:
            result = await _execute_tool_unsafe()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Execution error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    # 4. Enforce Post-Execution Policies (Read)
    try:
        if policy.tool_class.value == "read" and policy.is_document_op and policy.document_spec:
            read_hashes = DocumentValidator.validate_read_content(
                policy.document_spec,
                result
            )
            doc_hashes.extend([
                {"pointer": h.pointer, "hash": h.hash, "size_bytes": h.size_bytes} 
                for h in read_hashes
            ])
            
    except ToolPolicyError as e:
        # If read validation fails, we must mask the result or fail the request
        # Failing request ensures bad data doesn't leak
        raise HTTPException(status_code=502, detail=f"Output Policy Violation: {e.code} - {str(e)}")

    return ToolCallResponse(
        result=result,
        tool_class=policy.tool_class.value,
        document_hashes=doc_hashes
    )
