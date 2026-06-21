"""
Unit tests for JSON handling and repair concepts.
"""
import json
import pytest


def test_valid_json_parsing():
    """Test that valid JSON can be parsed."""
    valid_json = '{"key": "value", "number": 42}'
    parsed = json.loads(valid_json)
    assert parsed["key"] == "value"
    assert parsed["number"] == 42


def test_simple_array_parsing():
    """Test that JSON arrays can be parsed."""
    array_json = '["item1", "item2", "item3"]'
    parsed = json.loads(array_json)
    assert isinstance(parsed, list)
    assert len(parsed) == 3


def test_nested_object_parsing():
    """Test that nested objects are handled."""
    nested = '{"outer": {"inner": "value"}}'
    parsed = json.loads(nested)
    assert parsed["outer"]["inner"] == "value"


def test_empty_object_parsing():
    """Test that empty objects parse correctly."""
    empty = '{}'
    parsed = json.loads(empty)
    assert isinstance(parsed, dict)
    assert len(parsed) == 0


def test_json_with_special_characters():
    """Test that JSON with special characters parses correctly."""
    json_str = '{"text": "Hello\\nWorld", "emoji": "test"}'
    parsed = json.loads(json_str)
    assert "text" in parsed
    assert "\n" in parsed["text"]

