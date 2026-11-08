"""Sequence the remaining checks after the existing full comparison finishes.

This never restarts validation and never merges or accepts a memory regression.
The full report is written only after all timed workers and their comparisons.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

WORK = Path(__file__).resolve().parent
ROOT = WORK.parents[1]
FULL = WORK / 'full-comparison'
STATUS = WORK / 'post-full-checks-status.json'
assert not STATUS.exists()


def status(stage, **details):
    temporary = STATUS.with_suffix('.tmp')
    temporary.write_text(json.dumps(dict(stage=stage, time=time.time(), **details), indent=2) + '\n')
    temporary.replace(STATUS)
    print(stage, flush=True)


def run(script, *arguments):
    path = WORK / script
    with (WORK / (path.stem + '-sequenced.log')).open('x') as log:
        subprocess.run([sys.executable, str(path), *arguments], cwd=ROOT,
                       stdout=log, stderr=subprocess.STDOUT, check=True)


try:
    status('waiting_for_full_comparison')
    deadline = time.monotonic() + 5400
    while not (FULL / 'report.json').exists():
        outcomes = [json.loads(p.read_text()) for p in FULL.glob('*.outcome.json')]
        if any(not row['complete'] for row in outcomes):
            raise RuntimeError('Existing full worker failed; preserve evidence and investigate')
        if time.monotonic() >= deadline:
            raise TimeoutError('Observation deadline reached; do not restart the existing full run')
        time.sleep(5)
    full = json.loads((FULL / 'report.json').read_text())
    completed = json.loads((FULL / 'completed.json').read_text())
    assert completed == {'workers': 148, 'completed': True}
    assert full['regression_passed'] and len(full['pairs']) == 74
    assert all(row['passed'] and all(row['checks'].values()) for row in full['pairs'])
    scores = full['measured_scores']
    assert all(scores['main-' + res] == scores['candidate-' + res] for res in ('1m', '2m'))
    status('full_comparison_passed', pairs=74, measured_scores_identical=True)
    run('run_native_integration.py')
    native = json.loads((WORK / 'native-integration-tests.json').read_text())
    assert native['passed'] and len(native['rows']) == 2
    assert all(row['passed'] == 34 and row['skipped'] == 0 for row in native['rows'])
    status('native_integration_passed', tests_per_backend=34)
    run('memory_review.py', '--output', str(WORK / 'memory-review'))
    memory = json.loads((WORK / 'memory-review/report.json').read_text())
    assert memory['workers'] == 12
    assert all(row['fields_identical'] and row['returned_bytes_identical']
               for row in memory['cases'].values())
    status('memory_review_complete_pending_assessment', workers=12)
except Exception as error:
    status('failed_requires_review', error=repr(error))
    raise
