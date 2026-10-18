# Alternativen, zweite Runde: Funding, Carry, Momentum, Pullback, Kapital

Erzeugt 2026-10-18T16:38Z. Gleiche Kerzen und Kosten wie im Strategie-Vergleich (28 Coins, 2025-10-18 bis 2026-10-18, Out-of-Sample ab 2026-06-20), aber mit **echten Funding-Raten** statt der Pauschale: Long zahlt, Short bekommt.

## Funding-Raten: Bitget (90 Tage verfügbar) gegen Binance als Jahres-Proxy

Bitget liefert nur 90 Tage Historie. Für das Jahr dient Binance als Näherung. In den 90 gemeinsamen Tagen lag Bitget im Mittel höher; die Backtests mit Binance-Raten sind für Short-Seiten eher zu pessimistisch, für Long-Seiten eher zu optimistisch.

| Coin | Bitget % p.a. (90 T) | Binance % p.a. (90 T) | Korrelation | Binance % p.a. (Jahr) |
| --- | ---: | ---: | ---: | ---: |
| AAVEUSDT | +6.3 | +4.6 | 0.14 | +2.8 |
| ADAUSDT | +4.4 | +4.8 | 0.45 | +1.9 |
| APTUSDT | +7.4 | +3.2 | 0.53 | -13.7 |
| ARBUSDT | +6.9 | +0.7 | 0.26 | +1.9 |
| AVAXUSDT | +7.5 | +4.6 | 0.55 | -0.3 |
| BNBUSDT | +8.4 | +4.2 | 0.32 | +2.1 |
| BTCUSDT | +5.7 | +5.7 | 0.15 | +3.3 |
| DOGEUSDT | +8.7 | +6.3 | 0.18 | +3.0 |
| DOTUSDT | +9.5 | +4.4 | 0.26 | -5.2 |
| ENAUSDT | +8.1 | +6.4 | 0.08 | -0.9 |
| ETHUSDT | +6.4 | +4.5 | 0.31 | +2.5 |
| FILUSDT | +7.4 | +5.1 | 0.26 | -1.6 |
| HYPEUSDT | +5.7 | +6.8 | 0.55 | +5.4 |
| INJUSDT | +4.1 | -0.8 | 0.55 | -10.4 |
| LINKUSDT | +7.4 | +6.1 | 0.33 | +4.6 |
| LTCUSDT | +8.5 | +5.5 | 0.32 | +3.1 |
| NEARUSDT | +8.5 | +6.1 | 0.25 | +3.5 |
| ONDOUSDT | +8.5 | +5.3 | 0.33 | +0.1 |
| OPUSDT | +9.3 | +4.2 | 0.29 | -0.4 |
| PEPEUSDT | +5.1 | +4.4 | 0.66 | -0.8 |
| SOLUSDT | +4.7 | +3.4 | 0.48 | -0.5 |
| SUIUSDT | +6.8 | +4.8 | 0.41 | +3.1 |
| TIAUSDT | +7.8 | +6.2 | 0.16 | +1.7 |
| TRXUSDT | -5.6 | -11.5 | 0.85 | -8.6 |
| UNIUSDT | +8.0 | +7.0 | 0.23 | +4.4 |
| WLDUSDT | +7.2 | +0.4 | 0.64 | -6.0 |
| XRPUSDT | +7.5 | +3.6 | 0.51 | -0.0 |
| ZECUSDT | +5.9 | +6.0 | 0.48 | -8.5 |
| **Mittel** | +6.7 | +4.0 | 0.38 | -0.5 |

## Cash-and-Carry (Spot long, Perp short), 50 USDT

Kein Kursrisiko. Kapital halb Spot, halb Perp-Margin, also 25 USDT Perp-Notional. Kosten je Wechsel: Spot-Fee und Perp-Taker plus 2 bp auf jeder Seite.

