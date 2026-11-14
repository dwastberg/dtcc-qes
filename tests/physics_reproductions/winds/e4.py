from h import *
exec(open(__file__.replace('e4.py','e3b.py')).read().split("sq=")[0].split("B=(0,0,0,200,200,80)")[1])
B=(0,0,0,200,200,80)
rb=[(rot(100,100,40,40,20),30.0)]
for d in (250,255,245):
    print("rot20 wind",d,"vs +180: default",sym(rb,d),"no upwind:",sym(rb,d,upwind_cavity=0), "no upwind/sidewall/rooftop:",sym(rb,d,upwind_cavity=0,sidewall=0,rooftop=0))
# E4 low building in front of tower
B=(0,0,0,300,200,140)
tower=(rect(100,84,130,116),90.0); low=(rect(84,94,94,106),8.0)
for blds,name in (([low],'low only'),([tower,low],'tower+low')):
    r=run(blds,270,B)
    f=r.cell_flags; xs,ys=r.x,r.y
    my=(ys>94)&(ys<106)
    west=(xs>60)&(xs<84); east=(xs>94)&(xs<100)
    print("E4",name,": cavity(4) cells z<8 west of low bld:",(f[:4][:,my][:,:,west]==4).sum()," east (gap):",(f[:4][:,my][:,:,east]==4).sum(),
          " mean u z=1 west strip:",round(float(r.velocity[0][my][:,west][...,0].mean()),2), "flags west z=1 row:", f[0][50][(xs>60)&(xs<100)].tolist())
# E5 order dependence, equal heights
B=(0,0,0,240,160,60)
A=(rect(50,50,70,70),20.0); C=(rect(84,62,104,82),20.0)
for ex in (None,True):
    r1=run([A,C],270,B,exposed=ex); r2=run([C,A],270,B,exposed=ex)
    s1=np.hypot(r1.velocity[...,0],r1.velocity[...,1]); s2=np.hypot(r2.velocity[...,0],r2.velocity[...,1])
    d=np.abs(s1-s2)
    print("E5 exposed",ex,"swap input order: max|dS| all",round(float(d.max()),3),"z=1 max",round(float(d[0].max()),3),"#z=1 cells>0.25:",int((d[0]>0.25).sum()),"flag diffs",int((r1.cell_flags!=r2.cell_flags).sum()))
    r1=run([A,C],270,B,exposed=ex,wake=3); r2=run([C,A],270,B,exposed=ex,wake=3)
    s1=np.hypot(r1.velocity[...,0],r1.velocity[...,1]); s2=np.hypot(r2.velocity[...,0],r2.velocity[...,1]); d=np.abs(s1-s2)
    print("   wake=3: max|dS|",round(float(d.max()),3),"z=1 max",round(float(d[0].max()),3))
