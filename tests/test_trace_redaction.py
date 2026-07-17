"""Tests for run_trace_service._safe_trace_value — PII redaction and truncation."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.run_trace_service import _safe_trace_value, _SENSITIVE_KEYS


class TestRedaction:
    """Every key in _SENSITIVE_KEYS must be redacted."""

    @pytest.mark.parametrize("key", sorted(_SENSITIVE_KEYS))
    def test_sensitive_key_redacted(self, key: str):
        data = {key: "secret_value_here"}
        result = _safe_trace_value(data)
        assert isinstance(result, dict)
        assert result[key] == "[redacted]"

    def test_nested_sensitive_key_redacted(self):
        data = {"inner": {"api_key": "sk-123", "name": "test"}}
        result = _safe_trace_value(data)
        assert result["inner"]["api_key"] == "[redacted]"
        assert result["inner"]["name"] == "test"

    def test_case_insensitive_redaction(self):
        data = {"Authorization": "Bearer token", "API_KEY": "secret"}
        result = _safe_trace_value(data)
        assert result["Authorization"] == "[redacted]"
        assert result["API_KEY"] == "[redacted]"

    def test_partial_key_match_redacted(self):
        """Keys containing sensitive tokens are redacted (e.g. 'my_api_key')."""
        data = {"my_api_key": "secret", "user_email": "test@example.com"}
        result = _safe_trace_value(data)
        assert result["my_api_key"] == "[redacted]"
        assert result["user_email"] == "[redacted]"

    def test_new_sensitive_keys_present(self):
        """Verify the newly added keys from Issue #6 are in the set."""
        expected_new_keys = {"email", "phone", "recording_url", "assemblyai_transcript_id"}
        assert expected_new_keys.issubset(_SENSITIVE_KEYS)


class TestTruncation:
    def test_long_string_truncated(self):
        long_str = "x" * 1000
        result = _safe_trace_value(long_str)
        assert isinstance(result, str)
        assert len(result) < 1000
        assert result.endswith("...")

    def test_short_string_not_truncated(self):
        result = _safe_trace_value("short")
        assert result == "short"

    def test_large_list_truncated(self):
        big_list = list(range(100))
        result = _safe_trace_value(big_list)
        assert isinstance(result, list)
        # Should have max 5 items + 1 truncation notice
        assert len(result) <= 6

    def test_large_dict_truncated(self):
        big_dict = {f"key_{i}": i for i in range(50)}
        result = _safe_trace_value(big_dict)
        assert isinstance(result, dict)
        assert "__truncated__" in result

    def test_deep_nesting_truncated(self):
        data = {"a": {"b": {"c": {"d": {"e": {"f": "deep"}}}}}}
        result = _safe_trace_value(data)
        # At depth > 4, should be "[truncated]"
        inner = result["a"]["b"]["c"]["d"]
        assert inner.get("e") == "[truncated]" or inner == "[truncated]"

    def test_primitives_pass_through(self):
        assert _safe_trace_value(42) == 42
        assert _safe_trace_value(3.14) == 3.14
        assert _safe_trace_value(True) is True
        assert _safe_trace_value(None) is None

    def test_non_standard_types_stringified(self):
        result = _safe_trace_value(object())
        assert isinstance(result, str)
