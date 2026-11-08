"""Run the native-worker tests omitted when custom build paths are unspecified."""
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

WORK = Path(__file__).resolve().parent
ROOT = WORK.parents[1]
nodes = json.loads((WORK / 'native-integration-nodeids.json').read_text())
assert len(nodes) == 34 and len(set(nodes)) == 34
rows = []
for backend, package in [('openmp', 'installed-wheel'), ('serial', 'qualified-serial-package')]:
    build = WORK / ('qualified-' + backend)
    env = dict(os.environ, PYTHONPATH=f'{WORK/package}:{ROOT}/validation:{ROOT}/tests',
        OMP_NUM_THREADS='2' if backend == 'openmp' else '1', OMP_DYNAMIC='FALSE',
        OPENBLAS_NUM_THREADS='1', DTCC_QES_STUDY_EXECUTABLE=str(build / 'vertical_grid_study'),
        DTCC_QES_MONITOR_EXECUTABLE=str(build / 'check_monitor'),
        DTCC_QES_NATIVE_TEST=str(build / 'check_safety'),
        DTCC_QES_RUNNER_TEST=str(build / 'check_runner'),
        DTCC_QES_PHYSICS_TEST=str(build / 'check_physics'))
    output = WORK / f'pytest-native-integration-{backend}.xml'
    with (WORK / f'pytest-native-integration-{backend}.log').open('x') as log:
        subprocess.run([sys.executable, '-m', 'pytest', *nodes, '-q', '-W', 'error', '--tb=short',
            '--junitxml=' + str(output)], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    root = ET.parse(output).getroot()
    tests = list(root.iter('testcase'))
    assert len(tests) == 34
    assert not any(node.tag in ('failure', 'error', 'skipped') for node in root.iter())
    rows.append(dict(backend=backend, package=str(WORK/package), passed=34, skipped=0))
    print(backend, '34 passed, no skips', flush=True)
(WORK / 'native-integration-tests.json').write_text(json.dumps(dict(passed=True, rows=rows), indent=2) + '\n')
