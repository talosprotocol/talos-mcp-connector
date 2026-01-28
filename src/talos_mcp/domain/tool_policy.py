"""Tool Policy Engine for Phase 9.2 enforcement.

This module implements manifest-first tool classification with:
- Tool registry loading from versioned contracts artifact
- Pre-execution validation for write operations
- Post-execution validation for read operations
- Stable error codes per LOCKED spec
"""
import hashlib
import json
import logging
import base64
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass
from pathlib import Path

from pathlib import Path
import jsonpointer

logger = logging.getLogger(__name__)


class ToolPolicyError(Exception):
    """Base exception for tool policy violations."""
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


class ToolClass(str, Enum):
    READ = "read"
    WRITE = "write"


@dataclass
class DocumentSpec:
    """Document operation specification."""
    write_content_pointers: List[str]
    read_content_pointers: List[str]
    content_encoding: str  # "utf8" or "base64"
    max_read_bytes: int
    max_write_bytes: int
    max_batch_bytes: int


@dataclass
class ToolPolicy:
    """Policy for a single tool."""
    tool_name: str
    tool_class: ToolClass
    is_document_op: bool
    requires_idempotency_key: bool
    read_replay_safe: bool
    document_spec: Optional[DocumentSpec]


@dataclass
class DocumentHash:
    """Hash result for a document pointer."""
    pointer: str
    hash: str  # SHA-256 lowercase hex
    size_bytes: int


