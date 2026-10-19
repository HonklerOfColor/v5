import pandas as pd, numpy as np, json, itertools
from numba import njit
from scipy.stats import norm, skew, kurtosis

START, END = "2020-01-01", "2026-09-30"
IS_END, OOS_START = "2023-12-31", "2024-01-01"
EXPL = set("""XAU XAG PAXG XAUT CL BZ DEFI BTCDOM USDC BUSD TUSD USDP PAX DAI FDUSD USDE USD1 RLUSD PYUSD EUR EURI AEUR GBP AUD BRL TRY
UST XUSD U WBTC WBETH BETH SUSD USDS BFUSD TSLA NVDA MSTR INTC QQQ SPY SAMSUNG SKHYNIX SKHY SNDK SOXL SOXS SPCX MRVL CRCL MU EWY SNXX
DRAM KORU AAPL AMZN GOOGL META MSFT COIN HOOD DOTECO FOOTBALL BLUEBIRD""".split())

def _split(c, v, f=None, gap=7):
    """Ticker-Neustarts (z. B. LUNA 2.0) trennen: Lücke > gap Tage -> früheres Segment als SYM_pre."""
    newc = {}; newv = {}; newf = {}
    for s in list(c.columns):
        x = c[s]; valid = x.notna().values
        if valid.sum() == 0: continue
        pos = np.where(valid)[0]; gaps = np.where(np.diff(pos) > gap)[0]
        if len(gaps) == 0: continue
        cut = c.index[pos[gaps[-1] + 1]]
        pre = s[:-4] + "PRE" + "USDT"
        newc[pre] = x.where(x.index < cut); newv[pre] = v[s].where(v.index < cut)
        c[s] = x.where(x.index >= cut); v[s] = v[s].where(v.index >= cut)
        if f is not None and s in f.columns:
            newf[pre] = f[s].where(f.index < cut); f[s] = f[s].where(f.index >= cut)
    c = pd.concat([c, pd.DataFrame(newc)], axis=1); v = pd.concat([v, pd.DataFrame(newv)], axis=1)
    if f is not None: f = pd.concat([f, pd.DataFrame(newf, index=f.index)], axis=1)
    return c, v, f, list(newc)

def load(kind):
    c = pd.read_pickle(f"{kind}_close.pkl"); v = pd.read_pickle(f"{kind}_qvol.pkl")
    if kind == "perp":
        f = pd.read_pickle("funding.pkl"); c, v, f, sp = _split(c, v, f)
        f.to_pickle("funding_split.pkl")
    else:
        c, v, _, sp = _split(c, v)
    return c, v

def excl_set(close):
    ex = set()
    for s in close.columns:
        b = s[:-4]
        if b in EXPL or (b.endswith("B") and len(b) >= 3 and b[:-1] in EXPL): ex.add(s); continue
        r = close[s].dropna().pct_change().dropna()
        if len(r) < 30: continue
        if r.std() * np.sqrt(365) < 0.05: ex.add(s); continue
        if r.index.min() < pd.Timestamp("2025-01-01"): continue  # TradFi-Perps/Stock-Token erst ab 2025
        wk = r[r.index.dayofweek >= 5].abs().mean(); wd = r[r.index.dayofweek < 5].abs().mean()
        if wd > 0 and wk / wd < 0.4: ex.add(s)
    return ex

def universe(close, qvol, B, ex, min_hist=60, min_med=2e6, extra_ok=None):
    med = qvol.rolling(30, min_periods=20).median()
    hist = close.notna().cumsum()
    U = pd.DataFrame(False, index=close.index, columns=close.columns)
    cols = [c for c in close.columns if c not in ex]
    for me in close.index[close.index.is_month_end]:
        if me < pd.Timestamp("2019-11-30"): continue
        row = med.loc[me, cols]
        ok = (hist.loc[me, cols] >= min_hist) & (row >= min_med) & close.loc[me, cols].notna()
        if extra_ok is not None: ok &= extra_ok.loc[me, cols]
        sel = row[ok].sort_values(ascending=False).index[:B]
        nxt = (close.index > me) & (close.index <= me + pd.offsets.MonthEnd(1))
        U.loc[nxt, list(sel)] = True
    return U & close.notna()

