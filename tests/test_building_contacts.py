"""Public canonical-solid and native ring/exposure integration."""
from copy import deepcopy
import json

import numpy as np
import pytest
from shapely import contains_xy
from shapely.geometry import Polygon, box
from shapely.affinity import rotate
from dtcc_core.model import GeometryType, MultiSurface
from dtcc_qes import wind
from test_footprints import building, city, surface

pytestmark = pytest.mark.usefixtures("dtcc_logger")
OPTIONS = dict(bounds=(-20,-20,0,60,40,40), resolution=1, max_iterations=12)


def run(value, *, expose=True, **options):
    return wind.run(value, 5, 270, footprints=wind.Footprints(min_detail=.01, exposed_faces=expose),
                    **(OPTIONS | options))


def same(a,b):
    np.testing.assert_array_equal(a.cell_flags,b.cell_flags)
    np.testing.assert_array_equal(a.velocity,b.velocity)


def test_split_and_single_canonical_solids_are_exact():
    split=run(city(building('a',box(0,0,10,10),10),building('b',box(10,0,20,10),9.9)))
    single=run(city(building('block',box(0,0,20,10),10)))
    same(split,single)
    assert split.metadata['footprints']['counts']['solids']==1
    assert all(s['solids']==[0] for s in split.metadata['buildings'])
    assert split.metadata['model']['exposed_faces']
    json.dumps(split.metadata,allow_nan=False)


def test_overlap_and_partition_are_exact_and_permutation_independent():
    low=building('low',box(0,0,20,10),6)
    high=building('high',box(10,0,20,10),12)
    overlap=run(city(low,high))
    partition=run(city(building('low',box(0,0,10,10),6),deepcopy(high)))
    reversed_=run(city(deepcopy(high),deepcopy(low)))
    same(overlap,partition)
    same(overlap,reversed_)


@pytest.mark.parametrize('expose',[False,True])
def test_courtyard_and_tower_masks_follow_even_odd_rings(expose):
    value=city(building('podium',box(0,0,20,20),6),building('tower',box(5,5,15,15),12))
    result=run(value,expose=expose)
    x,y=np.meshgrid(result.x+result.origin[0],result.y+result.origin[1])
    podium=contains_xy(box(0,0,20,20),x,y)
    tower=contains_xy(box(5,5,15,15),x,y)
    for k,z in enumerate(result.z):
        expected=(podium & (z<=6)) | (tower & (z<=12))
        np.testing.assert_array_equal(result.solid_mask[k],expected)
    assert np.isfinite(result.velocity).all()
    # An actual empty courtyard, rather than a hole occupied by a tower.
    hole=Polygon(box(0,0,20,20).exterior.coords,[box(5,5,15,15).exterior.coords])
    courtyard=run(city(building('courtyard',hole,6)),expose=expose)
    expected=contains_xy(hole,x,y)
    np.testing.assert_array_equal(courtyard.solid_mask[2],expected)


def test_multipart_holes_and_oblique_contacts_are_supported():
    hole=Polygon(box(0,0,10,10).exterior.coords,[box(2,2,8,8).exterior.coords])
    a=building('multipart',hole,8)
    a.add_geometry(MultiSurface(surfaces=[surface(hole),surface(box(20,0,30,10))]),GeometryType.LOD0)
    result=run(city(a))
    assert result.metadata['footprints']['counts']['solids']==2
    first=rotate(box(0,0,10,10),25,origin=(0,0))
    second=rotate(box(10,0,20,10),25,origin=(0,0))
    rotated=run(city(building('a',first,6),building('b',second,12)))
    assert np.isfinite(rotated.velocity).all()


@pytest.mark.parametrize('grid',[None,wind.VerticalGrid.from_faces(np.arange(0,41,.5)),wind.VerticalGrid.auto()])
def test_preview_and_solve_share_final_solids_and_turbulence_reference(grid):
    value=city(building('a',box(0,0,10,10),10),building('b',box(10,0,20,10),9.9))
    options=dict(resolution=1,vertical_grid=grid,turbulence=True,footprints=wind.Footprints(min_detail=.01))
    preview=wind.preview_grid(value,**options)
    result=wind.run(value,5,270,max_iterations=3,**options)
    assert preview.domain==result.metadata['domain']
    assert preview.shape==result.solid_mask.shape
    heights=np.sort(np.array([s['native_height'] for s in result.metadata['solids']],dtype=np.float32))
    mean=np.float32(np.cumsum(heights,dtype=np.float32)[-1]/len(heights))
    assert result.turbulence.reference_height==float(np.float32(3*float(mean)))


def test_isolated_reference_exposure_switch_preserves_bits():
    from city_cases import city_case
    from fixtures.cases import ONE_BUILDING
    value,condition,grid,solver=city_case(ONE_BUILDING)
    strict=wind.run(value,**condition,**grid,**solver)
    for expose in [False,True]:
        result=wind.run(value,**condition,**grid,**solver,
            footprints=wind.Footprints(min_detail=.01,exposed_faces=expose))
        same(strict,result)


def test_exposure_changes_stepped_contact_but_preserves_mask():
    value=city(building('a',box(0,0,10,10),6),building('b',box(10,0,20,10),12))
    on,off=run(value),run(value,expose=False)
    np.testing.assert_array_equal(on.solid_mask,off.solid_mask)
    assert np.any(on.cell_flags!=off.cell_flags)
    assert np.max(np.abs(on.velocity-off.velocity))>0


@pytest.mark.parametrize('value',[True,{},'resolve'])
def test_invalid_public_footprint_settings_are_rejected(value):
    with pytest.raises(TypeError,match='Footprints or None'):
        wind.preview_grid(city(),bounds=(-20,-20,0,60,40,40),footprints=value)


def test_strict_near_contacts_are_recorded_without_cleaning(caplog):
    value=city(building('a',box(0,0,10,10),6),building('b',box(10.3,0,20.3,10),6))
    result=wind.run(value,5,270,**(OPTIONS | {'max_iterations':2}))
    pair,=result.metadata['near_contacts']
    assert pair['source_ids']==['a','b']
    assert pair['distance']==pytest.approx(.3)
    assert len([r for r in caplog.records if 'building pairs are closer' in r.message])==1
    assert 'footprints' not in result.metadata


def test_empty_resolved_city_and_corner_contact():
    empty=run(city())
    assert empty.metadata['footprints']['counts']['solids']==0
    assert np.isfinite(empty.velocity).all()
    corner=run(city(building('a',box(0,0,10,10),6),building('b',box(10,10,20,20),12)))
    assert np.isfinite(corner.velocity).all()
