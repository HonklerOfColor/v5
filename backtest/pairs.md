# Pairs-Trading auf Sektor-Paaren

Erzeugt 2026-10-18T17:16Z. 4h-Schlüsse, Spread = log(A) − log(B), z über 30 Tage, Einstieg |z| ≥ 2, Ausstieg |z| ≤ 0,5, Stop |z| ≥ 4, Zeitstopp 15 Tage. Je Bein 40 % des Kapitals (50 USDT), beide Beine Taker, echtes Funding je Bein. Out-of-Sample ab 2026-06-20. Paare nach Sektor festgelegt, nicht nach Ergebnis.

## Je Paar

| Paar | Sektor | Halbwertszeit (Tage) | IS | OOS | Jahr | Trades Jahr | Gewinner | Ziel/Stop/Zeit | Fees | Funding | max DD |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| BTCUSDT/ETHUSDT | die beiden Großen | 30.1 | +0.35 | -0.70 | -0.35 | 3 | 1 | 1/0/2 | 0.13 | -0.02 | 3.7 % |
| ETHUSDT/SOLUSDT | Smart-Contract-Plattformen | 19.0 | +1.10 | -0.95 | +0.15 | 6 | 4 | 4/2/0 | 0.24 | -0.04 | 5.9 % |
| OPUSDT/ARBUSDT | Ethereum-L2 | 200.6 | -8.40 | -8.74 | -15.68 | 42 | 17 | 9/27/6 | 1.72 | -0.29 | 40.6 % |
| UNIUSDT/AAVEUSDT | DeFi | 29.4 | +12.50 | +1.73 | +14.49 | 20 | 13 | 11/5/3 | 0.97 | -0.12 | 9.3 % |
| DOGEUSDT/PEPEUSDT | Memes | 42.3 | -2.32 | +0.68 | -1.67 | 27 | 11 | 10/12/4 | 1.21 | -0.29 | 16.1 % |
| NEARUSDT/APTUSDT | Alt-L1 | 13093.3 | -11.44 | -7.43 | -17.34 | 15 | 9 | 9/1/5 | 0.65 | -0.71 | 41.8 % |
| ADAUSDT/DOTUSDT | Alt-L1, ältere Generation | 14.4 | -2.29 | +0.04 | -2.18 | 37 | 14 | 8/23/6 | 1.61 | -0.18 | 14.3 % |
| LTCUSDT/ZECUSDT | Payment / Privacy | 74.4 | +11.40 | -14.99 | -6.75 | 21 | 11 | 9/9/3 | 1.11 | +0.26 | 40.7 % |
| SUIUSDT/APTUSDT | Move-L1 | 51.0 | +7.05 | +4.99 | +12.74 | 15 | 13 | 13/0/2 | 0.77 | -0.17 | 6.6 % |
| LINKUSDT/INJUSDT | Infrastruktur | 69.6 | -5.51 | -4.77 | -10.13 | 24 | 13 | 11/7/5 | 1.04 | +0.67 | 33.4 % |
| **Summe IS** | | | **+2.45** (5/10 positiv) | | | | | | | | |
| **Summe OOS** | | | | **-30.16** (4/10 positiv) | | | | | | | |
| **Summe FULL** | | | | | **-26.71** (3/10 positiv) | | | | | | |

## Nachbarschaft (Summe über 10 Paare)

| Lookback | Einstieg z | IS | OOS | Jahr | positiv Jahr | Trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 15 T | 1.5 | -69.56 | -26.58 | -94.21 | 1/10 | 403 |
| 15 T | 2.0 | -56.08 | -16.48 | -71.38 | 1/10 | 299 |
| 15 T | 2.5 | -32.08 | -7.73 | -39.81 | 2/10 | 221 |
| 30 T | 1.5 | -9.34 | -28.79 | -29.90 | 3/10 | 272 |
| 30 T | 2.0 | +2.45 | -30.16 | -26.71 | 3/10 | 210 |
| 30 T | 2.5 | -7.14 | -13.05 | -17.75 | 4/10 | 166 |
| 60 T | 1.5 | -13.87 | -11.74 | -14.00 | 3/10 | 208 |
| 60 T | 2.0 | -26.21 | -14.70 | -35.63 | 4/10 | 155 |
| 60 T | 2.5 | -22.65 | -12.18 | -28.92 | 4/10 | 130 |

## Quartale (Summe über 10 Paare, Basis-Parameter)

| Quartal | Netto | positiv |
| --- | ---: | ---: |
| 2025-10-18 – 2026-01-17 | +14.56 | 6/10 |
| 2026-01-17 – 2026-04-19 | +1.71 | 5/10 |
| 2026-04-19 – 2026-07-19 | -10.92 | 2/10 |
| 2026-07-19 – 2026-10-18 | -31.22 | 4/10 |