@njit(cache=True)
def donchian_combo(c, sig, windows, vt, cap):
    T = len(c); W = np.zeros(T); ch = np.zeros(T, np.bool_)
    for n in windows:
        pos = 0; stop = np.nan
        for t in range(T):
            prev = pos
            if np.isnan(c[t]) or np.isnan(sig[t]) or t < n - 1:
                pos = 0
            else:
                mx = -1e300; mn = 1e300; bad = False
                for k in range(t - n + 1, t + 1):
                    v = c[k]
                    if np.isnan(v):
                        bad = True; break
                    if v > mx: mx = v
                    if v < mn: mn = v
                if bad:
                    pos = 0
                else:
                    mid = 0.5 * (mx + mn)
                    if pos == 0:
                        if c[t] >= mx:
                            pos = 1; stop = mid
                    else:
                        if c[t] <= stop:
                            pos = 0
                        elif mid > stop:
                            stop = mid
            if pos != prev: ch[t] = True
            if pos == 1 and sig[t] > 0:
                W[t] += min(vt / sig[t], cap) / len(windows)
    return W, ch

def trend_panel(close, cols, windows, vt, cap):
    r = close[cols].pct_change(fill_method=None)
    sig = r.rolling(90, min_periods=90).std() * np.sqrt(365)
    W = pd.DataFrame(0.0, index=close.index, columns=cols); CH = pd.DataFrame(False, index=close.index, columns=cols)
    w = np.array(windows, dtype=np.int64)
    for s in cols:
        a, b = donchian_combo(close[s].values.astype(np.float64), sig[s].values.astype(np.float64), w, float(vt), float(cap))
        W[s] = a; CH[s] = b
    return W, CH

def funding_filter(Fd, cols, thr=0.0003, L=7):
    per8h = Fd[cols].fillna(0).rolling(L, min_periods=L).mean() / 3.0
    return per8h > thr

