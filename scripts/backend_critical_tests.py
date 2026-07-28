"""Run backend tests that guard security and data-integrity invariants."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


CRITICAL_TEST_TARGETS: tuple[str, ...] = (
    "tests/unit/test_config.py",
    "tests/unit/test_payload_size_limit.py",
    "tests/unit/test_storage.py",
    "tests/integration/test_auth_api.py",
    "tests/integration/test_auth_current_user.py",
    "tests/integration/test_project_access_enforcement.py",
    "tests/integration/test_api_key_policies.py",
    "tests/integration/test_ingest_batch_status.py",
    "tests/integration/test_retention.py",
    "tests/integration/test_payload_privacy.py",
    "tests/integration/test_cost_service.py",
    "tests/integration/test_pricing_api.py",
)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    backend_dir = repo_root / "backend"
    missing_targets = [
        target
        for target in CRITICAL_TEST_TARGETS
        if not (backend_dir / target).exists()
    ]
    if missing_targets:
        print("Missing critical backend test targets:", file=sys.stderr)
        for target in missing_targets:
            print(f"  {target}", file=sys.stderr)
        return 2

    print("Running backend critical regression tests:", flush=True)
    for target in CRITICAL_TEST_TARGETS:
        print(f"  {target}", flush=True)

    command = [sys.executable, "-m", "pytest", *CRITICAL_TEST_TARGETS, "-q"]
    return subprocess.call(command, cwd=backend_dir)


if __name__ == "__main__":
    raise SystemExit(main())
