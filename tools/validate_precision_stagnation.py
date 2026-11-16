"""Validate the precision-floor stop on exported domains using a native face-error probe.

Use a staged candidate package on PYTHONPATH. Demo export fetches live city
geometry; AIJ export uses the archived .spec.json requests and local AIJ data.
Existing successful results are retained when resuming a campaign.
"""
import argparse
import json
import shlex
import subprocess
from pathlib import Path

import numpy as np
from dtcc_qes import wind, comfort_dataset as cd

ROOT = Path(__file__).resolve().parents[1]


def build_probe(build_dir, destination):
    """Use exactly the compiler, includes, arithmetic flags and libraries of check_stop_rule."""
    build_dir = build_dir.resolve()
    flags = (build_dir / 'CMakeFiles/check_stop_rule.dir/flags.make').read_text()
    link = shlex.split((build_dir / 'CMakeFiles/check_stop_rule.dir/link.txt').read_text())

    def flag(name):
        return shlex.split(next(line.split(' = ', 1)[1] for line in flags.splitlines()
                                if line.startswith(name + ' = ')))

    obj = build_dir / 'precision_probe.o'
    subprocess.run([link[0], *flag('CXX_DEFINES'), *flag('CXX_INCLUDES'), *flag('CXX_FLAGS'),
                    '-c', str(ROOT / 'tools/precision_stagnation_probe.cpp'), '-o', str(obj)], check=True)
    link[link.index('CMakeFiles/check_stop_rule.dir/tests/native/check_stop_rule.cpp.o')] = str(obj)
    link[link.index('-o') + 1] = str(destination.resolve())
    subprocess.run(link, cwd=build_dir, check=True)


def export(prepared, profile, path):
    """Write owned geometry/profile inputs in the native probe's text format."""
    wind._prepare_profile(prepared, profile)
    condition = wind._native_condition(prepared.domain['profile'])
    grid, model = prepared.grid, prepared.model
    lines = [' '.join(map(str, [grid.nx, grid.ny, grid.nz, grid.cell_size]))]

    def vector(values):
        values = np.asarray(values).ravel()
        lines.append(str(len(values)) + ' ' + ' '.join(map(str, values)))

    vector([] if prepared.dz_layers is None else prepared.dz_layers)
    names = ['roughness_length', 'sensor_x', 'sensor_y', 'exposed_faces', 'wall_roughness',
             'rooftop_flag', 'upwind_cavity_flag', 'street_canyon_flag', 'street_intersection_flag',
             'wake_flag', 'high_rise_flag', 'sidewall_flag', 'tall_buildings_flag', 'angle_fade']
    values = [getattr(model, name) for name in names]
    lines.append(' '.join(str(int(value)) if isinstance(value, bool) else str(value) for value in values))
    for name in ['vertices', 'offsets', 'ids', 'heights', 'base_heights', 'ring_offsets']:
        vector(prepared.arrays.get(name, []))
    lines.append(f'{condition.speed} {condition.direction} {condition.reference_height}')
    vector(condition.layer_u)
    vector(condition.layer_v)
    path.write_text('\n'.join(lines) + '\n')


def export_demo(output):
    # Stop after the production dataset's exact geometry preparation, before weather or solving.
    from unittest.mock import patch

    class Captured(Exception):
        pass

    def capture(*args, **kwargs):
        prepared, profile = args[1:3]
        for direction in cd.DIRECTIONS:
            export(prepared, profile.with_direction(float(direction)),
                   output / f'demo-r{resolution:g}-d{direction:g}.txt')
        raise Captured()

    with patch.object(cd, 'fetch_climate', return_value=None), patch.object(wind, '_prepared_model', capture):
        for resolution in (1., 2.):
            try:
                cd.QESWindComfortDataset().build(cd.QESWindComfortArgs(
                    bounds=[319845, 6397785, 320095, 6398035], resolution=resolution,
                    max_cells=50_000_000, source='LM', criterion='city_of_london', strict_live=True))
            except Captured:
                pass


def export_aij(output):
    from validation.aij import runner
    from validation.aij.runspec import RunSpec

    requests = sorted(output.glob('*.spec.json'))
    if not requests:
        raise ValueError('AIJ export requires archived .spec.json requests in the output directory')
    for path in requests:
        spec = RunSpec.from_dict(json.loads(path.read_text()))
        args = runner.inputs(spec)
        with wind.prepare(args['city'], args['profile'], **args['run']) as model:
            export(model._prepared, args['profile'], path.with_name(path.name.replace('.spec.json', '.txt')))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--probe', type=Path, required=True)
    parser.add_argument('--build-dir', type=Path, help='Compile the probe against this CMake Makefiles build first')
    parser.add_argument('--suite', choices=('demo', 'aij'), default='demo')
    parser.add_argument('--pattern', default='*.txt')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--export-only', action='store_true')
    modes.add_argument('--run-only', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.build_dir:
        build_probe(args.build_dir, args.probe)
    if not args.run_only:
        (export_demo if args.suite == 'demo' else export_aij)(args.output)
    if args.export_only:
        return
    paths = sorted(args.output.glob(args.pattern), key=lambda path: ('d67.5' not in path.stem, path.name))
    if not paths:
        raise ValueError('No exported domains match the requested pattern')
    for path in paths:
        result = path.with_suffix('.json')
        if result.exists():
            if not json.loads(result.read_text())['pass']:
                raise RuntimeError(f'Existing validation failure: {result}')
            continue
        status = subprocess.run([str(args.probe.resolve()), str(path), str(result)])
        print(result.name, result.read_text() if result.exists() else f'exit {status.returncode}', flush=True)
        if status.returncode:
            raise RuntimeError(f'Validation failed: {path}')


if __name__ == '__main__':
    main()
