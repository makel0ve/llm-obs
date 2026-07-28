"""Run npm audit with a reviewable allowlist and severity threshold."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Severity = Literal["info", "low", "moderate", "high", "critical"]

SEVERITY_RANK: dict[Severity, int] = {
    "info": 0,
    "low": 1,
    "moderate": 2,
    "high": 3,
    "critical": 4,
}


@dataclass(frozen=True)
class AllowlistEntry:
    package: str
    reason: str
    advisories: frozenset[str]


@dataclass(frozen=True)
class Vulnerability:
    package: str
    severity: Severity
    advisories: frozenset[str]
    title: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--package-dir",
        type=Path,
        default=Path("frontend"),
        help="Directory containing package-lock.json.",
    )
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=Path("security/npm-audit-allowlist.json"),
        help="JSON file containing reviewed npm audit ignores.",
    )
    parser.add_argument(
        "--audit-level",
        choices=tuple(SEVERITY_RANK),
        default="high",
        help="Minimum severity that fails the gate.",
    )
    parser.add_argument(
        "--omit",
        choices=("dev", "optional", "peer"),
        action="append",
        default=[],
        help="Dependency type to omit from npm audit. Repeatable.",
    )
    return parser.parse_args()


def load_json_file(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"allowlist file does not exist: {path}") from None
    except json.JSONDecodeError as exc:
        raise SystemExit(f"allowlist file is not valid JSON: {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise SystemExit(f"allowlist file must contain a JSON object: {path}")
    return raw


def load_allowlist(path: Path) -> dict[str, list[AllowlistEntry]]:
    raw = load_json_file(path)
    entries = raw.get("ignore", [])
    if not isinstance(entries, list):
        raise SystemExit("allowlist field 'ignore' must be a list")

    allowlist: dict[str, list[AllowlistEntry]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise SystemExit("each allowlist entry must be an object")

        package = entry.get("package")
        reason = entry.get("reason")
        advisories = entry.get("advisories", [])
        if not isinstance(package, str) or not package:
            raise SystemExit("each allowlist entry needs a non-empty package")
        if not isinstance(reason, str) or not reason:
            raise SystemExit(f"allowlist entry for {package} needs a reason")
        if not isinstance(advisories, list) or not all(
            isinstance(item, str) and item for item in advisories
        ):
            raise SystemExit(f"allowlist entry for {package} has invalid advisories")

        allowlist.setdefault(package, []).append(
            AllowlistEntry(
                package=package,
                reason=reason,
                advisories=frozenset(advisories),
            )
        )

    return allowlist


def as_severity(value: object) -> Severity:
    if value in SEVERITY_RANK:
        return value  # type: ignore[return-value]
    return "info"


def advisory_ids(via: object) -> frozenset[str]:
    if not isinstance(via, list):
        return frozenset()

    ids: set[str] = set()
    for item in via:
        if isinstance(item, str):
            ids.add(item)
            continue
        if not isinstance(item, dict):
            continue
        for field in ("source", "url", "title"):
            value = item.get(field)
            if isinstance(value, str) and value:
                ids.add(value)
    return frozenset(ids)


def vulnerabilities_from_audit(raw: dict[str, object]) -> list[Vulnerability]:
    vulnerabilities = raw.get("vulnerabilities", {})
    if not isinstance(vulnerabilities, dict):
        raise SystemExit("npm audit JSON did not contain a vulnerabilities object")

    results: list[Vulnerability] = []
    for package, details in vulnerabilities.items():
        if not isinstance(package, str) or not isinstance(details, dict):
            continue
        via = details.get("via", [])
        advisories = advisory_ids(via)
        title = package
        if isinstance(via, list):
            for item in via:
                if isinstance(item, dict) and isinstance(item.get("title"), str):
                    title = item["title"]
                    break
        results.append(
            Vulnerability(
                package=package,
                severity=as_severity(details.get("severity")),
                advisories=advisories,
                title=title,
            )
        )
    return results


def is_allowed(
    vulnerability: Vulnerability,
    allowlist: dict[str, list[AllowlistEntry]],
) -> bool:
    entries = allowlist.get(vulnerability.package, [])
    if not entries:
        return False

    for entry in entries:
        if not entry.advisories:
            return True
        if vulnerability.advisories & entry.advisories:
            return True
    return False


def run_npm_audit(package_dir: Path, omit: list[str]) -> dict[str, object]:
    command = ["npm", "audit", "--json"]
    for dependency_type in omit:
        command.append(f"--omit={dependency_type}")

    completed = subprocess.run(
        command,
        cwd=package_dir,
        check=False,
        capture_output=True,
        text=True,
    )
    if not completed.stdout.strip():
        message = completed.stderr.strip() or "npm audit did not return JSON"
        raise SystemExit(message)

    try:
        raw = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"npm audit returned invalid JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise SystemExit("npm audit JSON root must be an object")
    if completed.returncode not in (0, 1):
        message = (
            completed.stderr.strip() or f"npm audit failed: {completed.returncode}"
        )
        raise SystemExit(message)
    return raw


def main() -> int:
    args = parse_args()
    audit_level = args.audit_level
    allowlist = load_allowlist(args.allowlist)
    audit = run_npm_audit(args.package_dir, args.omit)
    vulnerabilities = vulnerabilities_from_audit(audit)
    failing = [
        vulnerability
        for vulnerability in vulnerabilities
        if SEVERITY_RANK[vulnerability.severity] >= SEVERITY_RANK[audit_level]
        and not is_allowed(vulnerability, allowlist)
    ]

    if not failing:
        print(f"npm audit passed: no unallowlisted {audit_level}+ vulnerabilities")
        return 0

    print(
        f"npm audit failed: {len(failing)} unallowlisted "
        f"{audit_level}+ vulnerabilities",
        file=sys.stderr,
    )
    for vulnerability in sorted(
        failing,
        key=lambda item: (-SEVERITY_RANK[item.severity], item.package),
    ):
        print(
            f"- {vulnerability.package}: {vulnerability.severity}: "
            f"{vulnerability.title}",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
