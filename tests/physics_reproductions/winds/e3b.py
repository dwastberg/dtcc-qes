from h import *
B=(0,0,0,200,200,80)
def sym(blds,d,show=False,**k):
    a=run(blds,d,B,**k); b=run(blds,(d+180)%360,B,**k)
    va=a.velocity; vb=b.velocity[:, ::-1, ::-1, :]
    sa=np.hypot(va[...,0],va[...,1]); sb=np.hypot(vb[...,0],vb[...,1])
    d0=np.abs(sa-sb)
    fa=a.cell_flags; fb=b.cell_flags[:, ::-1, ::-1]
    if show:
        k_,j_,i_=np.unravel_index(d0.argmax(),d0.shape)
        print("    worst at z,y,x=",a.z[k_],a.y[j_],a.x[i_],"SA,SB=",sa[k_,j_,i_],sb[k_,j_,i_],"flags",fa[k_,j_,i_],fb[k_,j_,i_])
        for fl in (3,4,5,6,9,10): print("    flag",fl,"count A,B:",(fa==fl).sum(),(fb==fl).sum(),"mismatch",((fa==fl)!=(fb==fl)).sum())
        print("    z=1 max|dS|",d0[0].max()," z=1 #cells |dS|>0.25:",(d0[0]>0.25).sum(), " all-levels #>0.25:",(d0>0.25).sum())
    return [round(float(x),3) for x in (d0.max(), d0[0].max(), (fa!=fb).sum())]
sq=[(rect(80,80,120,120),30.0)]
off=dict(rooftop=0,upwind_cavity=0,street_canyon=0,sidewall=0,wake=2)
print("270 all default", sym(sq,270,show=True))
print("270 wake only", sym(sq,270,show=True,**off))
print("270 wake+upwind", sym(sq,270,**{**off,'upwind_cavity':2}))
print("270 wake+sidewall", sym(sq,270,**{**off,'sidewall':1}))
print("270 wake+rooftop", sym(sq,270,**{**off,'rooftop':1}))
print("185 all default", sym(sq,185,show=True))
print("185 wake only", sym(sq,185,show=True,**off))
print("185 wake+upwind", sym(sq,185,**{**off,'upwind_cavity':2}))
print("185 wake+sidewall", sym(sq,185,**{**off,'sidewall':1}))
print("185 wake+rooftop", sym(sq,185,**{**off,'rooftop':1}))
print("225 wake only", sym(sq,225,show=True,**off))
rb=[(rot(100,100,40,40,70),30.0)]
for d in (200,205,195):
    print("rot70 wind",d,"default",sym(rb,d), "no upwind:",sym(rb,d,upwind_cavity=0))
