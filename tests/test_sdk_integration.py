"""
SDK Integration Tests for talos-mcp-connector.

Verifies that:
1. DI container is properly bootstrapped
2. SDK ports are correctly registered
3. Audit logging works with SDK adapters
"""

import pytest
import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Skip all tests if talos_sdk is not installed
import importlib.util

SDK_AVAILABLE = importlib.util.find_spec("talos_sdk") is not None

pytestmark = pytest.mark.skipif(not SDK_AVAILABLE, reason="talos_sdk not installed")


class TestBootstrap:
    """Test DI container bootstrap."""

    def test_get_app_container_returns_container(self):
        """Container is created on first call."""
        from bootstrap import get_app_container

        container = get_app_container()
        assert container is not None

    def test_container_singleton(self):
        """Same container instance is reused."""
        from bootstrap import get_app_container

        c1 = get_app_container()
        c2 = get_app_container()
        assert c1 is c2

    def test_audit_store_registered(self):
        """IAuditStorePort is registered."""
        from bootstrap import get_app_container
        from talos_sdk.ports.audit_store import IAuditStorePort

        container = get_app_container()
        audit_store = container.resolve(IAuditStorePort)
        assert audit_store is not None

    def test_hash_port_registered(self):
        """IHashPort is registered."""
        from bootstrap import get_app_container
        from talos_sdk.ports.hash import IHashPort

        container = get_app_container()
        hash_port = container.resolve(IHashPort)
        assert hash_port is not None


class TestAuditLogging:
    """Test audit logging with SDK."""

    def test_log_event_returns_event_id(self):
        """log_event returns a valid event ID."""
        from audit import log_event

        event_id = log_event(
            event_type="test",
            resource_name="test_resource",
            action="create",
        )
        assert event_id is not None
        assert len(event_id) > 0

    def test_log_event_with_metadata(self):
        """log_event accepts metadata."""
        from audit import log_event

        event_id = log_event(
            event_type="test",
            resource_name="test_resource",
            action="update",
            metadata={"key": "value"},
        )
        assert event_id is not None

    def test_get_recent_events(self):
        """get_recent_events returns list."""
        from audit import get_recent_events, log_event

        # Log an event first
        log_event(event_type="test", resource_name="res", action="read")

        events = get_recent_events(limit=10)
        assert isinstance(events, list)


class TestHashPort:
    """Test hash port functionality."""

    def test_canonical_hash(self):
        """Hash port produces consistent hashes."""
        from bootstrap import get_app_container
        from talos_sdk.ports.hash import IHashPort

        container = get_app_container()
        hash_port = container.resolve(IHashPort)

        data = {"key": "value", "number": 42}
        hash1 = hash_port.canonical_hash(data)
        hash2 = hash_port.canonical_hash(data)

        assert hash1 == hash2
        assert len(hash1) == 32  # SHA-256 raw bytes

    def test_different_data_different_hash(self):
        """Different data produces different hashes."""
        from bootstrap import get_app_container
        from talos_sdk.ports.hash import IHashPort

        container = get_app_container()
        hash_port = container.resolve(IHashPort)

        hash1 = hash_port.canonical_hash({"a": 1})
        hash2 = hash_port.canonical_hash({"a": 2})

        assert hash1 != hash2
