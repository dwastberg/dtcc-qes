"""Small immutable views of recorded evidence, with no grid field access."""
from collections import Counter
from dataclasses import dataclass
import json
import math
from numbers import Real


PHYSICAL_K_DEFINITION = ('Half the final covariance trace on computed, currently valid fluid; '
    'unusable NaN; calm zero valid; tolerance-accepted negative energy clamped to zero')


def _strict(value, reasons, path=''):
    """Keep missing evidence explicit without emitting JSON NaN or infinity."""
    if value is None:
        reasons.setdefault(path, 'not_recorded')
        return None
    if isinstance(value, dict):
        return {str(k): _strict(v, reasons, f'{path}.{k}' if path else str(k)) for k,v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_strict(v, reasons, f'{path}[{i}]') for i,v in enumerate(value)]
    if isinstance(value, Real) and not isinstance(value, bool):
        if not math.isfinite(value):
            reasons[path] = 'nonfinite_recorded_value'
            return None
        return int(value) if isinstance(value, int) else float(value)
    return value


@dataclass(frozen=True)
class QualityReport:
    """Schema-v1 owned snapshot. ``to_dict`` returns an independent JSON view.

    Solver completion is numerical evidence only, never physical validation.
    Fields and covariance masks are deliberately not refreshed or scanned.
    """
    _json: str

    @property
    def schema_version(self):
        return 1

    def to_dict(self):
        return json.loads(self._json)

    def summary(self):
        data = self.to_dict()
        solver = data['solver']
        sample = data['sample']
        sampling = ('; sampling not supplied' if sample is None else
                    f"; samples {sample['valid']}/{sample['requested']} valid")
        return (f"Solver {solver['execution']} ({solver['termination_reason']}); "
                f"assessment {solver['assessment']}" + sampling +
                '; numerical evidence does not establish physical accuracy')


def quality_report(result, sample=None):
    """Read the authoritative qualification and scalar solve-time evidence.

    The default cost is independent of cell count. Optional sampling work is
    proportional only to the supplied sample; it never resamples the result.
    Missing historical metadata stays unavailable. Counts and support evidence
    are solve/sampling-time snapshots, independent of edited field values.
    """
    qualification = result.qualification
    diagnostics = result.diagnostics
    meta = result.metadata.get('turbulence')
    reasons = {}
    turbulence = None
    if meta is not None:
        cap, validity, reference = (meta.get(k) or {} for k in ('cap', 'validity', 'reference'))
        turbulence = dict(basis='solve_time_snapshot', model=meta.get('model'),
            version=meta.get('numerics_version'), experimental=meta.get('experimental'),
            covariance_model=meta.get('covariance_model'),
            computed=cap.get('computed_cells'), capped=cap.get('capped_cells'),
            invalid=validity.get('invalid_stress_cells'), reference_speed=reference.get('speed'),
            reference_height=reference.get('height'),
            tke_definition=meta.get('tke_definition'), physical_k_definition=PHYSICAL_K_DEFINITION,
            limitations=meta.get('limitations'))
    else:
        reasons['turbulence'] = 'turbulence_not_recorded'
    sampling = None
    if sample is not None:
        import numpy as np
        count = int(sample.valid.size)
        valid = int(np.count_nonzero(sample.valid))
        support = getattr(sample, 'support', None)
        sampling = dict(requested=count, valid=valid, invalid=count-valid,
            validity_basis='current_sample_valid_mask', unsupported=None, reasons=None,
            support_basis='owned_sampling_time_snapshot; source support cannot be refreshed from interpolant',
            reason_counts_overlap=True)
        if support is None:
            reasons.update({'sample.unsupported':'sampling_diagnostics_not_requested',
                            'sample.reasons':'sampling_diagnostics_not_requested'})
        else:
            sampling.update(unsupported=int(np.count_nonzero(~support.geometric)),
                reasons=dict(sorted(Counter(reason for row in support.reasons for reason in row).items())),
                support_counts={name: None if getattr(support,name) is None else
                    int(np.count_nonzero(getattr(support,name))) for name in
                    ('geometric','computed','contributors_valid','interpolant_valid')})
    else:
        reasons['sample'] = 'sample_not_supplied'
    divergence = dict(unit='s^-1', max=diagnostics.max_divergence, rms=diagnostics.rms_divergence,
        assessed_cells=diagnostics.divergence_cell_count,
        exclusions=['prescribed_lateral_cells', 'highest_physical_layer'],
        highest_physical_layer=dict(status='unavailable', reason='not_assessed'),
        top_band=dict(max=diagnostics.top_band_max_divergence, assessed_cells=diagnostics.top_band_cell_count,
            status='assessed' if diagnostics.top_band_cell_count and
                diagnostics.top_band_max_divergence is not None else 'unavailable'))
    if divergence['top_band']['status'] == 'unavailable':
        divergence['top_band']['reason'] = 'no_recorded_top_band_assessment'
    payload = _strict(dict(schema_version=1, solver=qualification['solver'],
        divergence=divergence, turbulence=turbulence, sample=sampling,
        qualification=qualification, physical_validation='not_established_by_this_report'), reasons)
    payload['unavailable_reasons'] = reasons
    return QualityReport(json.dumps(payload, sort_keys=True, allow_nan=False))
