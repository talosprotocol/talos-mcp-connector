"""
Audit logging utilities for MCP Connector.
Uses SDK ports for consistent audit trail.
"""

import time
import uuid
from dataclasses import dataclass
from typing import Optional

from bootstrap import get_app_container
from talos_sdk.ports.audit_store import IAuditStorePort
from talos_sdk.ports.hash import IHashPort


@dataclass
class ConnectorEvent:
    """Audit event for connector operations."""

    event_id: str
    timestamp: float
    event_type: str
    resource_name: str
    action: str
    metadata: Optional[dict] = None


def log_event(
    event_type: str, resource_name: str, action: str, metadata: Optional[dict] = None
) -> str:
    """Log an audit event using the SDK audit store."""
    container = get_app_container()
    audit_store = container.resolve(IAuditStorePort)
    hash_port = container.resolve(IHashPort)

    event = ConnectorEvent(
        event_id=str(uuid.uuid4()),
        timestamp=time.time(),
        event_type=event_type,
        resource_name=resource_name,
        action=action,
        metadata=metadata,
    )

    audit_store.append(event)

    # Hash the event for integrity (optional cross-check)
    _ = hash_port.canonical_hash(
        {
            "event_id": event.event_id,
            "timestamp": event.timestamp,
            "type": event.event_type,
            "resource": event.resource_name,
            "action": event.action,
        }
    )

    return event.event_id


def get_recent_events(limit: int = 100):
    """Get recent audit events."""
    container = get_app_container()
    audit_store = container.resolve(IAuditStorePort)
    page = audit_store.list(limit=limit)
    return page.events
