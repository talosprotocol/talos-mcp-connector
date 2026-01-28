"""Tests for tool policy engine (Phase 9.2.1)."""
import pytest
from talos_mcp.domain.tool_policy import (
    ToolPolicyEngine,
    DocumentValidator,
    ToolPolicyError,
    ToolClass,
    DocumentSpec,
    ToolPolicy,
)


class TestToolPolicyEngine:
    """Test ToolPolicyEngine behavior."""

    def test_resolve_unclassified_dev_mode(self):
        """Dev mode should return None for unclassified tools."""
        engine = ToolPolicyEngine(env="dev")
        policy = engine.resolve_policy("unknown-server", "unknown-tool")
        assert policy is None

    def test_resolve_unclassified_prod_mode(self):
        """Prod mode should raise for unclassified tools."""
        engine = ToolPolicyEngine(env="prod")
        with pytest.raises(ToolPolicyError) as exc:
            engine.resolve_policy("unknown-server", "unknown-tool")
        assert exc.value.code == "TOOL_UNCLASSIFIED_DENIED"

    def test_validate_capability_match_read_ok(self):
        """Read tool with read-only capability should pass."""
        policy = ToolPolicy(
            tool_name="list-issues",
            tool_class=ToolClass.READ,
            is_document_op=False,
            requires_idempotency_key=False,
            document_spec=None,
        )
        engine = ToolPolicyEngine(env="dev")
        engine.validate_capability_match(policy, capability_read_only=True)
        # No exception = pass

    def test_validate_capability_match_write_with_readonly_fails(self):
        """Write tool with read-only capability should fail."""
        policy = ToolPolicy(
            tool_name="create-pr",
            tool_class=ToolClass.WRITE,
            is_document_op=True,
            requires_idempotency_key=True,
            document_spec=None,
        )
        engine = ToolPolicyEngine(env="dev")
        with pytest.raises(ToolPolicyError) as exc:
            engine.validate_capability_match(policy, capability_read_only=True)
        assert exc.value.code == "TOOL_CLASS_MISMATCH"

    def test_validate_tool_class_declaration_mismatch(self):
        """Agent-declared tool_class mismatch should fail."""
        policy = ToolPolicy(
            tool_name="create-pr",
            tool_class=ToolClass.WRITE,
            is_document_op=True,
            requires_idempotency_key=True,
            document_spec=None,
        )
        engine = ToolPolicyEngine(env="dev")
        with pytest.raises(ToolPolicyError) as exc:
            engine.validate_tool_class_declaration(policy, declared_tool_class="read")
        assert exc.value.code == "TOOL_CLASS_DECLARATION_MISMATCH"

    def test_validate_idempotency_key_missing(self):
        """Missing idempotency key for write tool should fail."""
        policy = ToolPolicy(
            tool_name="create-pr",
            tool_class=ToolClass.WRITE,
            is_document_op=True,
            requires_idempotency_key=True,
            document_spec=None,
        )
        engine = ToolPolicyEngine(env="dev")
        with pytest.raises(ToolPolicyError) as exc:
            engine.validate_idempotency_key(policy, idempotency_key=None)
        assert exc.value.code == "IDEMPOTENCY_KEY_REQUIRED"


class TestDocumentValidator:
    """Test DocumentValidator behavior."""

    def test_compute_hash(self):
        """Hash computation should return lowercase hex."""
        result = DocumentValidator.compute_hash(b"hello world")
        assert len(result) == 64
        assert result == result.lower()
        # Known SHA-256 of "hello world"
        assert result == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"

    def test_validate_write_content_size_exceeded(self):
        """Write content exceeding limit should fail."""
        doc_spec = DocumentSpec(
            write_content_pointers=["/content"],
            read_content_pointers=[],
            content_encoding="utf8",
            max_read_bytes=10485760,
            max_write_bytes=10,  # Very small for test
            max_batch_bytes=52428800,
        )
        args = {"content": "This is more than 10 bytes"}
        
        with pytest.raises(ToolPolicyError) as exc:
            DocumentValidator.validate_write_content(doc_spec, args)
        assert exc.value.code == "DOC_SIZE_EXCEEDED"

    def test_validate_write_content_hash_mismatch(self):
        """Hash mismatch should fail."""
        doc_spec = DocumentSpec(
            write_content_pointers=["/content"],
            read_content_pointers=[],
            content_encoding="utf8",
            max_read_bytes=10485760,
            max_write_bytes=5242880,
            max_batch_bytes=52428800,
        )
        args = {"content": "hello world"}
        expected_hashes = [{"pointer": "/content", "hash": "wrong_hash"}]
        
        with pytest.raises(ToolPolicyError) as exc:
            DocumentValidator.validate_write_content(doc_spec, args, expected_hashes)
        assert exc.value.code == "DOC_HASH_MISMATCH"

    def test_validate_write_content_success(self):
        """Valid write content should return hashes."""
        doc_spec = DocumentSpec(
            write_content_pointers=["/content"],
            read_content_pointers=[],
            content_encoding="utf8",
            max_read_bytes=10485760,
            max_write_bytes=5242880,
            max_batch_bytes=52428800,
        )
        args = {"content": "hello world"}
        
        results = DocumentValidator.validate_write_content(doc_spec, args)
        
        assert len(results) == 1
        assert results[0].pointer == "/content"
        assert results[0].hash == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
        assert results[0].size_bytes == 11

    def test_validate_read_content_size_exceeded(self):
        """Read content exceeding limit should fail."""
        doc_spec = DocumentSpec(
            write_content_pointers=[],
            read_content_pointers=["/result"],
            content_encoding="utf8",
            max_read_bytes=10,  # Very small for test
            max_write_bytes=5242880,
            max_batch_bytes=52428800,
        )
        result = {"result": "This is more than 10 bytes"}
        
        with pytest.raises(ToolPolicyError) as exc:
            DocumentValidator.validate_read_content(doc_spec, result)
        assert exc.value.code == "DOC_SIZE_EXCEEDED_READ"
