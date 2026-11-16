import hashlib,json,sys
from fixtures.condition_state import prepare,configuration
from dtcc_qes import _qes
runner=prepare(configuration());options=_qes.SolverOptions();options.stop_rule='velocity';options.relaxation=1.999;options.velocity_tolerance=1e-9;options.max_iterations=20000
condition=_qes.WindCondition();condition.direction=67.5
result=runner.solve(condition,options)
assert result['stop_estimate']['floor_trigger']=='stagnation'
with open(sys.argv[1],'w') as f:json.dump(dict(history=result['stop_estimate'],diagnostics=result['diagnostics'],field=hashlib.sha256(result['velocity'].tobytes()).hexdigest()),f)
