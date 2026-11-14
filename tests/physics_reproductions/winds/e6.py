from h import *
B=(0,0,0,300,200,140)
# high-rise slab
for (L,W,H) in ((16,60,60),(16,16,60),(8,8,80)):
    bl=[(rect(100,100-W/2,100+L,100+W/2),float(H))]
    for hr in (0,1):
        r=run(bl,270,B,high_rise=hr); f=r.cell_flags
        print(f"high_rise={hr} L={L} W={W} H={H}: cavity cells {(f==4).sum()}, far-wake cells {(f==5).sum()}, z=1 speed 30 m behind centre {np.hypot(*np.moveaxis(r.velocity[0,50,int((100+L+30)/2)][:2],0,0)):.2f}")
# kinked facade
B=(0,0,0,240,200,80)
plain=[(rect(100,70,120,130),30.0)]
kink=[([(100,70),(100,90),(99.9,100),(100,110),(100,130),(120,130),(120,70)],30.0)]
seg=[([(100,70),(100,85),(100,100),(100,115),(100,130),(120,130),(120,70)],30.0)]
for name,bl in (('plain',plain),('3 collinear splits',seg),('0.1 m kink at mid-facade',kink)):
    for ex in (None,True):
        try:
            r=run(bl,270,B,exposed=ex); f=r.cell_flags; xs=r.x
            sp=np.hypot(r.velocity[0,...,0],r.velocity[0,...,1])
            print(f"{name} footprints={'None' if ex is None else 'Footprints()'}: upwind(3) cells {(f==3).sum()}, z=1 speed at 10/20/30 m in front of facade centre: {[round(float(sp[50,np.argmin(abs(xs-(100-d)))]),2) for d in (10,20,30)]}, cavity(4) {(f==4).sum()} sidewall(9) {(f==9).sum()}")
        except Exception as e: print(name,ex,"ERR",str(e)[:100])
