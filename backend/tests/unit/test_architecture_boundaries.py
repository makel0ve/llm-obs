import ast
from pathlib import Path

import pytest

API_DIR = Path(__file__).resolve().parents[2] / "app" / "api"

BANNED_API_IMPORT_PREFIXES = (
    "aioboto3",
    "boto3",
    "botocore",
    "redis.asyncio",
    "app.core.redis",
    "app.services.storage",
    "app.workers",
)

LEGACY_API_IMPLEMENTATION_IMPORT_ALLOWLIST = {
    ("v1/failed_tasks.py", "app.workers.process_span"),
    ("v1/health.py", "app.core.redis"),
    ("v1/health.py", "app.services.storage"),
    ("v1/health.py", "app.workers.health"),
    ("v1/metrics.py", "redis.asyncio"),
    ("v1/metrics.py", "app.core.redis"),
    ("v1/otlp.py", "redis.asyncio"),
    ("v1/otlp.py", "app.core.redis"),
    ("v1/pricing.py", "app.core.redis"),
    ("v1/projects.py", "app.core.redis"),
    ("v1/traces.py", "app.services.storage"),
}

pytestmark = pytest.mark.no_db


def _iter_import_modules(tree: ast.AST) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)

    return modules


def _is_banned_api_import(module: str) -> bool:
    return any(
        module == banned or module.startswith(f"{banned}.")
        for banned in BANNED_API_IMPORT_PREFIXES
    )


def test_api_layer_does_not_add_new_implementation_detail_imports() -> None:
    violations: set[str] = set()
    for path in sorted(API_DIR.rglob("*.py")):
        if path.name == "__init__.py":
            continue

        rel_path = path.relative_to(API_DIR).as_posix()
        tree = ast.parse(path.read_text(), filename=str(path))
        for module in _iter_import_modules(tree):
            if not _is_banned_api_import(module):
                continue
            if (rel_path, module) not in LEGACY_API_IMPLEMENTATION_IMPORT_ALLOWLIST:
                violations.add(f"{rel_path}: {module}")

    assert sorted(violations) == []