class ToolPolicyEngine:
    """
    Loads tool registry and enforces policies per Phase 9.2 LOCKED spec.
    
    Security invariants:
    - Manifest-first: classification comes from registry, not heuristics
    - Deny-by-default: unknown tools are denied in production
    - Defense in depth: connector is primary enforcement point
    """
    
    def __init__(self, registry_path: Optional[str] = None, env: str = "dev"):
        """
        Initialize policy engine.
        
        Args:
            registry_path: Path to tool_registry.json (from contracts artifact)
            env: Environment - "dev" or "prod"
        """
        self.env = env
        self.registry: Dict[tuple, ToolPolicy] = {}
        
        if registry_path:
            self._load_registry(registry_path)
        else:
            # Default to checking the package
            self._load_registry("talos_contracts")
    
    def _load_registry(self, path_or_package: str) -> None:
        """Load tool registry from versioned contracts artifact."""
        try:
            # Try loading as a package resource (Production/CI)
            # path_or_package is expected to be "talos_contracts"
            import importlib.resources
            with importlib.resources.open_text("talos_contracts.data", "tools_registry.json") as f:
                data = json.load(f)
                logger.info("Loaded registry from talos_contracts package")
        except (ImportError, ModuleNotFoundError, FileNotFoundError):
            # Fallback for local dev where package might not be built
            path = path_or_package if path_or_package.endswith(".json") else "contracts/data/tools_registry.json"
            if not Path(path).exists():
                logger.warning(f"Registry not found at {path}. Running without registry.")
                return

            with open(path, 'r') as f:
                data = json.load(f)
                logger.info(f"Loaded registry from local path: {path}")
        
        # Phase 9.2: Validate metadata
        version = data.get("registry_version")
        if not version:
            logger.warning("Registry missing version!")
        
        # Allow multiple servers in one file or single server file
        # The schema lists "tools" under root.
        
        tools_list = data.get("tools", [])
        for tool_def in tools_list:
            if "tool_server" not in tool_def:
                # Should be valid per schema
                logger.warning(f"Skipping invalid tool def: {tool_def}")
                continue
                
            server_id = tool_def["tool_server"]
            tool_name = tool_def["tool_name"]
            
            doc_spec = None
            if tool_def.get("doc_policy"):
                # Map schema 'doc_policy' to DocumentSpec
                # Schema has: doc_policy: {max_size_bytes...}, doc_inputs: [], doc_outputs: []
                # The ToolPolicy expects DocumentSpec structure.
                # We need to adapt the schema format to internal structure or update internal structure.
                # Using the schema field names:
                d_pol = tool_def["doc_policy"]
                d_in = tool_def.get("doc_inputs", [])
                d_out = tool_def.get("doc_outputs", [])
                
                doc_spec = DocumentSpec(
                    write_content_pointers=d_in,
                    read_content_pointers=d_out,
                    content_encoding="utf8", # Default per schema implies utf8 usually, or check content-type
                    max_read_bytes=d_pol.get("max_size_bytes", 10485760),
                    max_write_bytes=d_pol.get("max_size_bytes", 5242880),
                    max_batch_bytes=d_pol.get("max_size_bytes", 52428800) * 10 # heuristic
                )
            
            policy = ToolPolicy(
                tool_name=tool_name,
                tool_class=ToolClass(tool_def["tool_class"]),
                is_document_op=bool(doc_spec),
                requires_idempotency_key=tool_def.get("requires_idempotency_key", False),
                read_replay_safe=tool_def.get("read_replay_safe", False),
                document_spec=doc_spec,
            )
            
            self.registry[(server_id, tool_name)] = policy
            logger.debug(f"Loaded policy for {server_id}:{tool_name}")

    def verify_registry_completeness(self, advertised_tools: List[Dict[str, str]]) -> List[str]:
        """
        CI Gate: Check if all advertised tools are in regulatory.
        
        Args:
            advertised_tools: List of {"server": "...", "tool": "..."}
            
        Returns:
            List of missing tools (server:tool).
        """
        missing = []
        for item in advertised_tools:
            s_id = item["server"]
            t_name = item["tool"]
            if (s_id, t_name) not in self.registry:
                missing.append(f"{s_id}:{t_name}")
        return missing

    def resolve_policy(self, server_id: str, tool_name: str) -> Optional[ToolPolicy]:
        """
        Resolve policy for a tool. Returns None if unclassified.
        
        Raises:
            ToolPolicyError: If tool is unclassified in production
        """
        policy = self.registry.get((server_id, tool_name))
        
        if policy is None:
            if self.env == "prod":
                raise ToolPolicyError(
                    f"Tool {server_id}:{tool_name} not in registry",
                    "TOOL_UNCLASSIFIED_DENIED"
                )
            # In dev, we might allow, but strictly log
            logger.warning(f"UNCLASSIFIED tool: {server_id}:{tool_name} (dev mode)")
        
        return policy
    
    def validate_capability_match(
        self, 
        policy: ToolPolicy, 
        capability_read_only: bool
    ) -> None:
        """
        Validate tool class against capability read_only flag.
        
        Raises:
            ToolPolicyError: If write tool called with read-only capability
        """
        # Decision Table Enforcement
        if key := (capability_read_only, policy.tool_class):
            if key == (True, ToolClass.WRITE):
                 raise ToolPolicyError(
                    f"Write tool '{policy.tool_name}' called with read-only capability",
                    "TOOL_CLASS_MISMATCH"
                )
            # (True, READ) -> OK
            # (False, READ) -> OK
            # (False, WRITE) -> OK
    
    def validate_tool_class_declaration(
        self,
        policy: ToolPolicy,
        declared_tool_class: Optional[str]
    ) -> None:
        """
        Validate agent-declared tool_class matches registry.
        
        Raises:
            ToolPolicyError: If declaration mismatches registry
        """
        if declared_tool_class and declared_tool_class != policy.tool_class.value:
            raise ToolPolicyError(
                f"Declared tool_class '{declared_tool_class}' != registry '{policy.tool_class.value}'",
                "TOOL_CLASS_DECLARATION_MISMATCH"
            )
    
    def validate_idempotency_key(
        self,
        policy: ToolPolicy,
        idempotency_key: Optional[str]
    ) -> None:
        """
        Validate idempotency key is present for write tools that require it.
        
        Raises:
            ToolPolicyError: If idempotency key is missing
        """
        if policy.requires_idempotency_key and not idempotency_key:
            raise ToolPolicyError(
                f"Write tool '{policy.tool_name}' requires idempotency_key",
                "IDEMPOTENCY_KEY_REQUIRED"
            )


