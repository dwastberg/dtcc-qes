"""Measurement points, approach-flow profiles and measured results from the AIJ spreadsheets.

Sheet layouts and units are documented in AIJ_VALIDATION_PLAN.md (F9, F10).
Empty and ``'-'`` cells are missing data: any cell that is not a number is NaN.
Directions are meteorological degrees (see ``conventions``).
"""

from typing import NamedTuple

import numpy as np
import xlrd

from . import CASE_D_XLS, CASE_E_XLS
from .conventions import D_ANGLES, D_LABELS, E_LABELS, E_STATES, d_direction, e_direction

U_H = 6.65  # m/s, Case D inflow speed at the tower height (Inflow!C17)
H_MODEL_MM = 250.0  # Case D tower height in the model
Z_R = 250.0  # m, Case E boundary-layer height at full scale (Inflow!C20)
U_R = 7.8  # m/s, Case E inflow speed at Z_R (Inflow!C21)
E_REFERENCE_HEIGHT = 15.9  # m, Case E normalisation height (the Niigata station height)
E_QUANTUM = 0.019820405  # every Case E value is a multiple: U/U_R rounded to 0.01, divided by ~0.5045


class Points(NamedTuple):
    ids: np.ndarray  # int, the AIJ point number
    xyz: np.ndarray  # (n, 3) full-scale metres in the AIJ frame


class Measurements(NamedTuple):
    """Measured speed ratios at the probes; ``values[point, direction]``, NaN where missing."""
    case: str  # "D" or "E"
    state: str | None  # Case E: "before" or "after"
    quantity: str  # "scalar_speed_ratio" or "vector_speed_ratio"
    instrument: str  # "thermistor" or "split_fibre"
    ids: np.ndarray
    xyz: np.ndarray  # (n, 3) full-scale metres
    labels: tuple  # the column labels of the XLS
    directions: np.ndarray  # meteorological degrees
    values: np.ndarray  # (n, d)
    reference: dict  # normalisation: height [m] and stated speed [m/s] or None
    mirrored: np.ndarray | None = None  # (n, d) bool: copied from the mirror point, not measured


class SplitFibre(NamedTuple):
    """Case D split-fibre probe at 0°: mean vectors, variances and k at the measured points."""
    ids: np.ndarray
    xyz: np.ndarray
    measured: np.ndarray  # (n,) bool; 33 of 78 points
    velocity: np.ndarray  # (n, 3) U, V, W in m/s (wind-tunnel speeds), NaN where not measured
    variance: np.ndarray  # (n, 3) u'2, v'2, w'2 in m2/s2
    k: np.ndarray  # (n,) m2/s2
    speed_ratio: np.ndarray  # (n,) |(U, V, W)| / U_H as tabulated
    direction: float  # meteorological degrees
    reference: dict


class Inflow(NamedTuple):
    """Approach-flow profile at full-scale heights, with the wind-tunnel speeds."""
    case: str
    heights: np.ndarray  # m, full scale
    speeds: np.ndarray  # m/s
    k: np.ndarray  # m2/s2
    reference: dict  # height [m] and stated speed [m/s] or None of the result normalisation


def _number(value):
    return isinstance(value, float)


def _values(sheet, rows, columns) -> np.ndarray:
    """Numeric cells of a block as float64; any other cell type becomes NaN."""
    out = np.full((len(rows), len(columns)), np.nan)
    for i, r in enumerate(rows):
        for j, c in enumerate(columns):
            if sheet.cell_type(r, c) == xlrd.XL_CELL_NUMBER:
                out[i, j] = sheet.cell_value(r, c)
    return out


def _sheet(path, name):
    return xlrd.open_workbook(path).sheet_by_name(name)


def load_points_d(scale: float = 400.0, path=CASE_D_XLS) -> Points:
    """Case D points: three (No., x, y) column groups in model-scale mm.

    The probe height is 5 mm in the model (the ``z[mm]`` column of the result
    sheets), which is 2 m at the 1:400 scale.
    """
    sheet = xlrd.open_workbook(path).sheet_by_name("Geometry&Points")
    rows = []
    for r in range(sheet.nrows):
        values = sheet.row_values(r)
        for c in (1, 4, 7):
            group = values[c:c + 3]
            if len(group) == 3 and all(_number(v) for v in group):
                rows.append(group)
    rows.sort()
    table = np.array(rows, dtype=np.float64)
    factor = scale / 1000.0
    z = np.full(len(table), 5.0 * factor)
    return Points(table[:, 0].astype(int), np.column_stack([table[:, 1:3] * factor, z]))


