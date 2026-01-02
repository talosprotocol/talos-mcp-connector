"""
Bootstrap module for Talos MCP Connector.
Sets up Dependency Injection container with SDK adapters.
"""

from talos_sdk.container import Container, get_container
from talos_sdk.ports.audit_store import IAuditStorePort
from talos_sdk.ports.hash import IHashPort
from talos_sdk.adapters.memory_store import InMemoryAuditStore
from talos_sdk.adapters.hash import NativeHashAdapter


def bootstrap() -> Container:
    """Initialize the DI container with default adapters."""
    container = get_container()

    # Register adapters
    container.register(IAuditStorePort, InMemoryAuditStore())
    container.register(IHashPort, NativeHashAdapter())

    return container


# Application container instance
_container: Container | None = None


def get_app_container() -> Container:
    """Get the application's DI container."""
    global _container
    if _container is None:
        _container = bootstrap()
    return _container
