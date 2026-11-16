"""Recorded plateau regression and compatibility of the offline stop-rule replay."""
import json
from pathlib import Path
from validation.aij.stop_rule import replay

# The wind-comfort demo city at 1 m, default settings: a float32 velocity solve that ran to the sweep cap
# (docs/wind-comfort-convergence.md). Kept with the tests so that the replay runs without docs/data.
HISTORY = Path(__file__).resolve().parent / 'fixtures/reference/stop-rule/wind-comfort-demo-float32.json'


def test_demo_stagnation_replay():
    history = json.loads(HISTORY.read_text())['solver']['stop_estimate']
    assert replay(history, history['tolerance']) == (None, None)
    guarded = dict(history, stagnation_checks=8, stagnation_floor_factor=2)
    assert replay(guarded, guarded['tolerance']) == (1050, 'precision_floor')
    # An isolated near-floor sample is insufficient even with a long plateau.
    guarded['floor'] = [f if i % 2 else 0. for i, f in enumerate(history['floor'])]
    assert replay(guarded, guarded['tolerance']) == (None, None)