def load_points_e(path=CASE_E_XLS) -> Points:
    """Case E points: (No., X, Y) in full-scale metres, measured at 2 m."""
    sheet = xlrd.open_workbook(path).sheet_by_name("Geometry&Points")
    rows = [sheet.row_values(r)[1:4] for r in range(sheet.nrows)]
    table = np.array([row for row in rows if all(_number(v) for v in row)], dtype=np.float64)
    return Points(table[:, 0].astype(int), np.column_stack([table[:, 1:3], np.full(len(table), 2.0)]))


def _d_reference(scale):
    return dict(height=H_MODEL_MM * scale / 1000.0, speed=U_H)


def _check_ids(table_ids, points: Points, sheet_name):
    if not np.array_equal(np.asarray(table_ids, dtype=int), points.ids):
        raise ValueError(f"{sheet_name}: point ids differ from Geometry&Points")


def load_inflow_d(scale: float = 400.0, path=CASE_D_XLS) -> Inflow:
    """Case D ``Inflow`` B4:G16: z [model mm], z/H, U [m/s], U/U_H, k [m2/s2], k/U_H²."""
    table = _values(_sheet(path, "Inflow"), range(3, 16), range(1, 7))
    return Inflow("D", table[:, 0] * scale / 1000.0, table[:, 2], table[:, 4], _d_reference(scale))


def load_inflow_e(path=CASE_E_XLS) -> Inflow:
    """Case E ``Inflow`` B3:D14: z/Z_R, U/U_R and k/U_R² (Z_R = 250 m, U_R = 7.8 m/s)."""
    table = _values(_sheet(path, "Inflow"), range(2, 14), range(1, 4))
    reference = dict(height=E_REFERENCE_HEIGHT, speed=None)
    return Inflow("E", table[:, 0] * Z_R, table[:, 1] * U_R, table[:, 2] * U_R ** 2, reference)


def load_exp_s(scale: float = 400.0, path=CASE_D_XLS) -> SplitFibre:
    """Case D ``Results (Exp_S)`` A4:M81: split-fibre probe at 0°.

    Columns: point, x, y, z [model mm], U, u'2, V, v'2, W, w'2, scalar velocity
    |(U, V, W)|, its ratio to U_H, and k. Rows without data hold only the id.
    """
    sheet = _sheet(path, "Results (Exp_S)")
    rows = range(3, 81)
    table = _values(sheet, rows, range(13))
    points = load_points_d(scale, path)
    _check_ids(table[:, 0], points, "Results (Exp_S)")
    measured = np.isfinite(table[:, 4])
    return SplitFibre(points.ids, points.xyz, measured, table[:, [4, 6, 8]], table[:, [5, 7, 9]],
                      table[:, 12], table[:, 11], d_direction(0.0), _d_reference(scale))


def load_exp_t(scale: float = 400.0, path=CASE_D_XLS) -> Measurements:
    """Case D ``Results (Exp_T)`` A6:J83: thermistor scalar speed / U_H at 0°, 22.5° and 45°.

    At 0° the values at y < 0 repeat those of the mirror point (x, -y); they are
    marked in ``mirrored``.
    """
    sheet = _sheet(path, "Results (Exp_T)")
    rows = range(5, 83)
    ids = _values(sheet, rows, [0])[:, 0]
    points = load_points_d(scale, path)
    _check_ids(ids, points, "Results (Exp_T)")
    values = _values(sheet, rows, range(7, 10))
    mirrored = np.zeros(values.shape, dtype=bool)
    keys = {(round(x, 6), round(y, 6)): i for i, (x, y) in enumerate(points.xyz[:, :2])}
    for i, (x, y) in enumerate(points.xyz[:, :2]):
        partner = keys.get((round(x, 6), round(-y, 6)))
        if y < 0 and partner is not None and np.isfinite(values[i, 0]):
            mirrored[i, 0] = True
    directions = np.array([d_direction(a) for a in D_ANGLES])
    return Measurements("D", None, "scalar_speed_ratio", "thermistor", points.ids, points.xyz,
                        D_LABELS, directions, values, _d_reference(scale), mirrored)


def load_results_e(state: str, path=CASE_E_XLS) -> Measurements:
    """Case E ``Results (Before|After Construction)`` B4:R83: speed at 2 m / inflow at 15.9 m."""
    if state not in E_STATES:
        raise ValueError(f"state must be one of {E_STATES}")
    sheet = _sheet(path, f"Results ({state.capitalize()} Construction)")
    labels = tuple(sheet.cell_value(2, c) for c in range(2, 18))
    if labels != E_LABELS:
        raise ValueError(f"Unexpected direction labels {labels}")
    rows = range(3, 83)
    points = load_points_e(path)
    _check_ids(_values(sheet, rows, [1])[:, 0], points, sheet.name)
    values = _values(sheet, rows, range(2, 18))
    directions = np.array([e_direction(label) for label in labels])
    return Measurements("E", state, "scalar_speed_ratio", "thermistor", points.ids, points.xyz,
                        labels, directions, values, dict(height=E_REFERENCE_HEIGHT, speed=None))
