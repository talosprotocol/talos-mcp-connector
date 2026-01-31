# Agent workspace: services/mcp-connector
> **Project**: services/mcp-connector

This folder contains agent-facing context, tasks, workflows, and planning artifacts for this submodule.

## Current State
MCP connector wraps tool interactions with policy enforcement. Read and write tool separation and tool registry policies are active.

## Expected State
Strict least privilege and deterministic auditing. Robust error handling and compatibility with multiple tool servers.

## Behavior
Acts as a policy and transport adapter for MCP tools. Enforces registry constraints, idempotency, and audit-friendly hashing.

## How to work here
- Run/tests:
- Local dev:
- CI notes:

## Interfaces and dependencies
- Owned APIs/contracts:
- Depends on:
- Data stores/events (if any):

## Global context
See `.agent/context.md` for monorepo-wide invariants and architecture.
