"""
Pytest configuration and shared fixtures.
"""
import pytest


@pytest.fixture
def sample_session_id():
    """Sample session ID for testing."""
    return "test-session-123"


@pytest.fixture
def sample_prompt():
    """Sample prompt for testing."""
    return "Create a social media app with user authentication and posts"


@pytest.fixture
def sample_answers():
    """Sample clarification answers."""
    return ["Answer 1", "Answer 2"]

