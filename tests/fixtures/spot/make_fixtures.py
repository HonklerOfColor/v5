"""Erzeugt reference.json mit der Referenz-Implementierung aus docs/spot_modules/code (lib.py, tf.py).

Aufruf (braucht pandas, numpy, numba, scipy; der Bot selbst braucht sie nicht):
    python3 tests/fixtures/spot/make_fixtures.py

Der Datensatz ist synthetisch und deterministisch (Seed 20261018). Vier Coins über 520 Tage ab 2024-01-01:
- AAAUSDT  durchgehend
- BBBUSDT  späteres Listing (ab Tag 80)
- CCCUSDT  Lücke (Tage 200–209 fehlen) und Delisting ab Tag 450
- DDDUSDT  durchgehend, niedriges Volumen (fällt an der 2-Mio-Regel)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "docs" / "spot_modules" / "code"))
from lib import run_engine, trend_panel, universe  # noqa: E402

WINDOWS = [5, 10, 20, 30, 60, 90, 150, 250, 360]
B = 3
VT, CAP, COST, THR = 0.25, 1.0, 0.0015, 0.2
N = 520


def sig_ens(c: pd.Series) -> pd.Series:
    """Kopie von tf.sig(c, "ENS") / tf.sig(c, "SMAn"), ohne die Modul-Nebenwirkungen von tf.py."""
    parts = []
    for n in [20, 50, 100, 150, 200]:
        m = c.rolling(n, min_periods=n).mean()
        parts.append((c > m).astype(float).where(m.notna()))
    return pd.concat(parts, axis=1).mean(axis=1, skipna=False)


def main() -> None:
    rng = np.random.default_rng(20261018)
    idx = pd.date_range("2024-01-01", periods=N, freq="D")
    closes = {}
    vols = {}
    for name, start, vol, seed_vol in [("AAAUSDT", 100.0, 0.035, 9e6), ("BBBUSDT", 2.0, 0.05, 6e6),
                                       ("CCCUSDT", 0.5, 0.04, 4e6), ("DDDUSDT", 30.0, 0.03, 1.2e6)]:
        rets = rng.normal(0.0008, vol, N)
        path = start * np.exp(np.cumsum(rets))
        qv = seed_vol * np.exp(rng.normal(0, 0.3, N))
        closes[name] = path
        vols[name] = qv
    close = pd.DataFrame(closes, index=idx)
    qvol = pd.DataFrame(vols, index=idx)
    close.iloc[:80, 1] = np.nan
    qvol.iloc[:80, 1] = np.nan
    close.iloc[200:210, 2] = np.nan
    qvol.iloc[200:210, 2] = np.nan
    close.iloc[450:, 2] = np.nan
    qvol.iloc[450:, 2] = np.nan

    cols = list(close.columns)
    W, CH = trend_panel(close, cols, WINDOWS, VT, CAP)
    U = universe(close, qvol, B, set())
    TW = W * U / B
    FL = CH | (U.astype(int).diff().fillna(0) != 0)
    ideal = run_engine(close, TW, "trend", COST, flags=FL, start=str(idx[0].date()), end=str(idx[-1].date()))
    mn = pd.Series(10.0, index=cols)
    lq = pd.Series(0.0, index=cols)
    capped = run_engine(close, TW, "trend", COST, flags=FL, K=500.0, minN=mn, lotQ=lq,
                        start=str(idx[0].date()), end=str(idx[-1].date()))
    ens = {name: sig_ens(close[name]) for name in ("AAAUSDT", "BBBUSDT")}
    tf_W = pd.DataFrame({name: ens[name] / 2 for name in ens})
    tf_FL = tf_W.diff().fillna(0) != 0
    tf_run = run_engine(close[list(ens)], tf_W.fillna(0), "trend", COST, flags=tf_FL,
                        K=500.0, minN=pd.Series(1.0, index=list(ens)), lotQ=pd.Series(0.0, index=list(ens)),
                        start=str(idx[0].date()), end=str(idx[-1].date()))
    universe_by_month = {}
    for me in idx[idx.is_month_end]:
        nxt = U.loc[me + pd.Timedelta(days=1):me + pd.offsets.MonthEnd(1)]
        if len(nxt):
            universe_by_month[(me + pd.Timedelta(days=1)).strftime("%Y-%m")] = sorted(nxt.columns[nxt.any()].tolist())

    def col(frame, name):
        return [None if pd.isna(v) else float(v) for v in frame[name].tolist()]

    out = {
        "note": "Erzeugt mit docs/spot_modules/code/lib.py (trend_panel, universe, run_engine) und tf.sig ENS; siehe make_fixtures.py",
        "windows": WINDOWS, "B": B, "VT": VT, "cap": CAP, "cost": COST, "threshold": THR,
        "dates": [d.strftime("%Y-%m-%d") for d in idx],
        "closes": {name: col(close, name) for name in cols},
        "qvol": {name: col(qvol, name) for name in cols},
        "W": {name: col(W, name) for name in cols},
        "CH": {name: [bool(v) for v in CH[name].tolist()] for name in cols},
        "TW": {name: col(TW, name) for name in cols},
        "FL": {name: [bool(v) for v in FL[name].tolist()] for name in cols},
        "universe_by_month": universe_by_month,
        "equity_ideal": [float(v) for v in ideal["eq"].tolist()],
        "equity_min10_k500": [float(v) for v in capped["eq"].tolist()],
        "ens": {name: col(pd.DataFrame(ens), name) for name in ens},
        "tf_TW": {name: col(tf_W.fillna(0), name) for name in ens},
        "tf_FL": {name: [bool(v) for v in tf_FL[name].tolist()] for name in ens},
        "tf_equity_min1_k500": [float(v) for v in tf_run["eq"].tolist()],
    }
    target = Path(__file__).with_name("reference.json")
    target.write_text(json.dumps(out), encoding="utf-8")
    print(f"{target}: {target.stat().st_size} Bytes, Equity ideal Ende {out['equity_ideal'][-1]:.4f}, "
          f"K500 Ende {out['equity_min10_k500'][-1]:.4f}, TF Ende {out['tf_equity_min1_k500'][-1]:.4f}")
    print("Universum je Monat:", universe_by_month)


if __name__ == "__main__":
    main()
