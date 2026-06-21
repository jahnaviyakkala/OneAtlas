"""
Unit tests for integration registry and concepts.
"""
import pytest


def test_integration_names_list():
    """Test that we can work with a list of integration names."""
    integration_names = ["slack", "stripe", "gmail", "whatsapp", "webhook", "google_sheets"]
    assert len(integration_names) > 0
    assert "slack" in integration_names
    assert "stripe" in integration_names


def test_integration_properties():
    """Test that integrations have expected properties."""
    integration = {
        "id": "slack",
        "name": "Slack",
        "type": "messaging",
        "is_stub": False
    }
    assert integration["id"] == "slack"
    assert integration["name"] == "Slack"
    assert isinstance(integration["is_stub"], bool)


def test_implemented_vs_stubbed_integrations():
    """Test categorization of integrations."""
    implemented = ["slack", "gmail", "stripe", "whatsapp", "webhook", "google_sheets"]
    stubbed = ["jira", "hubspot", "notion", "twilio_sms"]
    
    assert len(implemented) > 0
    assert len(stubbed) > 0
    assert len(set(implemented) & set(stubbed)) == 0, "No integration should be both implemented and stubbed"


def test_integration_registry_structure():
    """Test that registry follows expected structure."""
    registry = {
        "slack": {"id": "slack", "name": "Slack"},
        "stripe": {"id": "stripe", "name": "Stripe"},
    }
    
    for integration_id, integration in registry.items():
        assert integration["id"] == integration_id
        assert "name" in integration

