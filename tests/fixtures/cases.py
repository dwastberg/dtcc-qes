"""Reference case definitions for dtcc-qes.

Each case is defined once, here, and used both by ``tools/make_reference.py``
(which writes QES XML and runs the standalone QES executable) and by the tests
(which build the same configuration through the Python API and compare the
results against the stored reference arrays).

All geometry is given in the *local simulation frame*: metres, origin at the
south-west corner of the physical domain, z measured from the flat ground.
Polygon vertices are listed clockwise, which is QES's convention (see
``RectangularBuilding.h``), and are not closed: QES closes the ring itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent
REFERENCE_DIR = FIXTURE_DIR / "reference"


@dataclass(frozen=True)
class Grid:
    nx: int  # physical cells in x
    ny: int  # physical cells in y
    nz: int  # physical cells in z
    cell_size: float  # metres, equal in x, y and z


@dataclass(frozen=True)
class Wind:
    speed: float  # m/s at reference_height
    direction: float  # degrees clockwise from north, direction wind comes from
    reference_height: float  # metres above ground
    roughness_length: float  # metres
    # QES needs one sensor; the profile is a neutral log law (boundaryLayerFlag 1).
    sensor_x: float
    sensor_y: float
    timestamp: str = "2020-01-01T00:00:00"


@dataclass(frozen=True)
class Building:
    id: int
    vertices: tuple[tuple[float, float], ...]  # clockwise, not closed
    height: float  # metres above base
    base_height: float = 0.0


@dataclass(frozen=True)
class Parameterizations:
    """QES BuildingsParams defaults (BuildingsParams.h)."""

    wall_roughness: float = 0.001
    rooftop_flag: int = 1
    upwind_cavity_flag: int = 2
    street_canyon_flag: int = 1
    street_intersection_flag: int = 0
    wake_flag: int = 2
    high_rise_flag: int = 0
    sidewall_flag: int = 1


@dataclass(frozen=True)
class Solver:
    tolerance: float = 1e-5
    max_iterations: int = 500


@dataclass(frozen=True)
class Case:
    name: str
    grid: Grid
    wind: Wind
    buildings: tuple[Building, ...] = ()
    parameterizations: Parameterizations = field(default_factory=Parameterizations)
    solver: Solver = field(default_factory=Solver)
    # Fixed model settings for this milestone.
    log_law_flag: int = 0
    mesh_type_flag: int = 0  # stair-step
    halo_x: float = 0.0
    halo_y: float = 0.0

    @property
    def extent(self) -> tuple[float, float, float]:
        g = self.grid
        return (g.nx * g.cell_size, g.ny * g.cell_size, g.nz * g.cell_size)


_GRID = Grid(nx=40, ny=30, nz=20, cell_size=2.0)
_WIND = Wind(
    speed=5.0,
    direction=270.0,
    reference_height=10.0,
    roughness_length=0.1,
    sensor_x=11.0,
    sensor_y=31.0,
)

FLAT = Case(name="flat", grid=_GRID, wind=_WIND)

ONE_BUILDING = Case(
    name="one_building",
    grid=_GRID,
    wind=_WIND,
    buildings=(
        Building(
            id=0,
            # 10 m x 10 m footprint, clockwise from the south-west corner.
            vertices=((30.0, 25.0), (30.0, 35.0), (40.0, 35.0), (40.0, 25.0)),
            height=8.0,
        ),
    ),
)

CASES: dict[str, Case] = {c.name: c for c in (FLAT, ONE_BUILDING)}


def reference_path(case: Case | str) -> Path:
    name = case if isinstance(case, str) else case.name
    return REFERENCE_DIR / f"{name}.npz"
