"""Experimental measured and power-law approaches on a synthetic building.

Run with: python examples/wind_profiles.py
These are reproducible numerical examples, not independently validated cases.
"""
import json

from dtcc_core.model import Building, City, GeometryType, Surface
import numpy as np
from dtcc_qes import wind


def main():
    city = City()
    block = Building(id="profile-example")
    block.measured_height = 8.0
    block.add_geometry(Surface(vertices=np.array([
        [30.,25.,0.], [30.,35.,0.], [40.,35.,0.], [40.,25.,0.],
    ])), GeometryType.LOD0)
    city.add_building(block)
    profiles = [
        wind.MeasuredProfile([2,5,10,20,40], [2.1,3.,4.2,5.6,7.], direction=270,
            reference_height=10, below="log", above="constant",
            metadata={"source": "synthetic example", "mean_type": "scalar mean speed"}),
        # Explicit engineering-comparison exponent; no universal terrain preset.
        wind.PowerLawProfile(5.,270.,reference_height=10.,exponent=.22,
                            metadata={"source": "synthetic power-law verification"}),
    ]
    for profile in profiles:
        result = wind.run(city, profile=profile, resolution=2., bounds=(0,0,0,80,60,40))
        print(json.dumps(dict(kind=profile.kind, reference=result.metadata["profile"]["reference"],
                              applied_at_heights=[1,5,10,20,40],
                              background_vectors=profile.evaluate([1,5,10,20,40]).tolist(),
                              converged=result.diagnostics.converged), indent=2))
    return profiles


if __name__ == "__main__":
    main()
