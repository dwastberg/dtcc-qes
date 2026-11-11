from dataclasses import replace
from types import SimpleNamespace
import time
import json
import numpy as np
import pytest
import shapely
from shapely.geometry import Polygon
from scipy.ndimage import label
from dtcc_qes import wind
from dtcc_qes.geometry import _slice, _raster_labels, _line_cells
from fixtures.cities import city_case
from fixtures.cases import ONE_BUILDING


def examine(polygons, *, resolution=1., height=1.5, roofs=None, bases=None, flags=None,
            points=(), routes=(), origin=(0,0,0)):
    size = 12
    grid = SimpleNamespace(resolution=resolution,x=(np.arange(size)+.5)*resolution,
        y=(np.arange(size)+.5)*resolution,z=np.arange(4)+.5,z_faces=np.arange(5),origin=origin)
    roofs = np.full(len(polygons),4.) if roofs is None else np.asarray(roofs)
    bases = np.zeros(len(polygons)) if bases is None else np.asarray(bases)
    union = shapely.union_all([p for p,b,r in zip(polygons,bases,roofs) if b<=height<r])
    if flags is None:
        inside = shapely.contains_xy(union,grid.x[None,:],grid.y[:,None])
        flags = np.where(np.broadcast_to(inside,(4,size,size)),0,1)
    return _slice(polygons,bases,roofs,[[str(i)] for i in range(len(polygons))],grid,height,
        np.asarray(points,float).reshape(-1,2),np.asarray(routes,float).reshape(-1,2,2),flags,
        time.monotonic()+30,256)


@pytest.mark.parametrize('seed', range(5))
def test_labeler_matches_scipy_face_oracle(seed):
    fluid = np.random.default_rng(seed).random((47,61))>.4
    actual = _raster_labels(fluid)
    expected, count = label(fluid,structure=[[0,1,0],[1,1,1],[0,1,0]])
    assert actual.max() == count
    np.testing.assert_array_equal(actual,expected)


def test_diagonal_contact_separates_physical_components_and_false_join():
    # A thin oblique wall joining opposite domain edges erases on the grid.
    polygon = Polygon([(0,.2),(11.8,12),(11.6,12),(0,.4)])
    row = examine([polygon], routes=[[[1,8],[8,1]]])
    assert row['status'] == 'issue'
    assert row['physical_components'] == 2
    assert any(w['kind']=='false_join' for w in row['witnesses'])
    assert row['routes'][0]['physical_connected'] is False
    assert row['routes'][0]['represented_connected'] is True


def test_closed_gap_despite_global_detour():
    row = examine([shapely.box(2,2,4.6,9),shapely.box(4.9,2,8,9)])
    kinds = {w['kind'] for w in row['witnesses']}
    assert {'closed_passage','under_resolved'} <= kinds
    assert row['physical_components'] == row['raster_components'] == 1


def test_hole_courtyard_erased_with_area_above_one_cell():
    # Area 1.21, but lies between all half-integer centres.
    hole = [(4.51,4.51),(5.49,4.51),(5.49,5.7),(4.51,5.7)]
    polygon = Polygon([(2,2),(9,2),(9,9),(2,9)], [hole])
    row = examine([polygon])
    assert any(w['kind']=='erased_space' for w in row['witnesses'])


def test_resolved_hole_and_touching_overlapping_prisms():
    polygon = Polygon([(2,2),(9,2),(9,9),(2,9)], [[(4,4),(7,4),(7,7),(4,7)]])
    row = examine([polygon],routes=[[[5,5],[1,1]]],points=[[5,5]])
    assert row['physical_components'] == row['raster_components'] == 2
    assert row['routes'][0]['physical_connected'] is False
    assert row['points'][0]['passage_x']['width'] == 3
    row = examine([shapely.box(2,2,5,8),shapely.box(5,2,8,8),shapely.box(4,4,7,9)])
    assert row['reason'] is None


def test_elevated_prism_roof_crossing_and_bad_mask():
    polygon = shapely.box(3,3,7,7)
    assert examine([polygon],bases=[2],roofs=[4])['status'] == 'no_issue_in_examined_scope'
    assert examine([polygon],roofs=[1.7])['reason'] == 'roof_crossing'
    assert examine([polygon],bases=[1.2])['reason'] == 'roof_crossing'
    flags = np.ones((4,12,12),np.int32)
    assert examine([polygon],flags=flags)['reason'] == 'mapping_not_reproduced'
    flags[1,0,0] = 2
    assert examine([polygon],flags=flags)['reason'] == 'terrain_not_supported'


