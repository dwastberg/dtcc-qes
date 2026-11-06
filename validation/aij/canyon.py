"""Private canyon validation adapter; no physical defaults or solver policy."""
from copy import deepcopy
from dataclasses import replace
import hashlib
from time import perf_counter

import numpy as np
from dtcc_qes import _qes, wind

from .evidence import digest, file_hash
from .stage_sampling import StageSampler


class CanyonSession:
    """Cache geometry only, using explicit legacy solver control for every call."""
    def __init__(self):
        self.runner = self.prepared = self.geometry = self.key = None
        self.preparations = 0

    def close(self):
        self.runner = self.prepared = self.geometry = self.key = None

    def run(self, args, *, model="legacy", capture=True, trace=False,
            baseline_turbulence=False, stages=True):
        started = perf_counter()
        if model not in ("legacy", "horizontal_reference_v1", "joined_v1"):
            raise ValueError("Unknown research canyon model: " + str(model))
        settings = dict(args["run"])
        solver = settings.pop("solver")
        turbulence = settings.pop("turbulence", None)
        if solver.mode != "legacy":
            raise ValueError("Canyon validation requires explicit legacy solver control")
        city, profile = args["city"], args["profile"]
        source = hashlib.sha256(city.to_proto().SerializeToString(deterministic=True)).hexdigest()
        key = digest(dict(city=source, settings=settings, turbulence=turbulence,
            reference_height=profile.reference_height, roughness_length=profile.roughness_length,
            library=wind._dtcc_version(), native=file_hash(_qes.__file__)))
        hit = self.runner is not None and key == self.key
        preparation_seconds = 0.
        if not hit:
            self.close()
            begin = perf_counter()
            grid = wind._validate_grid(settings["resolution"], settings.get("bounds"),
                settings.get("horizontal_padding", 20.), settings.get("vertical_clearance", 20.),
                settings.get("max_cells", 20_000_000), vertical_grid=settings.get("vertical_grid"))
            geometry, prepared = wind._prepare_city(city, profile, grid, settings.get("terrain"),
                settings.get("height_policy", "measured"), turbulence=turbulence is not None,
                footprints=settings.get("footprints"), parameterizations=settings.get("parameterizations", wind.Parameterizations()))
            runner = _qes.WindRunner()
            extra = {}
            if turbulence is not None:
                native = _qes.TurbulenceSettings(); native.enabled = True
                native.mixing_length_method = turbulence.qes_method
                extra["turbulence"] = native
            runner.prepare(prepared.grid, prepared.model, **prepared.arrays,
                           dz_layers=prepared.dz_layers, **extra)
            self.geometry, self.prepared, self.runner, self.key = geometry, prepared, runner, key
            self.preparations += 1
            preparation_seconds = perf_counter() - begin
        else:
            wind._prepare_profile(self.prepared, profile)
        prepared = replace(self.prepared, domain=deepcopy(self.prepared.domain))
        sampler = StageSampler(args["probes"].xyz) if stages else None
        cells = sampler(self.geometry, prepared) if sampler is not None else []
        result = wind._solve_prepared(self.geometry, prepared, profile, solver,
            vertical_grid=settings.get("vertical_grid"), turbulence_spec=turbulence,
            height_policy=settings.get("height_policy", "measured"), _runner=self.runner,
            _experiment=dict(canyon_model=model, canyon_capture=capture, canyon_trace_roof=trace,
                canyon_baseline_turbulence=baseline_turbulence, cells=cells, diagnose_flux=True))
        nz, ny, nx = prepared.domain["shape"]
        h = prepared.resolution
        faces = prepared.domain["vertical_grid"]["effective_faces"]
        width, depth, height = (nx-2)*h, (ny-2)*h, float(faces[-2]-faces[0])
        area = 2*height*(width+depth)+width*depth
        result.metadata["experiment"].update(cache_hit=hit, cache_key=key,
            input_geometry_sha256=source, stage_cells=cells, boundary_flux_area=area,
            preparation_seconds=preparation_seconds,
            solve_call_seconds=perf_counter()-started-preparation_seconds)
        result.metadata["timings"]["city_preparation_seconds"] = preparation_seconds
        result.metadata["timings"]["public_call_seconds"] = perf_counter()-started
        return result, None if sampler is None else sampler.sample(result)


def native_mass(result, uref):
    maximum, rms, top, boundary, top_boundary, solid = result.metadata["experiment"]["mass"]
    length = min(result.resolution, float(np.min(np.diff(result.z_faces))))
    return dict(interior=dict(rms=rms*length/uref, maximum=maximum*length/uref),
                top=dict(maximum=top*length/uref), solid_normal_max=solid/uref,
                net_boundary_flux=boundary+top_boundary)


def mass_gate(actual, parent, uref, area):
    checks = dict(solid=actual["solid_normal_max"] <= 1e-6)
    for band in ("interior", "top"):
        checks[band] = all(actual[band][key] <= max(1.1*value, 1e-6 if key == "rms" else 1e-4)
                           for key, value in parent[band].items())
    checks["boundary_flux"] = abs(actual["net_boundary_flux"])/(uref*area) <= max(
        1.1*abs(parent["net_boundary_flux"])/(uref*area), 1e-6)
    return checks
