import pandas as pd, numpy as np, pickle, json
from lib import *
pc,_=load("perp"); sc,_=load("spot"); Fd=pd.read_pickle("funding_split.pkl"); H=pd.read_pickle("perp_high_split.pkl")
bp={x['symbol']:x for x in json.load(open('bitget_perp.json'))['data']}
bs={x['symbol']:x for x in json.load(open('bitget_spot.json'))['data']}
def specs(cols,venue):
    mn={};lq={}
    for c in cols:
        if venue=="perp":
            x=bp.get(c); mn[c]=float(x['minTradeUSDT']) if x else 5.0; lq[c]=float(x['sizeMultiplier']) if x else 0.0
        else:
            x=bs.get(c); mn[c]=float(x['minTradeUSDT']) if x else 10.0; lq[c]=0.0
    return pd.Series(mn),pd.Series(lq)
out={}
jobs={"A_spot":("TW_A_spot.pkl",sc,"trend",0.0015,None,"spot",False),
      "A_perp":("TW_A_perp.pkl",pc,"trend",0.0011,Fd,"perp",False),
      "A_perp_filter":("TW_A_perp+filter.pkl",pc,"trend",0.0011,Fd,"perp",False),
      "B_base":("TW_B.pkl",pc,"rebal",0.0011,Fd,"perp",False),
      "B_iso":("TW_B.pkl",pc,"rebal",0.0011,Fd,"perp",True)}
for name,(f,close,mode,cost,fund,venue,liq) in jobs.items():
    TW,X=pickle.load(open(f,"rb"))
    mn,lq=specs(TW.columns,venue)
    for K in [None,100,250,500,1000,5000]:
        kw=dict(flags=X) if mode=="trend" else dict(rebal=X)
        o=run_engine(close,TW,mode,cost,funding=fund,K=K,minN=mn if K else None,lotQ=lq if K else None,liq_short=liq,high=(H if liq else None),**kw)
        out[(name,K)]=o
        s_all=stats(o["ret"],o["gross"],o["turnover"]); s_oos=stats(o["ret"].loc[OOS_START:END])
        print(name,K,"ALL SR %.2f CAGR %.3f DD %.3f expo %.3f | OOS SR %.2f CAGR %.3f"%(s_all["Sharpe"],s_all["CAGR"],s_all["MaxDD"],s_all["AvgExpo"],s_oos["Sharpe"],s_oos["CAGR"]),flush=True)
pickle.dump(out,open("resCap.pkl","wb"))
