"""Immutable campaign stages and predecessor gates, independent of physics models."""
import json
import os
from pathlib import Path

from .evidence import clean, file_hash


def reserve_stage(root, phase, *, limits):
    """Consume a stage by atomic directory creation; an attempt cannot be retried."""
    root = Path(root)
    phases = list(limits)
    if phase not in limits:
        raise ValueError(f"Unknown campaign stage: {phase}")
    if any((root / later).exists() for later in phases[phases.index(phase)+1:]):
        raise ValueError("Cannot run an earlier stage after a later stage was reserved")
    folder = root / phase
    folder.mkdir(parents=True, exist_ok=False)
    return folder


def require_predecessor(root, phase, frozen, *, limits, predecessors):
    """Require a complete, passing predecessor from the same frozen identity."""
    if phase not in limits:
        raise ValueError(f"Unknown campaign stage: {phase}")
    previous = predecessors.get(phase)
    if previous:
        folder = Path(root) / previous
        manifest = json.loads((folder / "manifest.json").read_text())
        report = json.loads((folder / "report.json").read_text())
        checks = report.get("checks", {})
        if (manifest.get("identity") != frozen or report.get("decision") != "pass"
                or not checks or not all(value is True for value in checks.values())):
            raise ValueError(f"{previous} advance gate is closed or belongs to another identity")
        if report.get("attempts") != limits[previous]:
            raise ValueError("Predecessor did not complete the reserved attempt sequence")
        outcome = folder / "outcome.json"
        if outcome.exists() and json.loads(outcome.read_text()).get("complete") is not True:
            raise ValueError("Predecessor worker failed after writing its report")
        for name, expected in report.get("evidence_hashes", {}).items():
            path = (folder / name).resolve()
            if not path.is_relative_to(folder.resolve()):
                raise ValueError("Predecessor evidence path escapes its stage")
            if file_hash(path) != expected:
                raise ValueError("Predecessor evidence changed")
    return previous


def journal(folder, report, *, plan=None, repo=None):
    """Preserve a worker report if a later supervisor failure needs recording."""
    folder = Path(folder)
    evidence = {str(p.relative_to(folder)): file_hash(p) for p in folder.rglob("*")
                if p.is_file() and p.name != "report.json" and not p.name.endswith(".log")}
    report = {**report, "evidence_hashes": evidence}
    payload = json.dumps(clean(report), indent=2, allow_nan=False) + "\n"
    path = folder / "report.json"
    if path.exists():
        path = folder / "supervisor-failure.json"
    # Exclusive creation also prevents two supervisors from replacing evidence.
    with path.open("x") as handle:
        handle.write(payload)
    if plan is not None:
        failed = [k for k, v in report["checks"].items() if not v]
        anchor = Path(repo) if repo is not None else Path(plan).parent
        link = os.path.relpath(path.resolve(), anchor.resolve())
        with Path(plan).open("a") as out:
            out.write(f'\n### Integrated validation: {folder.name}\n\n'
                      f'Decision: **{report["decision"]}**. Started native attempts: {report["attempts"]}. '
                      f'Unmet checks: {", ".join(failed) or "none"}. '
                      f'[Evidence]({link}). '
                      f'{report.get("conclusion", "The next stage requires this stage to pass.")}\n')
    return path
