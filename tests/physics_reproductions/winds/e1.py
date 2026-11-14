from h import *
B=(0,0,0,400,200,120)
tower=(rect(100,90,120,110),60.0); small=(rect(150,97,156,103),4.0)
for ex in (False,True):
    for blds,name in (([tower],'tower only'),([tower,small],'tower+kiosk')):
        r=run(blds,270,B,exposed=ex)
        f=r.cell_flags[0]; sp=np.hypot(r.velocity[0,...,0],r.velocity[0,...,1])
        j=slice(48,52);
        xs=r.x
        m=(xs>165)&(xs<300)
        print(f"exposed={ex} {name}: far-wake(5) cells at z={r.z[0]} x in 165..300, |y-100|<4: {(f[j][:,m]==5).sum()} of {f[j][:,m].size}; mean speed there {sp[j][:,m].mean():.3f}; speed at x=170,200,240: {[round(float(sp[50,np.argmin(abs(xs-x))]),2) for x in (170,200,240)]}")