| Variante | Spot-Fee | Abschnitt | Netto | Funding-Ertrag | Fees | Wechsel | Wochen in Cash |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| Rotation wöchentlich, 10 liquide | 0.1 % | IS | -1.74 | 0.47 | 2.21 | 25 | 6/35 |
| Rotation wöchentlich, 10 liquide | 0.1 % | OOS | -0.75 | 0.41 | 1.16 | 13 | 0/17 |
| Rotation wöchentlich, 10 liquide | 0.1 % | Jahr | -2.47 | 0.86 | 3.33 | 38 | 6/52 |
| Rotation wöchentlich, 28 Coins | 0.1 % | IS | -1.64 | 0.67 | 2.31 | 26 | 1/35 |
| Rotation wöchentlich, 28 Coins | 0.1 % | OOS | -1.09 | 0.42 | 1.51 | 17 | 0/17 |
| Rotation wöchentlich, 28 Coins | 0.1 % | Jahr | -2.69 | 1.08 | 3.77 | 43 | 1/52 |
| Rotation 28-Tage-Fenster, 10 liquide | 0.1 % | IS | -0.77 | 0.39 | 1.16 | 13 | 9/35 |
| Rotation 28-Tage-Fenster, 10 liquide | 0.1 % | OOS | +0.12 | 0.48 | 0.36 | 4 | 0/17 |
| Rotation 28-Tage-Fenster, 10 liquide | 0.1 % | Jahr | -0.65 | 0.86 | 1.52 | 17 | 9/52 |
| Rotation wöchentlich, 10 liquide | 0.2 % | IS | -2.94 | 0.46 | 3.40 | 25 | 6/35 |
| Rotation wöchentlich, 10 liquide | 0.2 % | OOS | -1.39 | 0.41 | 1.80 | 13 | 0/17 |
| Rotation wöchentlich, 10 liquide | 0.2 % | Jahr | -4.25 | 0.85 | 5.09 | 38 | 6/52 |
| Rotation wöchentlich, 28 Coins | 0.2 % | IS | -2.88 | 0.66 | 3.55 | 26 | 1/35 |
| Rotation wöchentlich, 28 Coins | 0.2 % | OOS | -1.91 | 0.42 | 2.34 | 17 | 0/17 |
| Rotation wöchentlich, 28 Coins | 0.2 % | Jahr | -4.69 | 1.06 | 5.75 | 43 | 1/52 |
| Rotation 28-Tage-Fenster, 10 liquide | 0.2 % | IS | -1.41 | 0.38 | 1.80 | 13 | 9/35 |
| Rotation 28-Tage-Fenster, 10 liquide | 0.2 % | OOS | -0.08 | 0.48 | 0.56 | 4 | 0/17 |
| Rotation 28-Tage-Fenster, 10 liquide | 0.2 % | Jahr | -1.49 | 0.85 | 2.34 | 17 | 9/52 |

Ein Coin, ein Jahr gehalten, Spot-Fee 0,1 %: Funding-Summe × 25 USDT minus zwei Wechselkosten.

| Coin | Funding-Ertrag | Netto Jahr |
| --- | ---: | ---: |
| BTCUSDT | +0.83 | +0.74 |
| ETHUSDT | +0.62 | +0.53 |
| SOLUSDT | -0.12 | -0.21 |
| XRPUSDT | -0.01 | -0.10 |
| DOGEUSDT | +0.75 | +0.66 |
| BNBUSDT | +0.53 | +0.44 |
| ADAUSDT | +0.48 | +0.39 |
| SUIUSDT | +0.78 | +0.69 |
| LINKUSDT | +1.14 | +1.05 |
| AVAXUSDT | -0.08 | -0.17 |

## Querschnitts-Momentum, wöchentlich, 28 Coins, gemeinsames Kapital

Top 3 long, Flop 3 short (oder nur long), Brutto-Exposure 100 % des Kapitals, kein Stop in der Woche, echtes Funding.

| Lookback | Richtung | Kapital | IS | OOS | Jahr | max DD Jahr | Trades | Fees Jahr |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 14 T | long+short | 50 | +11.47 | -3.50 | +5.59 | 29.4 % | 176 | 1.78 |
| 14 T | long+short | 1000 | +164.59 | -89.67 | +38.92 | 34.3 % | 193 | 38.88 |
| 14 T | nur long | 50 | -10.28 | +5.14 | -6.50 | 71.3 % | 85 | 1.14 |
| 14 T | nur long | 1000 | -312.23 | +94.97 | -279.84 | 75.4 % | 90 | 23.00 |
| 28 T | long+short | 50 | +4.73 | -8.23 | -5.25 | 27.4 % | 121 | 1.06 |
| 28 T | long+short | 1000 | +42.78 | -123.57 | -97.88 | 28.5 % | 141 | 24.01 |
| 28 T | nur long | 50 | -22.55 | +2.89 | -22.88 | 63.3 % | 56 | 0.56 |
| 28 T | nur long | 1000 | -541.68 | +100.76 | -514.16 | 69.8 % | 64 | 11.77 |
| 56 T | long+short | 50 | +13.21 | -15.86 | -3.57 | 32.4 % | 83 | 0.83 |
| 56 T | long+short | 1000 | +288.31 | -209.21 | +25.98 | 26.5 % | 89 | 18.68 |
| 56 T | nur long | 50 | +5.38 | +12.90 | +17.01 | 36.4 % | 35 | 0.62 |
| 56 T | nur long | 1000 | +94.78 | +343.28 | +440.14 | 37.7 % | 36 | 13.99 |

