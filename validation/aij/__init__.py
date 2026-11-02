"""Build dtcc-core City models of the AIJ pedestrian-wind benchmark cases D and E.

See ``validation/AIJ_CITY_MODELS.md`` for the source data findings and modelling
decisions. Every City is in full-scale metres in the AIJ measurement frame
(origin at the centre of the reproduced area), on flat ground at z = 0.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE_D_DXF = ROOT / "AIJ_D" / "CaseD(Highrise+Blocks).dxf"
CASE_D_XLS = ROOT / "AIJ_D" / "CaseD(Highrise+Blocks).xls"
CASE_E_DXF = ROOT / "AIJ_E" / "CaseE(Niigata).dxf"
CASE_E_XLS = ROOT / "AIJ_E" / "CaseE(Niigata).xls"
