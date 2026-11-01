"""Reference-preserving rotations and comfort assembly, with independent laws."""
from copy import deepcopy
from dataclasses import replace
import json
import math

import numpy as np
import pytest
from dtcc_core.model import City
from dtcc_qes import comfort,wind


PROFILES=[wind.LogProfile(5,350),wind.UniformProfile(5,350),wind.PowerLawProfile(5,350,10,.2),
    wind.MeasuredProfile([1,10,100],[2,5,7],direction=350,reference_height=10,below="log"),
    wind.MeasuredProfile([1,10,100],[2,5,7],directions=[10,350,330],reference_height=10,below="log"),
    wind.MeasuredProfile([1,10,100],u=[1,3,5],v=[2,-4,-1],reference_height=10,below="log")]


@pytest.mark.parametrize("profile",PROFILES)
@pytest.mark.parametrize("direction",[0,360,-20,105])
def test_rigid_rotation_and_roundtrip(profile,direction):
    z=np.array([1,3,10,50,100])
    original=profile.evaluate(z)
    rotated=profile.with_direction(direction)
    assert rotated.reference["direction"]==pytest.approx(direction%360,abs=1e-12)
    np.testing.assert_allclose(np.linalg.norm(rotated.evaluate(z),axis=1),np.linalg.norm(original,axis=1),rtol=2e-15)
    np.testing.assert_allclose(rotated.with_direction(profile.reference["direction"]).evaluate(z),original,atol=6e-15)
    assert rotated.roughness_length==profile.roughness_length
    assert rotated.to_dict()==wind.profile_from_dict(rotated.to_dict()).to_dict()
    a,b=original,rotated.evaluate(z)
    np.testing.assert_allclose(a@a.T,b@b.T,rtol=3e-15,atol=1e-14)


@pytest.mark.parametrize("profile",[wind.LogProfile(0,270),wind.UniformProfile(0,270),
    wind.PowerLawProfile(0,270,10,.2),wind.MeasuredProfile([1,10],[2,0],direction=270,reference_height=10)])
def test_calm_rotation_rejected(profile):
    with pytest.raises(ValueError,match="calm"):
        profile.with_direction(30)


@pytest.mark.parametrize("law",["standard","shifted"])
def test_matching_law_identity_reciprocity_and_extremes(law):
    for roughness in (1e-35,.1,5):
        identity=comfort.log_law_transfer([5],10,roughness,10,roughness,from_law=law,to_law=law)
        np.testing.assert_allclose(identity,[5],rtol=3e-16)
    forward=comfort.log_law_transfer([5],10,.03,20,.5,from_law=law,to_law=law)
    back=comfort.log_law_transfer(forward,20,.5,10,.03,from_law=law,to_law=law)
    np.testing.assert_allclose(back,[5],rtol=3e-16)


def test_both_target_terms_match_shifted_profile_and_standard_source():
    target=float(comfort.log_law_transfer([5],10,.03,10,.5)[0])
    blended=5*math.log(60/.03)/math.log(10/.03)
    profile=wind.LogProfile(target,270,roughness_length=.5)
    assert math.hypot(*profile.evaluate(60))==pytest.approx(blended,rel=3e-16)
    wrong=5*math.log(60/.03)/math.log(10/.03)*math.log1p(10/.5)/math.log(60/.5)
    assert abs(wrong-target)>.001
    assert np.isfinite(comfort.log_law_transfer([5],.01,.1,.01,.1,from_law="shifted"))[0]


def results(*,turbulence=None):
    return [wind.run(City(),wind.LogProfile(speed,d),bounds=(0,0,0,24,24,32),
        turbulence=turbulence) for speed,d in ((3,0),(7,90))]


def test_assembly_reference_normalization_and_copied_provenance():
    solved=results()
    actual=comfort.assess_results(solved,[3,7],[0,90])
    samples=[r.sample(1.75,method="linear") for r in solved]
    expected=comfort.assess([3,7],[0,90],np.stack([s.speed for s in samples]),[0,90],[3,7],height=1.75)
    np.testing.assert_array_equal(actual.comfort,expected.comfort)
    np.testing.assert_array_equal(actual.exceedance[5],expected.exceedance[5])
    before=deepcopy(actual.metadata)
    solved[0].velocity[:]=100
    solved[0].metadata["profile"]["caveats"].append("edited")
    assert actual.metadata==before
    json.dumps(actual.metadata,allow_nan=False)
    assert actual.metadata["runs"]["directions"][1]["reference"]["speed"]==7


def test_sampling_height_and_reference_mismatches_are_rejected():
    solved=results()
    with pytest.raises(ValueError,match="actual sampled height"):
        comfort.assess_results([solved[0],replace(solved[1],z=solved[1].z+.5)],[5],[0],method="nearest")
    for edit in ("origin","crs","x"):
        altered=replace(solved[1],**{edit: {"origin":(1,0,0),"crs":"different","x":solved[1].x+1}[edit]})
        with pytest.raises(ValueError,match="share"):
            comfort.assess_results([solved[0],altered],[5],[0])
    with pytest.raises(ValueError,match="distinct"):
        comfort.assess_results([solved[0],solved[0]],[5],[0])
    with pytest.raises(ValueError,match="nonempty"):
        comfort.assess_results([],[5],[0])


def test_unsupported_linear_height_remains_nan_and_gem_provenance_is_separate():
    solved=results(turbulence=wind.Turbulence())
    unsupported=comfort.assess_results(solved,[5],[0],height=.1)
    assert (unsupported.comfort==-1).all()
    assert all(r["sampling"]["sampled_height"] is None for r in unsupported.metadata["runs"]["directions"])
    for criterion in (comfort.NEN8100,comfort.CITY_OF_LONDON):
        actual=comfort.assess_results(solved,[5],[0],criterion,peak_factor=3)
        assert "runs" in actual.metadata
        assert ("gem" in actual.metadata)==criterion.gust_equivalent
        assert actual.metadata["runs"]["directions"][0]["qualification"]["turbulence"]["status"]=="screening"
        json.dumps(actual.metadata,allow_nan=False)
    mean=comfort.assess_results(solved,[5],[0],comfort.CITY_OF_LONDON)
    assert sum("Mean speeds only" in w for w in mean.warnings)==1
