"""DTCC integration with QES-Winds.

Use ``from dtcc_qes import wind`` for the in-memory city wind solver. Importing
this package also registers ``qes_wind`` with DTCC Core's dataset registry.
"""

__version__ = "0.1.0b1"

import dtcc_qes.datasets