class DocumentValidator:
    """
    Validates document operations per Phase 9.2 LOCKED spec.
    
    Handles:
    - Pre-execution validation (write ops) 
    - Post-execution validation (read ops)
    - Content hashing with deterministic preimage
    - Size limit enforcement
    """
    
    @staticmethod
    def extract_content(
        data: Dict[str, Any],
        pointer: str,
        encoding: str
    ) -> bytes:
        """
        Extract content bytes from data using JSON Pointer (RFC 6901).
        
        Args:
            data: Source data (args for write, result for read)
            pointer: JSON Pointer string (e.g., "/args/body")
            encoding: "utf8" or "base64"
        
        Returns:
            Content as bytes
        
        Raises:
            ToolPolicyError: If pointer resolution fails or encoding invalid
        """
        try:
            content = jsonpointer.resolve_pointer(data, pointer)
        except Exception as e:
            raise ToolPolicyError(
                f"Failed to resolve pointer '{pointer}': {e}",
                "DOC_POINTER_INVALID"
            )
        
        if content is None:
            return b""
        
        if not isinstance(content, str):
            # Enforce JCS (RFC 8785) for content canonicalization
            content = json.dumps(content, sort_keys=True, separators=(",", ":"))
        
        if encoding == "utf8":
            return content.encode("utf-8")
        elif encoding == "base64":
            try:
                return base64.b64decode(content)
            except Exception as e:
                raise ToolPolicyError(
                    f"Invalid base64 content at '{pointer}': {e}",
                    "DOC_ENCODING_INVALID"
                )
        else:
            raise ToolPolicyError(
                f"Unsupported encoding: {encoding}",
                "DOC_ENCODING_INVALID"
            )
    
    @staticmethod
    def compute_hash(content: bytes) -> str:
        """Compute SHA-256 hash of content (lowercase hex)."""
        return hashlib.sha256(content).hexdigest()
    
    @classmethod
    def validate_write_content(
        cls,
        doc_spec: DocumentSpec,
        args: Dict[str, Any],
        expected_hashes: Optional[List[Dict[str, str]]] = None
    ) -> List[DocumentHash]:
        """
        Pre-execution validation for write operations.
        
        Args:
            doc_spec: Document specification from registry
            args: Tool call arguments
            expected_hashes: Optional list of expected hashes from tool_call
        
        Returns:
            List of computed document hashes
        
        Raises:
            ToolPolicyError: If size limits exceeded or hash mismatch
        """
        results: List[DocumentHash] = []
        batch_total = 0
        
        for pointer in doc_spec.write_content_pointers:
            content = cls.extract_content(args, pointer, doc_spec.content_encoding)
            size = len(content)
            
            # Enforce per-write size limit
            if size > doc_spec.max_write_bytes:
                raise ToolPolicyError(
                    f"Write content at '{pointer}' exceeds limit ({size} > {doc_spec.max_write_bytes})",
                    "DOC_SIZE_EXCEEDED"
                )
            
            batch_total += size
            computed_hash = cls.compute_hash(content)
            
            # Check expected hash if provided
            if expected_hashes:
                expected = next(
                    (h for h in expected_hashes if h.get("pointer") == pointer),
                    None
                )
                if expected and expected.get("hash") != computed_hash:
                    raise ToolPolicyError(
                        f"Hash mismatch at '{pointer}': expected={expected['hash']}, got={computed_hash}",
                        "DOC_HASH_MISMATCH"
                    )
            
            results.append(DocumentHash(
                pointer=pointer,
                hash=computed_hash,
                size_bytes=size
            ))
        
        # Enforce batch size limit
        if batch_total > doc_spec.max_batch_bytes:
            raise ToolPolicyError(
                f"Batch size exceeds limit ({batch_total} > {doc_spec.max_batch_bytes})",
                "DOC_BATCH_SIZE_EXCEEDED"
            )
        
        return results
    
    @classmethod
    def validate_read_content(
        cls,
        doc_spec: DocumentSpec,
        result: Dict[str, Any]
    ) -> List[DocumentHash]:
        """
        Post-execution validation for read operations.
        
        Args:
            doc_spec: Document specification from registry
            result: Tool execution result
        
        Returns:
            List of computed document hashes
        
        Raises:
            ToolPolicyError: If size limits exceeded
        """
        results: List[DocumentHash] = []
        batch_total = 0
        
        for pointer in doc_spec.read_content_pointers:
            content = cls.extract_content(result, pointer, doc_spec.content_encoding)
            size = len(content)
            
            # Enforce per-read size limit
            if size > doc_spec.max_read_bytes:
                raise ToolPolicyError(
                    f"Read content at '{pointer}' exceeds limit ({size} > {doc_spec.max_read_bytes})",
                    "DOC_SIZE_EXCEEDED_READ"
                )
            
            batch_total += size
            computed_hash = cls.compute_hash(content)
            
            results.append(DocumentHash(
                pointer=pointer,
                hash=computed_hash,
                size_bytes=size
            ))
        
        # Enforce batch size limit
        if batch_total > doc_spec.max_batch_bytes:
            raise ToolPolicyError(
                f"Batch size exceeds limit ({batch_total} > {doc_spec.max_batch_bytes})",
                "DOC_BATCH_SIZE_EXCEEDED"
            )
        
        return results
