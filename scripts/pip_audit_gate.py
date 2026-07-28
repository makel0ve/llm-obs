"""Run pip-audit on project dependency graphs with a reviewable allowlist."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path


@dataclass(frozen=True)
class AllowlistEntry:
    package: str
    advisories: frozenset[str]
    reason: str
    expires: date


@dataclass(frozen=True)
class Vulnerability:
    project: Path
    package: str
    version: str
    advisory: str
    fix_versions: tuple[str, ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project",
        type=Path,
        action="append",
        required=True,
        help="Python project directory to audit. Repeatable.",
    )
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=Path("security/pip-audit-allowlist.json"),
        help="JSON file containing reviewed pip-audit ignores.",
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


def parse_expiry(value: object, package: str) -> date:
    if not isinstance(value, str) or not value:
        raise SystemExit(f"allowlist entry for {package} needs an expires date")

    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(
            f"allowlist entry for {package} has invalid expires date: {value}"
        ) from exc


def load_allowlist(path: Path) -> dict[str, list[AllowlistEntry]]:
    raw = load_json_file(path)
    entries = raw.get("ignore", [])
    if not isinstance(entries, list):
        raise SystemExit("allowlist field 'ignore' must be a list")

    today = datetime.now(UTC).date()
    allowlist: dict[str, list[AllowlistEntry]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise SystemExit("each allowlist entry must be an object")

        package = entry.get("package")
        advisories = entry.get("advisories")
        reason = entry.get("reason")
        if not isinstance(package, str) or not package:
            raise SystemExit("each allowlist entry needs a non-empty package")
        if not isinstance(advisories, list) or not all(
            isinstance(item, str) and item for item in advisories
        ):
            raise SystemExit(f"allowlist entry for {package} needs advisories")
        if not isinstance(reason, str) or not reason:
            raise SystemExit(f"allowlist entry for {package} needs a reason")

        expires = parse_expiry(entry.get("expires"), package)
        if expires < today:
            raise SystemExit(
                f"allowlist entry for {package} expired on {expires.isoformat()}"
            )

        allowlist.setdefault(package, []).append(
            AllowlistEntry(
                package=package,
                advisories=frozenset(advisories),
                reason=reason,
                expires=expires,
            )
        )

    return allowlist


def run_pip_audit(project: Path) -> dict[str, object]:
    completed = subprocess.run(
        ["pip-audit", str(project), "--skip-editable", "--format", "json"],
        check=False,
        capture_output=True,
        text=True,
    )
    if not completed.stdout.strip():
        message = completed.stderr.strip() or f"pip-audit failed for {project}"
        raise SystemExit(message)

    try:
        raw = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"pip-audit returned invalid JSON for {project}: {exc}"
        ) from exc

    if not isinstance(raw, dict):
        raise SystemExit(f"pip-audit JSON root must be an object for {project}")
    if completed.returncode not in (0, 1):
        message = completed.stderr.strip() or (
            f"pip-audit failed for {project}: {completed.returncode}"
        )
        raise SystemExit(message)
    return raw


def vulnerabilities_from_audit(
    project: Path,
    audit: dict[str, object],
) -> list[Vulnerability]:
    dependencies = audit.get("dependencies", [])
    if not isinstance(dependencies, list):
        raise SystemExit(f"pip-audit JSON did not contain dependencies: {project}")

    vulnerabilities: list[Vulnerability] = []
    for dependency in dependencies:
        if not isinstance(dependency, dict):
            continue
        package = dependency.get("name")
        version = dependency.get("version")
        vulns = dependency.get("vulns", [])
        if not isinstance(package, str) or not isinstance(version, str):
            continue
        if not isinstance(vulns, list):
            continue
        for vuln in vulns:
            if not isinstance(vuln, dict):
                continue
            advisory = vuln.get("id")
            fix_versions = vuln.get("fix_versions", [])
            if not isinstance(advisory, str):
                continue
            if not isinstance(fix_versions, list) or not all(
                isinstance(item, str) for item in fix_versions
            ):
                fix_versions = []
            vulnerabilities.append(
                Vulnerability(
                    project=project,
                    package=package,
                    version=version,
                    advisory=advisory,
                    fix_versions=tuple(fix_versions),
                )
            )
    return vulnerabilities


def is_allowed(
    vulnerability: Vulnerability,
    allowlist: dict[str, list[AllowlistEntry]],
) -> bool:
    entries = allowlist.get(vulnerability.package, [])
    return any(vulnerability.advisory in entry.advisories for entry in entries)


def main() -> int:
    args = parse_args()
    allowlist = load_allowlist(args.allowlist)
    vulnerabilities: list[Vulnerability] = []
    for project in args.project:
        vulnerabilities.extend(
            vulnerabilities_from_audit(project, run_pip_audit(project))
        )

    failing = [
        vulnerability
        for vulnerability in vulnerabilities
        if not is_allowed(vulnerability, allowlist)
    ]
    if not failing:
        print("pip-audit passed: no unallowlisted vulnerabilities")
        return 0

    print(
        f"pip-audit failed: {len(failing)} unallowlisted vulnerabilities",
        file=sys.stderr,
    )
    for vulnerability in sorted(
        failing,
        key=lambda item: (str(item.project), item.package, item.advisory),
    ):
        fixes = ", ".join(vulnerability.fix_versions) or "no fix version"
        print(
            f"- {vulnerability.project}: {vulnerability.package} "
            f"{vulnerability.version}: {vulnerability.advisory} ({fixes})",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