## Pullback im Trend (4h, RSI(2) unter 10 über SMA 200), je Symbol 50 USDT

| Variante | IS Summe | IS positiv | OOS Summe | OOS positiv | Jahr Summe | Jahr positiv | Trades | Fees |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| long+short | -31.66 | 3/28 | -21.50 | 4/28 | -52.55 | 2/28 | 1547 | 16.52 |
| nur long | -7.84 | 5/28 | -6.79 | 7/28 | -13.61 | 6/28 | 581 | 6.73 |
| long+short, RSI 5/95 | -16.75 | 7/28 | -16.94 | 7/28 | -33.61 | 4/28 | 830 | 8.82 |

## Trendfolge 40/20 auf 4h mit echtem Funding

### Je Symbol eigene 50 USDT, Risiko 1 %

| Funding | IS Summe | IS positiv | OOS Summe | OOS positiv | Jahr Summe | Jahr positiv | Funding Jahr |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Pauschale 0,01 %/8h | +2.51 | 12/28 | +29.09 | 18/28 | +25.71 | 14/28 | +8.96 |
| echt (Binance-Proxy) | +6.66 | 13/28 | +30.53 | 19/28 | +31.35 | 16/28 | +3.89 |

### Portfolio mit gemeinsamem Kapital: Skalierung über das Konto

Höchstens 5 Positionen, Signal-Rangfolge nach Ausbruchsstärke, Risiko 1 % je Trade, echtes Funding. Dieselbe Strategie, nur das Konto wächst. Prozent bezogen auf das Startkapital.

| Universum | Kapital | IS | OOS | Jahr | Jahr % | max DD Jahr | Trades Jahr | zu klein | PF Jahr |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 28 Coins | 50 | -6.56 | -1.90 | -7.31 | -14.6 % | 34.0 % | 325 | 571 | 0.87 |
| 28 Coins | 200 | -11.79 | -24.83 | -38.44 | -19.2 % | 36.7 % | 351 | 2 | 0.85 |
| 28 Coins | 500 | -26.84 | -58.27 | -81.74 | -16.3 % | 37.3 % | 349 | 0 | 0.87 |
| 28 Coins | 1000 | -55.41 | -112.54 | -158.29 | -15.8 % | 37.6 % | 349 | 0 | 0.88 |
| 28 Coins | 3000 | -171.32 | -336.49 | -482.94 | -16.1 % | 37.9 % | 349 | 0 | 0.88 |
| 28 Coins | 10000 | -577.35 | -1117.96 | -1613.60 | -16.1 % | 37.9 % | 349 | 0 | 0.88 |
| 10 liquide | 50 | -4.00 | +3.23 | -1.84 | -3.7 % | 30.3 % | 227 | 227 | 0.96 |
| 10 liquide | 200 | -24.08 | -2.32 | -27.41 | -13.7 % | 30.9 % | 263 | 6 | 0.86 |
| 10 liquide | 500 | -61.05 | -4.76 | -63.12 | -12.6 % | 31.2 % | 264 | 0 | 0.87 |
| 10 liquide | 1000 | -124.97 | -13.95 | -129.55 | -13.0 % | 31.5 % | 264 | 0 | 0.87 |
| 10 liquide | 3000 | -392.15 | -42.24 | -410.88 | -13.7 % | 32.0 % | 264 | 0 | 0.87 |
| 10 liquide | 10000 | -1325.29 | -141.91 | -1388.43 | -13.9 % | 32.1 % | 264 | 0 | 0.86 |

### Alle Signale nehmen: kein Platzlimit, gemeinsames Margin-Budget

