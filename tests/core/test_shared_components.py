"""Architectural validation tests for Shared Components.

This module ensures that the shared components and foundational packages
strictly adhere to the dependency rules defined in the architecture.
These tests act as automated guardrails to prevent accidental dependency violations.
"""

import ast
from pathlib import Path

import app.core


def test_core_exports_shared_access_points():
    """Verify that core infrastructure symbols are accessible from app.core."""
    expected_symbols = [
        "get_logger",
        "initialize_logging",
        "shutdown_logging",
        "report_application_error",
        "ApplicationError",
        "ApplicationLifecycle",
        "ApplicationState",
        "ComponentRegistry",
        "ComponentNotFoundError",
        "ComponentNotInitializedError",
    ]

    for symbol in expected_symbols:
        assert hasattr(app.core, symbol), f"app.core must export '{symbol}'"


def test_models_has_no_internal_dependencies():
    """Verify that app/models/ does not import from any other app package.

    Rule: Data Model must be completely independent to avoid circular dependencies.
    """
    models_dir = Path("app/models")

    for py_file in models_dir.rglob("*.py"):
        with open(py_file, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                # Check absolute imports starting with 'app.'
                if node.module and node.module.startswith("app."):
                    raise AssertionError(
                        f"File {py_file} imports from '{node.module}'. "
                        "Violation: models/ must not depend on any other app module."
                    )
                # Check relative imports going up to parent packages (level > 1)
                if node.level > 1:
                    raise AssertionError(
                        f"File {py_file} uses relative import going up {node.level} levels. "
                        "Violation: models/ must not depend on parent packages."
                    )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("app."):
                        raise AssertionError(
                            f"File {py_file} imports '{alias.name}'. "
                            "Violation: models/ must not depend on any other app module."
                        )


def test_core_has_no_upward_dependencies():
    """Verify that app/core/ does not import from business or mid-level modules.

    Rule: Infrastructure layer (core/) must not depend on business logic.
    Note: application.py acts as the composition root and is allowed to wire
    infrastructure components (like storage), but not business logic.
    """
    core_dir = Path("app/core")

    # Modules that core/ must NEVER depend on
    forbidden_modules = {
        "services",
        "pipelines",
        "knowledge",
        "fetchers",
        "integrations",
        "vectorstores",
    }

    for py_file in core_dir.rglob("*.py"):
        # application.py is the composition root, allowed to wire infrastructure
        if py_file.name == "application.py":
            continue

        with open(py_file, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    # Extract the top-level module name (e.g., 'services' from 'services.digest')
                    top_module = node.module.split(".")[0]
                    if top_module in forbidden_modules:
                        raise AssertionError(
                            f"File {py_file} imports from '{node.module}'. "
                            f"Violation: core/ must not depend on '{top_module}'."
                        )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    top_module = alias.name.split(".")[0]
                    if top_module in forbidden_modules:
                        raise AssertionError(
                            f"File {py_file} imports '{alias.name}'. "
                            f"Violation: core/ must not depend on '{top_module}'."
                        )
