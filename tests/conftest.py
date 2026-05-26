"""
pytest configuration for Schola-herv test suite.
"""
import asyncio
import pytest


@pytest.fixture(scope="session")
def event_loop_policy():
    """Use the default event loop policy."""
    return asyncio.DefaultEventLoopPolicy()
