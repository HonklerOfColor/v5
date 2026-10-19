import sys,os; sys.path.insert(0,"/workspace/research/bt2"); os.chdir("/workspace/research/bt2")
import pandas as pd,numpy as np,pickle,json
from lib import *
sc,_=load("spot"); C=sc[["BTCUSDT","ETHUSDT"]].loc["2017-08-17":END]
COST=0.0015
def sig(c,kind):
    if kind.startswith("SMA"): n=int(kind[3:]); m=c.rolling(n,min_periods=n).mean(); return (c>m).astype(float).where(m.notna())
    if kind.startswith("EMA"):
        a,b=map(int,kind[3:].split("/")); ea=c.ewm(span=a,adjust=False,min_periods=a).mean(); eb=c.ewm(span=b,adjust=False,min_periods=b).mean()
        x=(ea>eb).astype(float); x[c.index<c.index[0]+pd.Timedelta(days=b)]=np.nan; return x
    if kind=="ENS":
        ss=[sig(c,f"SMA{n}") for n in [20,50,100,150,200]]; return pd.concat(ss,axis=1).mean(axis=1,skipna=False)
KINDS=["SMA50","SMA100","SMA200","EMA10/20","EMA20/50","ENS"]
def weights(kind,freq,assets=("BTCUSDT","ETHUSDT")):
    W={}
    for a in assets:
        s=sig(C[a],kind)
        if freq=="W":
            s=s.where(s.index.dayofweek==6).ffill()
        W[a]=s/len(assets)
    W=pd.DataFrame(W)
    FL=W.diff().fillna(0)!=0
    return W.fillna(0),FL
def run(kind,freq,assets=("BTCUSDT","ETHUSDT"),start="2018-03-05",end=END,K=None,cost=COST):
    W,FL=weights(kind,freq,assets)
    mn=pd.Series(1.0,index=list(assets)) if K else None; lq=pd.Series(0.0,index=list(assets)) if K else None
    return run_engine(C,W,"trend",cost,flags=FL,K=K,minN=mn,lotQ=lq,start=start,end=end)
res={}
for k in KINDS:
    for f in ["D","W"]:
        res[(k,f)]=run(k,f)
for a in ["BTCUSDT","ETHUSDT"]:
    res[("ENS","D",a)]=run("ENS","D",(a,))
    res[("EMA10/20","D",a)]=run("EMA10/20","D",(a,))
for K in [100,500,1000]:
    res[("ENS","D","K",K)]=run("ENS","D",K=K)
res[("ENS","D","cost008")]=run("ENS","D",cost=0.0008)
# benchmarks
R=C.pct_change().loc["2018-03-05":END].fillna(0)
bh={"BTC B&H":R["BTCUSDT"],"ETH B&H":R["ETHUSDT"]}
w=pd.DataFrame(0.5,index=R.index,columns=R.columns); 
# 50/50 monthly rebalanced
out=[]
for m,g in R.groupby(R.index.to_period("M")):
    e=(1+g).cumprod(); eq=0.5*e.iloc[:,0]+0.5*e.iloc[:,1]; prev=np.r_[1.0,eq.values[:-1]]; out.append(pd.Series(eq.values/prev-1,g.index))
bh["50/50 B&H"]=pd.concat(out)
A=pickle.load(open("/workspace/research/bt2/resA.pkl","rb")); bh["A-Spot (bt2)"]=A[("spot","all",10,0.25)]["ret"]
pickle.dump((res,bh),open("/workspace/research/bt3/resTF.pkl","wb"))
for p,(a,b) in {"Pre 2018-03..2019":("2018-03-05","2019-12-31"),"IS":(START,IS_END),"OOS":(OOS_START,END),"Gesamt20":(START,END),"Lang18":("2018-03-05",END)}.items():
    print("==",p)
    for k in [("ENS","D"),("ENS","W"),("EMA10/20","D"),("SMA200","D")]:
        s=stats(res[k]["ret"].loc[a:b],res[k]["gross"],res[k]["turnover"]); print(k,"SR %.2f CAGR %.1f%% DD %.1f%% expo %.2f TO %.1f"%(s["Sharpe"],s["CAGR"]*100,s["MaxDD"]*100,s["AvgExpo"],s["Turnover_pa"]))
    for n,r in bh.items():
        s=stats(r.loc[a:b]); 
        if s: print(n,"SR %.2f CAGR %.1f%% DD %.1f%%"%(s["Sharpe"],s["CAGR"]*100,s["MaxDD"]*100))
