from h import *
# E3 point symmetry of upwind cavity
B=(0,0,0,200,200,80)
def sym(blds,d,**k):
    a=run(blds,d,B,**k); b=run(blds,(d+180)%360,B,**k)
    va=a.velocity; vb=b.velocity[:, ::-1, ::-1, :]
    sa=np.hypot(va[...,0],va[...,1]); sb=np.hypot(vb[...,0],vb[...,1])
    d0=np.abs(sa-sb)[:5]
    fa=a.cell_flags; fb=b.cell_flags[:, ::-1, ::-1]
    return d0.max(), d0.mean(), (fa!=fb).sum(), np.abs(va[...,0]+vb[...,0])[:5].max()
sq=[(rect(80,80,120,120),30.0)]
for d in (270,90,180,0,185,5,175,355,275,95):
    print("axis-aligned 40x40x30 wind",d,"vs +180: max|dS|,mean|dS|,flagdiff,max|du|:",[round(float(x),3) for x in sym(sq,d)])
rb=[(rot(100,100,40,40,20),30.0)]
for d in (200,290,205,195):
    print("rotated20 wind",d,"vs +180:",[round(float(x),3) for x in sym(rb,d)])
for d in (200,205):
    print("  same with upwind_cavity=0:",[round(float(x),3) for x in sym(rb,d,upwind_cavity=0)])
print("  axis 185 with upwind_cavity=0:",[round(float(x),3) for x in sym(sq,185,upwind_cavity=0)])
