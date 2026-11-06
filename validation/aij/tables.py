"""Measurement points, approach-flow profiles and measured results from the AIJ spreadsheets.

Sheet layouts and units are documented in AIJ_VALIDATION_PLAN.md (F9, F10) for
Cases D and E, and in AIJ_AB_VALIDATION.md (F1-F4) for Cases A and B.
Empty and ``'-'`` cells are missing data: any cell that is not a number is NaN.
Directions are meteorological degrees (see ``conventions``).
"""

from typing import NamedTuple

import numpy as np
import xlrd

from . import CASE_A_XLS, CASE_B_XLS, CASE_D_XLS, CASE_E_XLS
from .conventions import AB_DIRECTION, D_ANGLES, D_LABELS, E_LABELS, E_STATES, d_direction, e_direction

U_H = 6.65  # m/s, Case D inflow speed at the tower height (Inflow!C17)
H_MODEL_MM = 250.0  # Case D tower height in the model
Z_R = 250.0  # m, Case E boundary-layer height at full scale (Inflow!C20)
U_R = 7.8  # m/s, Case E inflow speed at Z_R (Inflow!C21)
E_REFERENCE_HEIGHT = 15.9  # m, Case E normalisation height (the Niigata station height)
E_QUANTUM = 0.019820405  # every Case E value is a multiple: U/U_R rounded to 0.01, divided by ~0.5045

# Cases A and B have no drawing. Full scale puts the near-ground section at the 2 m
# pedestrian height, as in Cases D and E (AIJ_AB_VALIDATION.md, D1): both buildings are then 32 m tall.
A_B = 16.0  # m, Case A b at full scale: z = 0.125 b is 2 m
A_MODEL_B_MM = 80.0  # Case A b in the wind tunnel (Meng & Hibi 1998), so the scale is 1:200
B_B = 8.0  # m, Case B b at full scale: z = 12.5 mm is 2 m
B_MODEL_B_MM = 50.0  # Case B b in the wind tunnel ("b=50mm in experiment", Geometry&Points C14), so 1:160
AB_HEIGHT_B = {"A": 2.0, "B": 4.0}  # building height in b
# Both cases: Dantec split-fibre probes, which resolve reverse flow (Meng & Hibi 1998; Shirasawa et al. 2003).
# In Case A the streamwise and cross components were measured in separate traverses.
AB_INSTRUMENT = {"A": "split_fibre", "B": "split_fibre"}
SECTION_ID = 1000  # combined probe id of Cases A and B: SECTION_ID x section number + AIJ point number
# (label, sheet, height of a horizontal section in b or None for the vertical section). The z column of the
# z = 1.25b sheet repeats 0.125 under a "z/b" header; the sheet name and its values put it at 1.25 b (F3).
A_SECTIONS = (("vertical", "Results (Ver. sec.)", None),
              ("z=0.125b", "Results(Hol. sec.; z=0.125b）", 0.125),
              ("z=1.25b", "Results (Hol. sec.; z=1.25b）", 1.25))
B_SECTIONS = (("vertical", "Results (Ver. sec.)", None), ("z=12.5mm", "Results (Hol. sec.)", None))


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


class VectorResults(NamedTuple):
    """Case A or B at 0°: mean velocity and turbulence at the points of every measured section.

    Points keep their AIJ numbers within a section; ``ids`` combine them with the
    section number (``SECTION_ID``), so they are unique across sections.
    """
    case: str
    ids: np.ndarray  # int, SECTION_ID x section number (from 1) + AIJ point number
    section: np.ndarray  # str, the section label of each point
    xyz: np.ndarray  # (n, 3) full-scale metres, origin at the building centre on the ground
    velocity: np.ndarray  # (n, 3) U, V, W in m/s (wind-tunnel speeds)
    variance: np.ndarray  # (n, 3) u'2, v'2, w'2 in m2/s2
    k: np.ndarray  # (n,) m2/s2, ½ the sum of the variances
    direction: float  # meteorological degrees
    reference: dict  # height H [m, full scale] and speed U_H [m/s] of the normalisation


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


