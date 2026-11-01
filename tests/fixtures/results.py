"""Keyword-only constructors for synthetic public outputs."""

from dtcc_qes import wind


def wind_result(
    *,
    velocity,
    x,
    y,
    z,
    cell_flags,
    origin,
    crs,
    resolution,
    diagnostics,
    metadata,
    z_faces=None,
    turbulence=None,
):
    return wind.WindResult(
        velocity=velocity,
        x=x,
        y=y,
        z=z,
        cell_flags=cell_flags,
        origin=origin,
        crs=crs,
        resolution=resolution,
        diagnostics=diagnostics,
        metadata=metadata,
        z_faces=z_faces,
        turbulence=turbulence,
    )


def turbulence_fields(
    *,
    stress,
    tke,
    co_eps,
    mixing_length,
    computed,
    capped,
    stress_valid,
    friction_velocity,
    reference_speed,
    reference_height,
    roughness_length,
    displacement_height,
):
    return wind.TurbulenceFields(
        stress=stress,
        tke=tke,
        co_eps=co_eps,
        mixing_length=mixing_length,
        computed=computed,
        capped=capped,
        stress_valid=stress_valid,
        friction_velocity=friction_velocity,
        reference_speed=reference_speed,
        reference_height=reference_height,
        roughness_length=roughness_length,
        displacement_height=displacement_height,
    )
