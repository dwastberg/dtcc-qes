"""Build dtcc-core City models of the AIJ pedestrian-wind benchmark cases A, B, D and E.

See ``validation/AIJ_CITY_MODELS.md`` (D, E) and ``validation/AIJ_AB_VALIDATION.md``
(A, B) for the source data findings and modelling decisions. Every City is in
full-scale metres in the AIJ measurement frame (origin at the centre of the
reproduced area, or of the building in A and B), on flat ground at z = 0.
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(os.environ.get("DTCC_QES_AIJ_DATA", ROOT)).expanduser().resolve()
CASE_A_XLS = DATA_ROOT / "AIJ_A" / "CaseA(1_1_2).xls"
CASE_B_XLS = DATA_ROOT / "AIJ_B" / "CaseB(4_4_1).xls"
CASE_D_DXF = DATA_ROOT / "AIJ_D" / "CaseD(Highrise+Blocks).dxf"
CASE_D_XLS = DATA_ROOT / "AIJ_D" / "CaseD(Highrise+Blocks).xls"
CASE_E_DXF = DATA_ROOT / "AIJ_E" / "CaseE(Niigata).dxf"
CASE_E_XLS = DATA_ROOT / "AIJ_E" / "CaseE(Niigata).xls"
