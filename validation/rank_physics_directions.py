"""Apply the plan's deterministic D2 ranking to two archived fast runs."""
import argparse
from pathlib import Path
import numpy as np
from compare_physics_archives import comparisons
from aij import metrics


def pooled(archive):
    values=comparisons(archive,2.)
    names=(('A-K',),('B-K',),('D-thermistor-K',),
           ('E-before-thermistor-K','E-after-thermistor-K'))
    scores=[]
    for group in names:
        score=metrics.scores(np.concatenate([values[n].simulated.ravel() for n in group]),
                             np.concatenate([values[n].measured.ravel() for n in group]))
        scores.append([score['hit_rate'],score['r']])
    return np.array(scores)


def mirror(path):
    rows=[list(map(float,line.split('initial/final')[1].split()))
          for line in Path(path).read_text().splitlines() if 'mirror max' in line]
    if len(rows)!=12:raise ValueError('Expected all twelve synthetic layout/wake combinations')
    return np.mean([r[2] for r in rows])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('v1','v3','v1_frames','v3_frames'):parser.add_argument(name,type=Path)
    args=parser.parse_args()
    a,b=pooled(args.v1),pooled(args.v3)
    print('Required synthetic tests must pass separately for both variants.')
    for case,sa,sb in zip('ABDE',a,b):print(case,'V1 q/R',*sa,'V3 q/R',*sb)
    delta=b-a;mean=delta.mean();print('mean score V1',a.mean(),'V3',b.mean(),'delta',mean)
    if mean>.02 and delta.min()>=-.02:choice='V3 (score)'
    elif mean<-.02 and delta.max()<=.02:choice='V1 (score)'
    else:
        ma,mb=mirror(args.v1_frames),mirror(args.v3_frames)
        print('Mean initial mirror error V1',ma,'V3',mb)
        if abs(ma-mb)>.05:choice='V1 (mirror)' if ma<mb else 'V3 (mirror)'
        else:choice='V1 (simpler, order-independent tie-break)'
    print('Decision:',choice)


if __name__=='__main__':main()