def run_engine(close, TW, mode, cost, funding=None, K=None, minN=None, lotQ=None, thr=0.2, flags=None, rebal=None, start=START, end=END, liq_short=False, high=None):
    """mode 'trend': trade if flag or |T-P|>thr|T| or close-out; mode 'rebal': trade only on rebal days (+forced close-outs).
    Weights TW are fractions of equity, decided at close t, effective from t+1."""
    idx = close.loc[start:end].index
    cols = TW.columns
    C = close.loc[:, cols].reindex(idx).values
    R = close.loc[:, cols].pct_change(fill_method=None).reindex(idx).values
    TWv = TW.reindex(idx).fillna(0).values
    Fv = funding.reindex(index=idx, columns=cols).fillna(0).values if funding is not None else np.zeros_like(C)
    FLv = flags.reindex(idx).fillna(False).values if flags is not None else np.zeros_like(C, dtype=bool)
    HI = high.reindex(index=idx, columns=cols).values if high is not None else None
    RB = rebal.reindex(idx).fillna(False).values if rebal is not None else None
    n = len(cols); P = np.zeros(n); E = 1.0 if K is None else float(K); ent = np.full(n, np.nan); entN = np.zeros(n); nliq = 0
    mN = np.zeros(n) if minN is None else minN.reindex(cols).values
    lq = np.zeros(n) if lotQ is None else lotQ.reindex(cols).fillna(0).values
    eq = np.zeros(len(idx)); turn = np.zeros(len(idx)); gross = np.zeros(len(idx)); fund = np.zeros(len(idx)); costs = np.zeros(len(idx))
    for t in range(len(idx)):
        price = C[t]; r = R[t]
        if t > 0:
            dead = np.isnan(price) & (P != 0)
            rr = np.where(np.isnan(r), 0.0, r)
            pnl = np.sum(P * rr) - np.sum(P * Fv[t])
            fund[t] = -np.sum(P * Fv[t])
            E += pnl; P = P * (1 + rr)
            if liq_short:
                trig = price if HI is None else np.where(np.isnan(HI[t]), price, np.maximum(HI[t], price))
                liq = (P < 0) & (trig >= 2.0 * ent)
                if liq.any():
                    # isolierte 1x-Marge: Verlust auf Einstands-Notional begrenzt -> Überschuss zurückbuchen
                    excess = (-P[liq] - 2.0 * entN[liq])  # aktueller Verlust - Einstandsnotional (>0)
                    E += np.sum(excess); P[liq] = 0; nliq += int(liq.sum())
            if dead.any():
                c0 = np.sum(np.abs(P[dead])) * cost; E -= c0; costs[t] += c0; turn[t] += np.sum(np.abs(P[dead])); P[dead] = 0
        if E <= 0:
            eq[t:] = 0; break
        T = TWv[t] * E
        T = np.where(np.isnan(price), 0.0, T)
        if K is not None:
            lotusd = lq * np.where(np.isnan(price), 0, price)
            q = np.where(lotusd > 0, np.sign(T) * np.floor(np.abs(T) / np.where(lotusd > 0, lotusd, 1) + 1e-9) * lotusd, T)
            T = np.where(np.abs(q) < mN, 0.0, q)
        delta = T - P
        if mode == "trend":
            trade = FLv[t] | (np.abs(delta) > thr * np.abs(T)) | ((T == 0) & (P != 0))
        else:
            trade = (RB[t] & (delta != 0)) | ((T == 0) & (P != 0) & np.isnan(price))
        if K is not None:
            trade &= (np.abs(delta) >= mN) | (T == 0)
        trade &= (delta != 0)
        d = np.where(trade, delta, 0.0)
        c1 = np.sum(np.abs(d)) * cost
        E -= c1; costs[t] += c1; turn[t] += np.sum(np.abs(d))
        newP = P + d
        if liq_short:
            pz = np.where(np.isnan(price) | (price <= 0), 1.0, price)
            uo = np.abs(P) / pz; un = np.abs(newP) / pz
            flip = trade & ((np.sign(newP) != np.sign(P)) | (P == 0))
            grow = trade & ~flip & (un > uo)
            ent = np.where(flip, price, np.where(grow, (uo * np.nan_to_num(ent) + (un - uo) * price) / np.where(un > 0, un, 1), ent))
            entN = np.where(trade, un * np.nan_to_num(ent), entN)
        P = newP
        eq[t] = E; gross[t] = np.sum(np.abs(P))
    eqs = pd.Series(eq, idx)
    ret = eqs.pct_change().fillna(0)
    E0 = 1.0 if K is None else float(K)
    ret.iloc[0] = eqs.iloc[0] / E0 - 1
    base = eqs.shift(1).fillna(E0)
    return dict(ret=ret, eq=eqs, turnover=pd.Series(turn, idx) / base, gross=pd.Series(gross, idx) / eqs.replace(0, np.nan),
                funding=pd.Series(fund, idx) / base, costs=pd.Series(costs, idx) / base, n_liq=nliq)

def stats(r, gross=None, turnover=None):
    r = r.dropna()
    if len(r) < 20: return {}
    eq = (1 + r).cumprod(); yrs = len(r) / 365
    cagr = eq.iloc[-1] ** (1 / yrs) - 1 if eq.iloc[-1] > 0 else -1
    vol = r.std() * np.sqrt(365); sh = r.mean() / r.std() * np.sqrt(365) if r.std() > 0 else np.nan
    dn = r[r < 0].std() * np.sqrt(365); dd = (eq / eq.cummax() - 1).min()
    m = (1 + r).resample("ME").prod() - 1
    out = dict(TotRet=eq.iloc[-1] - 1, CAGR=cagr, Vol=vol, Sharpe=sh, Sortino=(r.mean() * 365 / dn if dn > 0 else np.nan), MaxDD=dd,
               Calmar=(cagr / -dd if dd < 0 else np.nan), PosMonths=(m > 0).mean(), WorstMonth=m.min())
    if gross is not None: out["AvgExpo"] = gross.loc[r.index].mean()
    if turnover is not None: out["Turnover_pa"] = turnover.loc[r.index].sum() / yrs
    return out

