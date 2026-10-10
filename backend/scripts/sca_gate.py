#!/usr/bin/env python3
"""Software composition analysis (SCA) gate for the backend's Python
dependency tree.

Policy: only fail CI when a vulnerable package is a *direct* dependency
(listed in `pyproject.toml`'s `[project.dependencies]`) that pip-audit
reports a published fix for. Never fail CI over a vulnerable *transitive*
dependency, or a direct dependency with no fix published yet — forcing a
transitive package's version while leaving its parent unchanged is a risky,
untested combination this project doesn't want to gate on. Those cases are
reported (visible, non-blocking) instead.

Exception list: some findings technically have a "direct dependency" fix per
the rule above, but that fix has been evaluated and found unsafe to apply
right now. Rather than special-casing those here, `sca-exceptions.json` (next
to this script's parent directory) is a standing, reusable override list:
each entry names a vuln id (as pip-audit reports it, e.g. a GHSA/PYSEC/CVE
id) and a documented reason, and any finding matching an entry is reported
separately as EXEMPTED instead of blocking. This is deliberately visible,
not silent — exempted findings are still printed on every run, and an
exception that stops matching anything (the finding got fixed upstream) is
flagged as stale so it doesn't linger unreviewed.

Run via: uv run python scripts/sca_gate.py
(pip-audit itself is pulled in ad hoc via `uv run --with pip-audit`, so it
isn't a tracked project dependency.)
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
EXCEPTIONS_PATH = REPO_ROOT / "sca-exceptions.json"


def load_exceptions() -> list[dict]:
    if not EXCEPTIONS_PATH.exists():
        return []

    try:
        parsed = json.loads(EXCEPTIONS_PATH.read_text())
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse {EXCEPTIONS_PATH}: {exc}") from exc

    if not isinstance(parsed, list):
        raise RuntimeError(f"{EXCEPTIONS_PATH} must be a JSON array of exception entries.")
    for entry in parsed:
        if not entry.get("id") or not entry.get("reason"):
            raise RuntimeError(
                f"{EXCEPTIONS_PATH} has an entry missing a required 'id' or 'reason' field: {entry}"
            )
    return parsed


def normalize_name(name: str) -> str:
    """Normalize a package name for comparison: lowercase, underscores and
    hyphens treated as equivalent (PEP 503-style normalization)."""
    return re.sub(r"[-_.]+", "-", name).strip().lower()


def parse_direct_dependencies(pyproject_path: Path) -> set[str]:
    """Pull the bare package names out of [project.dependencies], stripping
    version specifiers (>=, ==, <, etc.) and extras syntax (e.g.
    "uvicorn[standard]" -> "uvicorn")."""
    text = pyproject_path.read_text()

    try:
        import tomllib

        data = tomllib.loads(text)
        raw_deps = data.get("project", {}).get("dependencies", [])
    except Exception:
        # Fallback: crude regex-based extraction if tomllib parsing fails
        # for any reason (shouldn't happen on 3.12+, but keep this robust).
        match = re.search(r"dependencies\s*=\s*\[(.*?)\]", text, re.DOTALL)
        raw_deps = re.findall(r'"([^"]+)"', match.group(1)) if match else []

    names = set()
    for raw in raw_deps:
        # Strip extras: "uvicorn[standard]>=0.51.0" -> "uvicorn>=0.51.0"
        without_extras = re.sub(r"\[[^\]]*\]", "", raw)
        # Strip version specifiers and anything after them.
        name = re.split(r"[><=!~;\s]", without_extras, maxsplit=1)[0].strip()
        if name:
            names.add(normalize_name(name))
    return names


def run_pip_audit() -> dict:
    """Run pip-audit via uv and parse its JSON report from stdout.
    pip-audit exits non-zero when it finds vulnerabilities — that's normal
    and expected, not a failure of this script, so stdout is parsed
    regardless of exit code."""
    result = subprocess.run(
        ["uv", "run", "--with", "pip-audit", "pip-audit", "--format", "json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    stdout = result.stdout.strip()
    if not stdout:
        raise RuntimeError(
            "pip-audit produced no output on stdout to parse."
            + (f" stderr: {result.stderr.strip()}" if result.stderr else "")
        )

    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse pip-audit JSON output: {exc}") from exc


def main() -> int:
    direct_deps = parse_direct_dependencies(PYPROJECT_PATH)
    audit = run_pip_audit()
    exceptions = load_exceptions()
    exceptions_by_id = {e["id"].upper(): e for e in exceptions}
    used_exception_ids: set[str] = set()

    # pip-audit's JSON report has a top-level "dependencies" list, each
    # with a "vulns" list (empty when that package has no findings).
    dependencies = audit.get("dependencies", audit if isinstance(audit, list) else [])

    blocking = []
    report_only = []
    exempted = []

    for dep in dependencies:
        vulns = dep.get("vulns") or []
        if not vulns:
            continue

        pkg_name = dep.get("name", "")
        normalized = normalize_name(pkg_name)
        is_direct = normalized in direct_deps

        for vuln in vulns:
            fix_versions = vuln.get("fix_versions") or []
            vuln_id = vuln.get("id", "?")
            entry = {
                "package": pkg_name,
                "version": dep.get("version", "?"),
                "id": vuln_id,
                "fix_versions": fix_versions,
            }

            exception = exceptions_by_id.get(vuln_id.upper())
            if exception:
                used_exception_ids.add(exception["id"].upper())
                exempted.append({**entry, "exception": exception})
            elif is_direct and fix_versions:
                blocking.append(entry)
            else:
                report_only.append(entry)

    print("=== SCA Gate: backend (pip-audit) ===\n")

    print(f"BLOCKING (direct fix available) — {len(blocking)} finding(s)")
    if not blocking:
        print("  (none)")
    else:
        for e in blocking:
            fixes = ", ".join(e["fix_versions"])
            print(f"  - {e['package']}=={e['version']} [{e['id']}] -> fix: upgrade to {fixes}")

    print(
        f"\nREPORT ONLY (no safe fix without forcing a child dependency) — {len(report_only)} finding(s)"
    )
    if not report_only:
        print("  (none)")
    else:
        for e in report_only:
            if e["fix_versions"]:
                fixes = ", ".join(e["fix_versions"])
                print(
                    f"  - {e['package']}=={e['version']} [{e['id']}] -> transitive-only fix available ({fixes}), "
                    "parent dependency unchanged"
                )
            else:
                print(f"  - {e['package']}=={e['version']} [{e['id']}] -> no fix published yet")

    print(f"\nEXEMPTED (covered by sca-exceptions.json) — {len(exempted)} finding(s)")
    if not exempted:
        print("  (none)")
    else:
        for e in exempted:
            exc = e["exception"]
            print(
                f"  - {e['package']}=={e['version']} [{e['id']}] -> exempted by {exc['id']} "
                f"(added {exc.get('addedDate', '?')} by {exc.get('addedBy', '?')})"
            )
            print(f"      reason: {exc['reason']}")

    stale = [e for e in exceptions if e["id"].upper() not in used_exception_ids]
    if stale:
        print(
            f"\nWARNING: {len(stale)} exception(s) in sca-exceptions.json matched no current "
            "finding — the underlying issue may already be fixed upstream. Consider removing:"
        )
        for e in stale:
            print(f"  - {e['id']} ({e.get('package', '?')})")

    print()

    if blocking:
        print(
            f"SCA gate FAILED: {len(blocking)} finding(s) have a fix available by updating a direct dependency.",
            file=sys.stderr,
        )
        return 1

    print("SCA gate passed (report-only and exempted findings, if any, do not block CI).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
