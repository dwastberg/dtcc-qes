"""Optional, bounds-based QES datasets registered by importing this module."""

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Literal

import numpy as np
from pydantic import ConfigDict, Field as Argument, model_validator

from dtcc_core import datasets as core_datasets
from dtcc_core.datasets import DatasetBaseArgs, DatasetDescriptor
from dtcc_core.model import Bounds, City, Field, FieldSlice, Transform

from . import __version__, wind
from ._dataset_city import prepare_city

__all__ = ["QESWindArgs", "QESWindDataset"]


class QESWindArgs(DatasetBaseArgs):
    """A city selection in EPSG:3006 and one steady wind condition."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    source: Literal["LM", "OSM"] = "LM"
    smallest_building_size: float = Argument(15.0, ge=0, description="Source area filter in square metres.")
    min_building_detail: float = Argument(0.5, gt=0, description="Core footprint cleaning/merging scale in metres.")
    wind_speed: float = Argument(5.0, ge=0, description="Wind speed in m/s at reference_height.")
    wind_direction: float = Argument(270.0, ge=0, lt=360, description="Meteorological direction FROM, clockwise from north.")
    reference_height: float = Argument(10.0, gt=0)
    roughness_length: float = Argument(0.1, gt=0)
    resolution: float = Argument(2.0, gt=0, description="Uniform solver cell spacing in metres.")
    horizontal_padding: float = Argument(20.0, ge=0)
    vertical_clearance: float = Argument(20.0, ge=0)
    max_cells: int = Argument(200_000_000, ge=1)
    tolerance: float = Argument(1e-4, gt=0)
    max_iterations: int = Argument(1000, ge=1)
    raise_on_nonconvergence: bool = False
    product: Literal["field", "slice"] = "field"
    slice_axis: Literal["x", "y", "z"] = "z"
    slice_position: float = Argument(0.5, ge=0, le=1, description="Relative position within the cell-centre extent.")
    slice_height: float | None = Argument(
        None, ge=0,
        description="Slice height in metres above flat ground; overrides slice_axis to 'z' and slice_position.",
    )
    slice_resolution: int = Argument(128, ge=2, le=1024, description="Samples per display axis, independent of solver spacing.")

    @model_validator(mode="after")
    def validate_solver_options(self):
        if not np.isfinite(self.bounds).all():
            raise ValueError("bounds must contain finite coordinates")
        if self.slice_height is not None:
            self.slice_axis = "z"
        # Reuse the solver's float32 and integer limits before fetching data.
        wind._validate_condition(self.wind_speed, self.wind_direction,
                                 self.reference_height, self.roughness_length)
        wind._validate_grid(self.resolution, None, self.horizontal_padding,
                            self.vertical_clearance, self.max_cells)
        wind._validate_solver(self.tolerance, self.max_iterations, self.raise_on_nonconvergence)
        return self

    def wind_options(self):
        return dict(speed=self.wind_speed, direction=self.wind_direction,
                    reference_height=self.reference_height, roughness_length=self.roughness_length,
                    resolution=self.resolution, horizontal_padding=self.horizontal_padding,
                    vertical_clearance=self.vertical_clearance, max_cells=self.max_cells,
                    tolerance=self.tolerance, max_iterations=self.max_iterations,
                    raise_on_nonconvergence=self.raise_on_nonconvergence)


class QESWindDataset(DatasetDescriptor):
    """Steady QES wind over a fetched, conditioned, flat-ground city."""

    name = "qes_wind"
    title = "QES Urban Wind"
    description = "Steady neutral wind over conditioned building footprints on flat ground using QES-Winds."
    ArgsModel = QESWindArgs
    data_category = "simulation"
    result_kind = "vector_field"
    python_return_type = "dtcc_core.model.VolumeGrid"
    source_service = "dtcc-qes"
    default_crs = "EPSG:3006"
    generated_by = {"package": "dtcc-qes", "version": __version__, "license": "GPL-3.0-only"}
    source = [{"name": "dtcc_core.datasets.city", "role": "upstream geometry and heights"}]
    license = "Input data terms are inherited from the selected city sources."
    processing_steps = [
        "Fetch a LOD1 city with LOD0 footprints and estimated heights",
        "Fill courtyards and clean/merge footprints using dtcc-core",
        "Flatten terrain and solve one steady QES wind condition",
    ]
    presentation_limitations = [
        "Flat ground, constant-height blocks and stair-step cells; courtyards are filled.",
        "Convergence measures multiplier change, not a mass-conservation residual.",
    ]

    def describe(self):
        metadata = super().describe()
        metadata["products"] = [
            {"name": "field", "python_return_type": "dtcc_core.model.VolumeGrid", "formats": []},
            {"name": "slice", "python_return_type": "dtcc_core.model.FieldSlice", "formats": []},
        ]
        metadata["field_names"] = ["velocity", "speed", "cell_flags"]
        return metadata

    def __call__(self, **kwargs):
        # build attaches realization-specific context; the base implementation
        # would replace it with descriptor-only context after the solve.
        return self.build(self.validate(kwargs))

    def validate(self, kwargs):
        values = dict(kwargs)
        bounds = values.get("bounds")
        if isinstance(bounds, Bounds):
            names = (("xmin", "ymin", "xmax", "ymax") if bounds.zmin == bounds.zmax == 0
                     else ("xmin", "ymin", "zmin", "xmax", "ymax", "zmax"))
            values["bounds"] = [getattr(bounds, name) for name in names]
        return self.ArgsModel(**values)

    def build(self, args: QESWindArgs):
        xy = list(args.bounds) if len(args.bounds) == 4 else [args.bounds[i] for i in (0, 1, 3, 4)]
        source_city = core_datasets.city(
            bounds=xy, source=args.source, smallest_building_size=args.smallest_building_size,
            lod="lod1", strict_live=args.strict_live,
        )
        if not isinstance(source_city, City):
            raise TypeError("The city dataset must return a dtcc_core.model.City")
        upstream = source_city.dataset_context
        if upstream is not None and upstream.health and upstream.health.get("partial_result"):
            raise ValueError("QES wind requires a complete city; the upstream dataset returned a partial result")
        city, bounds, preparation = prepare_city(source_city, args)
        solved = wind.run(city, **args.wind_options(), bounds=bounds,
                          terrain=bounds[2], height_policy="allow_estimated")
        obj = solved.to_dtcc() if args.product == "field" else _field_slice(solved, args)
        context = self.create_context(args)
        context.metadata.python_return_type = f"dtcc_core.model.{type(obj).__name__}"
        context.provenance.generated_at = datetime.now(timezone.utc).isoformat()
        if upstream is not None:
            context.provenance.derived_from.append(upstream.model_dump(mode="json"))
            context.metadata.license = upstream.metadata.license
        context.provenance.processing_steps.append({
            "operation": "qes_wind", "preparation": preparation,
            "simulation": solved.metadata, "diagnostics": asdict(solved.diagnostics),
        })
        context.health = {"converged": solved.diagnostics.converged}
        if not solved.diagnostics.converged:
            context.warnings.append("QES solver did not converge; inspect the recorded diagnostics.")
        obj.dataset_context = context
        return obj


def _nearest(axis, positions):
    """Nearest sample indices, choosing the lower index on ties."""
    right = np.clip(np.searchsorted(axis, positions), 0, len(axis) - 1)
    left = np.maximum(right - 1, 0)
    return np.where(np.abs(positions - axis[left]) <= np.abs(axis[right] - positions), left, right)


def _field_slice(result, args):
    axes = (result.x, result.y, result.z)
    normal = "xyz".index(args.slice_axis)
    plane_axes = tuple(i for i in range(3) if i != normal)
    target = axes[normal][0] + args.slice_position * (axes[normal][-1] - axes[normal][0])
    if args.slice_height is not None:
        domain_height = result.metadata["domain"]["effective_bounds"][5] - result.origin[2]
        if args.slice_height > domain_height:
            raise ValueError(f"slice_height must be within the simulation domain (0 to {domain_height:g} metres)")
        target = args.slice_height
    normal_index = int(_nearest(axes[normal], target))
    position = args.slice_position
    if args.slice_height is not None:
        position = ((float(axes[normal][normal_index]) - float(axes[normal][0])) /
                    (float(axes[normal][-1]) - float(axes[normal][0])))
    samples = [np.linspace(axes[i][0], axes[i][-1], args.slice_resolution) for i in plane_axes]
    plane = np.stack(np.meshgrid(*samples, indexing="ij"), axis=-1).reshape(-1, 2)
    points = np.empty((len(plane), 3))
    points[:, plane_axes] = plane
    points[:, normal] = axes[normal][normal_index]
    indices = [_nearest(axis, points[:, i]) for i, axis in enumerate(axes)]
    velocity = result.velocity[indices[2], indices[1], indices[0]].copy()
    flags = result.cell_flags[indices[2], indices[1], indices[0]].copy()
    points += np.asarray(result.origin)
    physical_bounds = result.metadata["domain"]["effective_bounds"]
    field_slice = FieldSlice(
        name="qes_wind_slice", points=points, slice_axis=args.slice_axis,
        slice_position=position, resolution=args.slice_resolution, axes=plane_axes,
        crs=result.crs, transform=Transform(srs=result.crs or ""),
        domain_bounds=Bounds(**dict(zip(("xmin", "ymin", "zmin", "xmax", "ymax", "zmax"), physical_bounds))),
        metadata_payload={"dataset": "qes_wind", "sampling": "nearest_cell",
                          "slice_coordinate": float(points[0, normal]),
                          "slice_height": float(points[0, 2] - result.origin[2]) if normal == 2 else None,
                          "requested_slice_height": args.slice_height,
                          "solid_cell_flags": [0, 2]},
    )
    for name, values, dim, unit in (
        ("velocity", velocity, 3, "m/s"),
        ("speed", np.linalg.norm(velocity.astype(np.float64), axis=1), 1, "m/s"),
        ("cell_flags", flags, 1, "1"),
    ):
        field_slice.add_field(Field(name=name, values=values, dim=dim, unit=unit, association="sample"))
    return field_slice