def test_native_result_preview_budget_origin_and_snapshot():
    city,condition,options,solver = city_case(ONE_BUILDING,(1000,-2000,10))
    options["resolution"] = 1.
    result = wind.run(city,**condition,**options,**solver)
    report = wind.check_geometry(city,result,points=[[1,1]],routes=[[[1,1],[3,1]]],heights=[1.5])
    payload = report.to_dict()
    assert payload['status'] == 'no_issue_in_examined_scope'
    assert payload['mask_hash']
    assert payload['slices'][0]['points'][0]['containing_cell_solid'] is False
    json.dumps(payload,allow_nan=False)
    result.cell_flags[:] = 0
    assert report.to_dict() == payload
    preview = wind.preview_grid(city,**options)
    early = wind.check_geometry(city,preview,points=[[1,1]]).to_dict()
    assert early['slices'][0]['reason'] == 'solver_mask_not_prepared'
    shifted = replace(preview,x=preview.x+1)
    assert wind.check_geometry(city,shifted).to_dict()['slices'][0]['reason'] == 'grid_alignment_mismatch'
    limited = wind.check_geometry(city,preview,points=np.ones((65,2))).to_dict()
    assert limited['status'] == 'budget_limited'
    assert len(limited['slices'][0]['points']) == 65
    timed = wind.check_geometry(city,preview,max_seconds=1e-15).to_dict()
    assert timed['status'] == 'budget_limited'
    layers = wind.check_geometry(city,preview,heights=[1,2,3,4,5]).to_dict()
    assert layers['status'] == 'budget_limited' and len(layers['slices']) == 5


def test_line_supercover_counts_face_contacts():
    cells = _line_cells(shapely.LineString([(2.2,4),(5.8,4)]),12,12,1)
    assert (3,3) in cells and (4,3) in cells


def test_footprints_path_and_zero_width_corner_contact():
    city,condition,options,solver = city_case(ONE_BUILDING)
    options['resolution'] = 1.
    settings = wind.Footprints()
    result = wind.run(city,**condition,**options,**solver,footprints=settings)
    report = wind.check_geometry(city,result,footprints=settings).to_dict()
    assert report['status'] == 'no_issue_in_examined_scope'
    # Two closed prisms touch at a corner, dividing the domain into interiors.
    row = examine([shapely.box(0,0,6,6),shapely.box(6,6,12,12)],
                  routes=[[[2,9],[9,2]]])
    assert row['physical_components'] == row['raster_components'] == 2
    assert row['routes'][0]['physical_connected'] is False


def test_multiple_canonical_prisms_and_hole_offsets():
    from dtcc_qes.geometry import _polygons
    # Both arrays contain vertex offsets; building offsets do not index rings.
    outer=np.array([[0,0],[0,4],[4,4],[4,0],[0,0]])
    hole=np.array([[1,1],[2,1],[2,2],[1,2],[1,1]])
    other=outer+10
    prepared=SimpleNamespace(arrays=dict(vertices=np.concatenate([outer,hole,other]),
        offsets=np.array([0,10,15]),ring_offsets=np.array([0,5,10,15])))
    first,second=_polygons(prepared)
    assert first.area==15 and len(first.interiors)==1
    assert second.area==16 and not second.interiors


def test_prior_e_coarsening_witnesses_are_preserved():
    from pathlib import Path
    patches=json.loads((Path(__file__).parents[1]/'research/unified_v2/prior_geometry_witnesses.json').read_text())
    for witness in patches:
        actual=_raster_labels(np.asarray(witness['fine_fluid_patch'],bool))
        assert actual.max() == witness['components']
        assert actual.max() > 1  # one represented coarse-fluid cell joins these fine components


def test_physical_passage_lost_splits_a_single_component():
    row=examine([shapely.box(0,5,5.1,7),shapely.box(5.3,5,12,7)],
        routes=[[[2,2],[2,9]]],points=[[2,6]])
    assert row['physical_components']==1 and row['raster_components']==2
    assert any(w['kind']=='disconnection' for w in row['witnesses'])
    assert row['routes'][0]['physical_connected'] is True
    assert row['routes'][0]['represented_connected'] is False
    assert row['points'][0]['containing_cell_solid'] is True
    assert row['points'][0]['passage_x']['width']==0


def test_oblique_narrow_gap_remains_a_resolution_warning():
    from shapely.affinity import rotate
    polygons=[rotate(p,30,origin=(6,6)) for p in
              (shapely.box(2,3,4.6,7),shapely.box(4.9,3,8,7))]
    row=examine(polygons)
    assert row['status']=='issue'
    warnings=[w for w in row['witnesses'] if w['kind']=='under_resolved']
    assert len(warnings)==1
    assert warnings[0]['physical_width']==pytest.approx(.3)


def test_mutated_vertical_axes_and_flag_shape_cannot_pass_alignment():
    city,condition,options,solver=city_case(ONE_BUILDING)
    preview=wind.preview_grid(city,**options)
    shifted=replace(preview,z=preview.z+1)
    assert wind.check_geometry(city,shifted).to_dict()['slices'][0]['reason']=='grid_alignment_mismatch'
    result=wind.run(city,**condition,**options,**solver)
    bad=replace(result,cell_flags=result.cell_flags[:1])
    assert wind.check_geometry(city,bad).to_dict()['slices'][0]['reason']=='grid_alignment_mismatch'
