"""Immutable, checksummed snapshots of validation evidence."""

import hashlib
import json
import re
import shutil
from pathlib import Path


def archive_results(root, label, revision, output, figures, records, fingerprint):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", label):
        raise ValueError("archive label must contain only letters, digits, _ or -")
    destination = Path(root) / "archive" / f"{label}-{revision}"
    destination.mkdir(parents=True, exist_ok=False)
    sources = [(Path(output) / "summary.txt", Path("summary.txt"))]
    sources += [(Path(p), Path(p).name) for p in figures]
    for case, key in sorted(set(records)):
        for extension in ("json", "npz"):
            relative = Path("runs") / case / f"{key}.{extension}"
            sources.append((Path(root) / relative, relative))
    for source, relative in sources:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    manifest = {
        "revision": revision, "fingerprint": fingerprint,
        "sha256": {str(p.relative_to(destination)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted(destination.rglob("*")) if p.is_file()},
    }
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return destination
