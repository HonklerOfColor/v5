import pandas as pd, numpy as np, pickle, json, time
from lib import *
t0=time.time()
pc,pv=load("perp"); sc,sv=load("spot"); Fd=pd.read_pickle("funding_split.pkl")
exP=excl_set(pc); exS=excl_set(sc)
json.dump({"perp":sorted(exP),"spot":sorted(exS)},open("excluded.json","w"),indent=0)
WSETS={"all":[5,10,20,30,60,90,150,250,360],"short":[5,10,20,30],"long":[60,90,150,250,360]}
BS=[5,10,20]; VTS=[0.25,0.50]
COST={"spot":0.0015,"perp":0.0011}
U={(v,B):universe(c,q,B,ex) for v,(c,q,ex) in {"spot":(sc,sv,exS),"perp":(pc,pv,exP)}.items() for B in BS}
pickle.dump(U,open("univA.pkl","wb"))
res={}
for venue,close,cap in [("spot",sc,1.0),("perp",pc,2.0)]:
    cols=sorted(set().union(*[set(U[(venue,B)].columns[U[(venue,B)].any()]) for B in BS]))
    print(venue,"coins ever in universe:",len(cols),flush=True)
    filt=funding_filter(Fd.reindex(columns=pc.columns),cols) if venue=="perp" else None
    for wn,ws in WSETS.items():
        for vt in VTS:
            W,CH=trend_panel(close,cols,ws,vt,cap)
            variants=[("",W,CH)]
            if venue=="perp":
                Wf=W.where(~filt,0.0); CHf=CH|(filt.astype(int).diff().fillna(0)!=0)
                variants.append(("+filter",Wf,CHf))
            for suf,WW,CC in variants:
                for B in BS:
                    Uv=U[(venue,B)][cols]
                    TW=WW*Uv/B; FL=CC|(Uv.astype(int).diff().fillna(0)!=0)
                    key=(venue+suf,wn,B,vt)
                    out=run_engine(close,TW,"trend",COST[venue],funding=(Fd if venue=="perp" else None),flags=FL)
                    res[key]=out
                    if wn=="all" and B==10 and vt==0.25:
                        mk=run_engine(close,TW,"trend",0.0002 if venue=="perp" else 0.0008,funding=(Fd if venue=="perp" else None),flags=FL)
                        res[key+("optcost",)]=mk
                        pickle.dump((TW,FL),open(f"TW_A_{venue}{suf}.pkl","wb"))
            print(venue,wn,vt,round(time.time()-t0),flush=True)
pickle.dump(res,open("resA.pkl","wb"))
for k in [("spot","all",10,0.25),("perp","all",10,0.25),("perp+filter","all",10,0.25)]:
    for p,(a,b) in {"IS":(START,IS_END),"OOS":(OOS_START,END)}.items():
        s=stats(res[k]["ret"].loc[a:b],res[k]["gross"],res[k]["turnover"]); print(k,p,{x:round(y,3) for x,y in s.items()})