def sharpe(r):
    r = r.dropna(); return r.mean() / r.std() * np.sqrt(365) if r.std() > 0 else np.nan

def deflated_sharpe(r, trial_sr_annual):
    r = r.dropna().values; T = len(r); sr = r.mean() / r.std()
    g3 = skew(r); g4 = kurtosis(r, fisher=False)
    N = len(trial_sr_annual); V = np.var(np.array(trial_sr_annual) / np.sqrt(365), ddof=1)
    emc = 0.5772156649
    sr0 = np.sqrt(V) * ((1 - emc) * norm.ppf(1 - 1 / N) + emc * norm.ppf(1 - 1 / (N * np.e))) if N > 1 else 0.0
    den = np.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2)
    dsr = norm.cdf((sr - sr0) * np.sqrt(T - 1) / den)
    psr = norm.cdf((sr - 0) * np.sqrt(T - 1) / den)
    return dict(DSR=dsr, PSR0=psr, SR0_annual=sr0 * np.sqrt(365), N=N)

def pbo_cscv(M, S=16):
    M = np.asarray(M); T = len(M) // S * S; M = M[-T:]; N = M.shape[1]
    blocks = np.array_split(np.arange(T), S); lam = []; degr = []
    for comb in itertools.combinations(range(S), S // 2):
        isx = np.concatenate([blocks[i] for i in comb]); oos = np.concatenate([blocks[i] for i in range(S) if i not in comb])
        si = M[isx].mean(0) / M[isx].std(0); so = M[oos].mean(0) / M[oos].std(0)
        k = np.nanargmax(si); rank = (so < so[k]).sum() + 1
        w = rank / (N + 1); lam.append(np.log(w / (1 - w))); degr.append((si[k], so[k]))
    lam = np.array(lam); d = np.array(degr)
    return dict(PBO=float((lam <= 0).mean()), median_logit=float(np.median(lam)),
                IS_best_SR=float(d[:, 0].mean() * np.sqrt(365)), OOS_of_best_SR=float(d[:, 1].mean() * np.sqrt(365)))

def walk_forward(rets: dict, years=range(2022, 2027), first=START):
    out = []; picks = {}
    for y in years:
        tr = {k: sharpe(v.loc[first:f"{y-1}-12-31"]) for k, v in rets.items()}
        best = max(tr, key=lambda k: tr[k] if tr[k] == tr[k] else -9)
        picks[y] = best; out.append(rets[best].loc[f"{y}-01-01":f"{y}-12-31"])
    return pd.concat(out), picks

def block_bootstrap(rmat, n_paths=10000, horizon=365, mean_block=20, seed=7):
    rng = np.random.default_rng(seed); T = len(rmat); p = 1.0 / mean_block
    idx = np.empty((n_paths, horizon), dtype=np.int64)
    cur = rng.integers(0, T, n_paths)
    for h in range(horizon):
        newb = rng.random(n_paths) < p
        cur = np.where(newb, rng.integers(0, T, n_paths), (cur + 1) % T)
        idx[:, h] = cur
    res = {}
    for j, name in enumerate(rmat.columns):
        x = rmat.values[:, j][idx]
        eq = np.cumprod(1 + x, axis=1); fin = eq[:, -1] - 1
        dd = (eq / np.maximum.accumulate(eq, axis=1) - 1).min(axis=1)
        res[name] = dict(fin=fin, dd=dd)
    return res
