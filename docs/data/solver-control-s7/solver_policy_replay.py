"""Independent S7 replay of the native pedestrian predictor (no solver calls)."""
from __future__ import annotations
import math

POLICY='pedestrian-v1'
METHOD='s5c-rb-sor-float-omega-v1-omega-1.90'
TARGET=dict(vector_p95=5e-4,vector_maximum=1e-3,speed_p95=5e-4,speed_maximum=1e-3,
            scaled_mass_maximum=1e-3,scaled_mass_rms=1e-4,relative_residual_maximum=1e-3,
            relative_residual_rms=1e-4,length_m=23.7)


def prediction(cp, params, uref):
    out=dict(available=False,reason='warming_up',vector_p95=None,vector_maximum=None,
             speed_p95=None,speed_maximum=None,required_maximum=None,hotspot_maximum=None,
             q_minimum=None,q_maximum=None)
    if cp['iteration']<params['minimum_iterations']:return out
    monitor=cp['monitor']
    if not monitor['required_valid'] or any(h['valid']<16 for h in monitor['heights']):
        out['reason']='invalid_support';return out
    values=[];qs=[];required=[];hotspots=[]
    def tail(short,long,metric,index):
        if (not short['available'] or not long['available'] or short['validity_changes'] or long['validity_changes']
            or short['common_valid']!=long['common_valid'] or short['common_valid']==0
            or short['to_iteration']!=cp['iteration'] or long['to_iteration']!=cp['iteration']
            or short['to_iteration']-short['from_iteration']!=25 or long['to_iteration']-long['from_iteration']!=100):
            return None
        stat='p95' if index%2==0 else 'maximum'
        ds=short[metric][stat];dl=long[metric][stat];a=short['ratios'][index];b=long['ratios'][index]
        if any(x is None or not math.isfinite(x) or x<=0 for x in [ds,dl,a,b]):return None
        q=max(a,b)
        if min(a,b)<.02 or q>=params['maximum_ratio'] or max(a,b)>4*min(a,b):return None
        qs.extend([a,b])
        return params['safety_factor']*max(ds*q/(1-q),dl*q**4/(1-q**4))
    for h in monitor['heights']:
        group=[tail(h['short'],h['long'],'vector',0),tail(h['short'],h['long'],'vector',1),
               tail(h['short'],h['long'],'speed',2),tail(h['short'],h['long'],'speed',3)]
        if any(x is None for x in group):out['reason']='unstable_or_plateaued_tail';return out
        values.append(group)
        # The ROI maximum covers every point, including current/previous peaks.
        for window in [h['short'],h['long']]:
            for peak in window['hotspots']:
                if not peak['present'] or not peak['before_valid'] or not peak['current_valid']:
                    out['reason']='invalid_hotspot';return out
        hotspots.append(max(group[1],group[3]))
    for r in monitor['receptors']:
        if not r['required']:continue
        if (not r['valid'] or any(not r[w]['available'] or r[w]['validity_changes'] or r[w]['common_valid']!=1 for w in ['short','long'])):
            out['reason']='unavailable_required_support';return out
        required.append(max(max(g[1],g[3]) for g in values))
    if not values or not required:out['reason']='invalid_support';return out
    out.update(available=True,reason='predicted',vector_p95=max(g[0] for g in values),
               vector_maximum=max(g[1] for g in values),speed_p95=max(g[2] for g in values),
               speed_maximum=max(g[3] for g in values),required_maximum=max(required),
               hotspot_maximum=max(hotspots),q_minimum=min(qs),q_maximum=max(qs))
    return out


def safeguards(cp, uref):
    r=cp['residual'];scale=TARGET['length_m']/uref
    mass=cp['monitor']['regional_mass'];regional=cp['regional_residual']
    normalized=[(v['maximum']*scale,v['rms']*scale,v['cells']) for v in mass]
    normalizer=(r['rhs_maximum'],r['rhs_rms'])
    passed=(r['cells']>0 and all(math.isfinite(x) and x>0 for x in normalizer)
        and 0<=r['relative_maximum']<=TARGET['relative_residual_maximum']
        and 0<=r['relative_rms']<=TARGET['relative_residual_rms']
        and bool(mass) and len(mass)==len(regional)
        and all(n>0 and math.isfinite(a) and math.isfinite(b)
                and 0<=a<=TARGET['scaled_mass_maximum'] and 0<=b<=TARGET['scaled_mass_rms'] for a,b,n in normalized)
        and all(v['cells']>0 and 0<=v['maximum']/normalizer[0]<=TARGET['relative_residual_maximum']
                and 0<=v['rms']/normalizer[1]<=TARGET['relative_residual_rms'] for v in regional))
    return dict(passed=passed,scaled_mass_maximum=max((a for a,b,n in normalized),default=None),
                scaled_mass_rms=max((b for a,b,n in normalized),default=None))


def replay(checkpoints, params, uref):
    streak=0;out=[];anchor=None;previous=None
    for cp in checkpoints:
        fresh=prediction(cp,params,uref);p=dict(fresh);s=safeguards(cp,uref)
        drift=[]
        stable=cp['monitor']['required_valid']
        for item in cp['monitor']['heights']+[r for r in cp['monitor']['receptors'] if r['required']]:
            w=item['short'];v=w['vector']['maximum'];k=w['speed']['maximum']
            stable=stable and w['available'] and not w['validity_changes'] and w['common_valid']>0 and v is not None and k is not None
            if v is not None and k is not None:drift.append((v,k))
        if anchor is not None:
            if not stable or previous is None or cp['iteration']-previous!=25 or cp['iteration']-anchor['iteration']>100:anchor=None
            else:
                anchor['vector']+=max(v for v,k in drift);anchor['speed']+=max(k for v,k in drift)
        if fresh['available'] and (anchor is None or max(fresh['vector_maximum'],fresh['speed_maximum'])<=max(anchor['vector'],anchor['speed'])):
            anchor=dict(iteration=cp['iteration'],vector=fresh['vector_maximum'],speed=fresh['speed_maximum'],
                        q_minimum=fresh['q_minimum'],q_maximum=fresh['q_maximum'])
        if anchor is not None and anchor['iteration']!=cp['iteration']:
            p.update(available=True,reason='transported_anchor',vector_p95=anchor['vector'],vector_maximum=anchor['vector'],
                     speed_p95=anchor['speed'],speed_maximum=anchor['speed'],required_maximum=max(anchor['vector'],anchor['speed']),
                     hotspot_maximum=max(anchor['vector'],anchor['speed']),q_minimum=anchor['q_minimum'],q_maximum=anchor['q_maximum'])
        p.update(anchor_iteration=anchor['iteration'] if anchor else None,fresh_tail_available=fresh['available'],current_tail_reason=fresh['reason'])
        previous=cp['iteration']
        candidate=(p['available'] and all(p[k]<=TARGET[k] for k in ['vector_p95','vector_maximum','speed_p95','speed_maximum'])
                   and p['required_maximum']<=TARGET['vector_maximum'] and p['hotspot_maximum']<=TARGET['vector_maximum'] and s['passed'])
        streak=streak+1 if candidate else 0
        out.append(dict(iteration=cp['iteration'],prediction=p,safeguards=s,consecutive=streak,
                        accepted=streak>=3))
    return out
