"""Solver and turbulence specifications used by combined-feature checks."""

from dtcc_qes import wind, _qes


def pedestrian_solver(**changes):
    monitor = wind.MonitorSpec(
        (0, 80, 0, 80),
        history_limit=8,
        receptors=tuple(wind.Receptor(f"h{h}", 27, 21, h) for h in (1.5, 1.75)),
    )
    return wind.Solver(
        **(
            dict(
                tolerance=1e-5,
                max_solve_seconds=5,
                monitor=monitor,
                policy="pedestrian-v1",
            )
            | changes
        )
    )


def native_turbulence(method=0, enabled=True):
    value = _qes.TurbulenceSettings()
    value.enabled = enabled
    value.mixing_length_method = method
    return value
