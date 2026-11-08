"""Copy selected qualification evidence to a fresh durable local output root."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

WORK = Path(__file__).resolve().parent


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(2**20), b''):
            h.update(block)
    return h.hexdigest()


def archive(destination):
    assessment = json.loads((WORK / 'memory-review/assessment.json').read_text())
    assert assessment['accepted'], 'Memory review must be resolved before archiving the accepted release'
    assert json.loads((WORK / 'full-comparison/report.json').read_text())['regression_passed']
    assert json.loads((WORK / 'native-integration-tests.json').read_text())['passed']
    destination.mkdir(parents=True, exist_ok=False)
    files = set()
    # Keep complete results and corresponding installed packages, without
    # copying disposable build trees or unrelated research archives.
    for name in ('full-comparison', 'memory-review', 'memory-review-e', 'combined-main', 'combined-candidate',
                 'policy-workers', 'dist', 'final-dist', 'installed-wheel', 'final-wheel',
                 'baseline-package', 'baseline-serial-package',
                 'qualified-openmp-package', 'qualified-serial-package'):
        folder = WORK / name
        assert folder.is_dir(), name
        files.update(p for p in folder.rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc')
    for suffix in ('*.json', '*.xml', '*.log', '*.py', '*.cpp', '*.npz', '*.txt'):
        files.update(WORK.glob(suffix))
    for name in ('baseline-openmp', 'baseline-serial', 'qualified-openmp', 'qualified-serial', 'sanitizers'):
        folder = WORK / name
        for pattern in ('CMakeCache.txt', 'solver-policy-identity.txt', 'ctest.xml', '_qes*.so',
                        'Testing/Temporary/LastTest.log', 'CMakeFiles/*/CMakeCXXCompiler.cmake'):
            files.update(p for p in folder.glob(pattern) if p.is_file())
    files.update((WORK / 'candidate-tests').glob('ctest*.xml'))
    entries = []
    for source in sorted(files):
        relative = source.relative_to(WORK)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        source_hash = sha(source)
        shutil.copy2(source, target)
        assert sha(target) == source_hash
        entries.append(dict(path=str(relative), bytes=target.stat().st_size, sha256=source_hash))
    index = dict(schema='ready-integration-archive-v1', source=str(WORK),
                 destination=str(destination), files=entries,
                 bytes=sum(item['bytes'] for item in entries),
                 retrieval='Paths in this index are relative to this archive root. Original absolute execution paths remain unchanged in the raw manifests. Git commits and the final source distribution preserve the source; restore scripts under build/ready-integration in that checkout when reproducing build-oriented commands.',
                 excluded='Disposable compiler objects, unrelated research archives and external AIJ input files; input hashes remain in the full comparison manifest.')
    (destination / 'index.json').write_text(json.dumps(index, indent=2) + '\n')
    print(json.dumps(dict(destination=str(destination), files=len(entries), bytes=index['bytes'],
                          index_sha256=sha(destination / 'index.json'))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    archive(parser.parse_args().destination.resolve())
