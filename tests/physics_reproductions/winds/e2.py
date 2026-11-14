from h import *
# E2 sidewall in a wake: tandem cubes, gap 50 m
B=(0,0,0,300,160,80)
A=(rect(60,70,80,90),20.0); C=(rect(130,70,150,90),20.0)
for ex in (False,True):
    r=run([A,C],270,B,exposed=ex)
    f=r.cell_flags; u=r.velocity[...,0]
    xs,ys=r.x,r.y
    mx=(xs>128)&(xs<152); my=((ys>60)&(ys<70))|((ys>90)&(ys<100))
    sub=f[:10][:,my][:,:,mx]; usub=u[:10][:,my][:,:,mx]
    print(f"E2 exposed={ex}: sidewall(9) cells beside downstream cube: {(sub==9).sum()}; min u beside it (z<20): {usub.min():.2f}; mean u z=1: {usub[0].mean():.2f}")
    mxa=(xs>58)&(xs<82); suba=f[:10][:,my][:,:,mxa]
    print(f"    upstream cube sidewall cells: {(suba==9).sum()}, min u {u[:10][:,my][:,:,mxa].min():.2f}")
