import csv, sys
from datetime import datetime, timezone, timedelta
sys.path.insert(0, __file__.rsplit("/",1)[0])
import backtest as bt

def load5():
    b=[]
    with open('/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv') as f:
        for r in csv.DictReader(f):
            try: o=float(r['open']);h=float(r['high']);l=float(r['low']);c=float(r['close'])
            except: continue
            dt=datetime.fromisoformat(r['time']).astimezone(timezone(timedelta(hours=-5)))
            b.append((dt,o,h,l,c,dt.hour*60+dt.minute))
    return b

BASE=dict(slopeEntry=2.5, slAboveSma=50.0, slBelowSma=30.0, tpPts=50.0, tpMult=3.0,
          trailTrigger=30.0, trailDist=8.0, trailDistStrong=10.0,
          tExpBars=20, tExpHardBars=20, tExpHardSlope=1.0, cooldownBars=10, cooldownBarsRTH=10)

def st(tr,slip=0.0):
    n=len(tr); net=sum(t[3]-slip for t in tr); w=sum(1 for t in tr if t[3]-slip>0)
    gw=sum(t[3]-slip for t in tr if t[3]-slip>0); gl=sum(t[3]-slip for t in tr if t[3]-slip<=0)
    return n,net,(gw/abs(gl) if gl else 99),(w/n*100 if n else 0)

if __name__=="__main__":
    bars=bt.load(); b5=load5()
    for name,data in [('3wk',bars),('5yr',b5)]:
        base=bt.run(data,BASE)
        db =bt.run(data,dict(BASE,enableDeepBlock=True))
        dbo=bt.run(data,dict(BASE,enableDeepBlock=True,enableDeepLossOppBlock=True))
        print(f'=== {name} ===')
        for slip in (0.0,1.0):
            for lbl,tr in [('BASE(no block)',base),('deepLoss shallow-block',db),('deepLoss OPP-block',dbo)]:
                n,net,pf,w=st(tr,slip)
                print(f'  slip{slip} {lbl:<24} {n:>5}tr net{net:>7.0f} PF{pf:.2f} win{w:.0f}%')
        rem=[t for t in base if t not in dbo]
        rw=sum(1 for t in rem if t[3]>0)
        print(f'  OPP-block removes {len(rem)} trades, {rw/len(rem)*100 if rem else 0:.0f}% winners, net {sum(t[3] for t in rem):.0f}')
        print()
