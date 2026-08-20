"""Tests for ComponentRegistry."""

import pytest

from app.core.registry import (
    ComponentNotFoundError,
    ComponentNotInitializedError,
    ComponentRegistry,
)


def test_register_and_get_component():
    """Verify that a component can be registered, started, and retrieved."""
    registry = ComponentRegistry()
    mock_instance = object()

    registry.register(
        "test_component",
        init_func=lambda: mock_instance,
        shutdown_func=lambda x: None,
        priority=10,
    )
    registry.start_all()

    result = registry.get_component("test_component")
    assert result is mock_instance


def test_register_duplicate_component_raises_error():
    """Verify that registering a duplicate component raises ValueError."""
    registry = ComponentRegistry()

    registry.register("test", lambda: None, lambda x: None, 10)

    with pytest.raises(ValueError, match="Component 'test' is already registered"):
        registry.register("test", lambda: None, lambda x: None, 20)


def test_get_nonexistent_component_raises_error():
    """Verify that getting a non-existent component raises ComponentNotFoundError."""
    registry = ComponentRegistry()

    with pytest.raises(ComponentNotFoundError, match="Component 'missing' not found"):
        registry.get_component("missing")


def test_get_uninitialized_component_raises_error():
    """Verify that getting a registered but uninitialized component raises error."""
    registry = ComponentRegistry()
    registry.register("test", lambda: object(), lambda x: None, 10)

    with pytest.raises(ComponentNotInitializedError, match="not initialized"):
        registry.get_component("test")


def test_has_component_returns_true_for_registered():
    """Verify that has_component returns True for registered components."""
    registry = ComponentRegistry()
    registry.register("test", lambda: None, lambda x: None, 10)

    assert registry.has_component("test") is True


def test_has_component_returns_false_for_missing():
    """Verify that has_component returns False for non-registered components."""
    registry = ComponentRegistry()

    assert registry.has_component("missing") is False


def test_start_all_initializes_in_priority_order():
    """Verify that components are initialized in ascending priority order."""
    registry = ComponentRegistry()
    init_order = []

    registry.register("low", lambda: init_order.append("low") or "low_inst", lambda x: None, 10)
    registry.register("high", lambda: init_order.append("high") or "high_inst", lambda x: None, 30)
    registry.register("mid", lambda: init_order.append("mid") or "mid_inst", lambda x: None, 20)

    registry.start_all()

    assert init_order == ["low", "mid", "high"]


def test_start_all_rollback_on_failure():
    """Verify that initialized components are shut down if a later component fails."""
    registry = ComponentRegistry()
    shutdown_calls = []

    def fail_init():
        raise RuntimeError("Init failed")

    registry.register("good", lambda: "good_inst", lambda x: shutdown_calls.append(x), 10)
    registry.register("bad", fail_init, lambda x: None, 20)

    with pytest.raises(RuntimeError, match="Init failed"):
        registry.start_all()

    # The 'good' component should have been rolled back
    assert shutdown_calls == ["good_inst"]


def test_shutdown_all_shuts_down_in_reverse_priority_order():
    """Verify that components are shut down in descending priority order."""
    registry = ComponentRegistry()
    shutdown_order = []

    registry.register("low", lambda: "low_inst", lambda x: shutdown_order.append("low"), 10)
    registry.register("high", lambda: "high_inst", lambda x: shutdown_order.append("high"), 30)
    registry.register("mid", lambda: "mid_inst", lambda x: shutdown_order.append("mid"), 20)

    registry.start_all()
    registry.shutdown_all()

    assert shutdown_order == ["high", "mid", "low"]


def test_shutdown_all_ignores_errors():
    """Verify that shutdown continues even if one component fails."""
    registry = ComponentRegistry()
    shutdown_calls = []

    def fail_shutdown(x):
        raise RuntimeError("Shutdown failed")

    registry.register("good", lambda: "good_inst", lambda x: shutdown_calls.append("good"), 10)
    registry.register("bad", lambda: "bad_inst", fail_shutdown, 20)

    registry.start_all()
    registry.shutdown_all()  # Should not raise

    assert "good" in shutdown_calls


def test_shutdown_all_resets_initialization_state():
    """Verify that components cannot be accessed after shutdown."""
    registry = ComponentRegistry()
    registry.register("test", lambda: "inst", lambda x: None, 10)

    registry.start_all()
    assert registry.get_component("test") == "inst"

    registry.shutdown_all()

    with pytest.raises(ComponentNotInitializedError):
        registry.get_component("test")