def ab_source(case):
    """(spreadsheet, sections, full-scale b) of Case A or B."""
    if case not in ("A", "B"):
        raise ValueError("case must be 'A' or 'B'")
    return (CASE_A_XLS, A_SECTIONS, A_B) if case == "A" else (CASE_B_XLS, B_SECTIONS, B_B)


def _rows(sheet, first) -> range:
    """The data rows from ``first``: every row whose point number is a number."""
    last = first
    while last < sheet.nrows and sheet.cell_type(last, 0) == xlrd.XL_CELL_NUMBER:
        last += 1
    return range(first, last)


def _ab_reference(case, heights, speeds) -> dict:
    """H and the tabulated approach-flow speed at H (both tables have a point at H)."""
    height = AB_HEIGHT_B[case] * (A_B if case == "A" else B_B)
    at = np.flatnonzero(np.isclose(heights, height))
    if len(at) != 1:
        raise ValueError(f"Case {case} inflow has no single point at H = {height:g} m")
    return dict(height=float(height), speed=float(speeds[at[0]]))


def load_inflow_ab(case: str) -> Inflow:
    """Case A ``Inflow`` B3:G26: z/b, U [m/s], σu, σv, σw [m/s], k [m2/s2].
    Case B ``Inflow`` B4:H15: z [model mm], U [m/s], the 1/4 power law, u'2, v'2, w'2, k [m2/s2].

    Heights are converted to full scale; speeds stay wind-tunnel speeds. The
    reference is U_H, the tabulated speed at the building height.
    """
    path, _, b = ab_source(case)
    sheet = _sheet(path, "Inflow")
    if case == "A":
        table = _values(sheet, range(2, 26), range(1, 7))
        heights, k = table[:, 0] * b, table[:, 5]
    else:
        table = _values(sheet, range(3, 15), range(1, 8))
        heights, k = table[:, 0] * b / B_MODEL_B_MM, table[:, 6]
    speeds = table[:, 1]
    return Inflow(case, heights, speeds, k, _ab_reference(case, heights, speeds))


def load_results_ab(case: str) -> VectorResults:
    """Every result sheet of Case A (A3:K) or B (A4:K): No., x, y, z, U, V, W, then
    σu, σv, σw (A, m/s) or u'2, v'2, w'2 (B, m2/s2), then k = ½ Σ variances.

    Case A coordinates are in b, Case B coordinates in model mm. The flow is
    along +x in both (the "WIND" arrows of Fig. 2), so the direction is ``AB_DIRECTION``.
    """
    path, sections, b = ab_source(case)
    book = xlrd.open_workbook(path)
    parts = []
    for number, (label, name, height) in enumerate(sections, 1):
        sheet = book.sheet_by_name(name)
        table = _values(sheet, _rows(sheet, 2 if case == "A" else 3), range(11))
        xyz = table[:, 1:4] * (b if case == "A" else b / B_MODEL_B_MM)
        if height is not None:
            xyz[:, 2] = height * b
        variance = table[:, 7:10] ** 2 if case == "A" else table[:, 7:10]
        parts.append((SECTION_ID * number + table[:, 0].astype(int), np.full(len(table), label, dtype=object),
                      xyz, table[:, 4:7], variance, table[:, 10]))
    ids, section, xyz, velocity, variance, k = (np.concatenate(column) for column in zip(*parts))
    inflow = load_inflow_ab(case)
    if len(set(ids.tolist())) != len(ids):
        raise ValueError(f"Case {case}: duplicate point numbers within a section")
    return VectorResults(case, ids, section.astype(str), xyz, velocity, variance, k, AB_DIRECTION, inflow.reference)


def load_points_ab(case: str) -> Points:
    results = load_results_ab(case)
    return Points(results.ids, results.xyz)
