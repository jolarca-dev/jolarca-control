"""Minimal health check — ensures the test harness is wired correctly."""


def test_health() -> None:
    """Assert True so CI has at least one passing test."""
    assert True