Trendfolge lebt von wenigen großen Gewinnern. Mit 5 Plätzen verfallen Signale, und genau die fehlen dann. Hier gibt es kein Platzlimit; die Grenze ist nur das Margin-Budget (50 % des Kapitals bei Hebel 2). Risiko je Trade variiert, weil bis zu 28 Positionen gleichzeitig offen sein können und Krypto stark korreliert.

| Universum | Kapital | Risiko | IS | OOS | Jahr | Jahr % | max DD Jahr | Trades | zu klein | PF |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 28 Coins | 300 | 0.25 % | -8.06 | +9.31 | +3.49 | +1.2 % | 25.3 % | 970 | 531 | 1.01 |
| 28 Coins | 300 | 0.50 % | -21.87 | -39.13 | -56.44 | -18.8 % | 33.7 % | 865 | 888 | 0.88 |
| 28 Coins | 300 | 1.00 % | -75.31 | -48.04 | -103.38 | -34.5 % | 45.4 % | 607 | 1751 | 0.79 |
| 28 Coins | 1000 | 0.25 % | -42.93 | +31.33 | -14.14 | -1.4 % | 27.8 % | 1090 | 161 | 0.99 |
| 28 Coins | 1000 | 0.50 % | -94.21 | -109.89 | -192.69 | -19.3 % | 36.4 % | 903 | 757 | 0.88 |
| 28 Coins | 1000 | 1.00 % | -281.35 | -155.06 | -383.43 | -38.3 % | 47.1 % | 649 | 1599 | 0.76 |
| 28 Coins | 3000 | 0.25 % | -150.99 | +95.77 | -60.78 | -2.0 % | 28.4 % | 1088 | 160 | 0.98 |
| 28 Coins | 3000 | 0.50 % | -245.76 | -346.40 | -547.17 | -18.2 % | 35.7 % | 912 | 736 | 0.88 |
| 28 Coins | 3000 | 1.00 % | -739.79 | -349.95 | -991.07 | -33.0 % | 45.5 % | 690 | 1427 | 0.80 |
| 10 liquide | 300 | 0.25 % | -8.95 | +15.58 | +8.32 | +2.8 % | 14.7 % | 332 | 164 | 1.08 |
| 10 liquide | 300 | 0.50 % | -22.89 | +14.28 | -7.92 | -2.6 % | 28.8 % | 374 | 67 | 0.97 |
| 10 liquide | 300 | 1.00 % | -43.90 | +1.09 | -42.26 | -14.1 % | 38.7 % | 323 | 206 | 0.87 |
| 10 liquide | 1000 | 0.25 % | -35.94 | +54.62 | +19.66 | +2.0 % | 16.6 % | 389 | 4 | 1.05 |
| 10 liquide | 1000 | 0.50 % | -77.32 | +38.63 | -39.52 | -4.0 % | 30.4 % | 382 | 39 | 0.95 |
| 10 liquide | 1000 | 1.00 % | -153.69 | -3.59 | -158.40 | -15.8 % | 38.6 % | 327 | 193 | 0.86 |
| 10 liquide | 3000 | 0.25 % | -119.56 | +167.07 | +45.42 | +1.5 % | 17.1 % | 390 | 0 | 1.03 |
| 10 liquide | 3000 | 0.50 % | -245.76 | +107.86 | -140.33 | -4.7 % | 30.8 % | 382 | 39 | 0.95 |
| 10 liquide | 3000 | 1.00 % | -441.60 | -39.70 | -479.78 | -16.0 % | 38.2 % | 325 | 209 | 0.86 |

## Quartale, 1000 USDT gemeinsames Kapital, echtes Funding

| Quartal | B&H Median | Trend 28 Coins | Trend 10 liquide | Momentum 28 T l/s | Carry 10 liquide (50 USDT) |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2025-10-18 – 2026-01-17 | -20 % | +13.02 | -95.30 | -229.40 | -0.64 |
| 2026-01-17 – 2026-04-19 | -35 % | -51.06 | -79.23 | +143.81 | -0.64 |
| 2026-04-19 – 2026-07-19 | -15 % | -80.34 | +58.48 | +25.25 | -0.56 |
| 2026-07-19 – 2026-10-18 | +30 % | -16.74 | +11.48 | -17.72 | -0.69 |
