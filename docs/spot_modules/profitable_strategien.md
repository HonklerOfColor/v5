# Welche Trading-Bot-Strategien sind belegbar profitabel?
**Krypto · Bitget USDT-M Perps · 100–1000 USDT · moderates Risiko**
Stand: 18.10.2026 · Rechercheumfang: über 60 Quellen gesichtet, Kern-Papers als PDF gelesen (pdftotext); dazu eine eigene Out-of-Sample-Nachprüfung (Abschnitt 4).

---

## 0. Kurzfassung (TL;DR)

1. **Es gibt keine Bot-Strategie, die für Privatanleger mit 100–1000 USDT nach Kosten nachweislich und dauerhaft deutlich profitabel ist.** Die meisten spektakulären Zahlen aus der Literatur haben gemeinsame Ursachen:
   - frühe, ineffiziente Marktphasen (2014–2021)
   - Small-Caps ohne Perps
   - Bruttozahlen oder Gebühren auf Institutions-Niveau
   - Post-Publication-Decay

   Die wenigen sauberen, kostenbewussten Replikationen auf **Binance-Perps ab 2020** finden fast durchgehend **kein signifikantes Edge**.
2. Deine eigenen Ergebnisse passen genau ins Bild:
   - **Funding-Arbitrage ist tot.** Ich habe es mit Binance-Vision-Daten selbst nachgerechnet: Die jährliche BTC/ETH-Funding-Summe fiel von 34 % (2021) auf 5,0 % (2025) und 1,8 % (2026 YTD), und Feb–Apr 2026 waren negativ.
   - **TSMOM ist schwach.**
3. **Eigene Nachprüfung des bestbelegten Trend-Papers** (Zarattini/Pagani/Barbon 2025, regelbasiert und ohne freie Parameter) auf Binance-Perps:
   - 2021 bis Paper-Ende (03/2025): Sharpe nur 0,6–0,8 statt 1,58.
   - **Echter Out-of-Sample-Zeitraum nach Veröffentlichung (20.03.2025–17.10.2026):** Sharpe −0,2 bis +0,25, also ≈ 0 % Rendite.
   - Was bleibt, ist **Drawdown-Schutz**: max. DD 8–16 % statt 53–69 % bei Buy&Hold. Es ist kein Alpha.
4. **Was am ehesten noch Sinn ergibt (Ranking):**
   1. Diversifiziertes, volatilitätsgesteuertes **Long/Flat-Trendfolgen** (Donchian-Ensemble, Top-10–20 Coins, täglich, wenig Turnover). Das ist ein Risikomanagement-Overlay, das in Bullenphasen Geld verdient und Crashes meidet. Erwartung: Sharpe 0,5–0,9 langfristig, kein BTC-Schlagen.
   2. **Cross-sektionaler Funding-Carry-Faktor** (long niedriges / short hohes Funding, dollar-neutral, wöchentlich). Einzige neuere Studie mit Walk-Forward-OOS-Sharpe von 0,39, aber PBO 0,81, also hohe Overfitting-Wahrscheinlichkeit.
   3. **BTC/ETH-Trend als Exposure-Filter** für eine sonst passive Position (wie der Bitwise-BITC-ETF). Live-Track-Record: 3 Jahre +37 % (BTC ca. +200 %), 1 Jahr −12 % (BTC ca. −27 %).
   4. *(Bedingt)* **Volatilitäts-Verkauf mit Regime-Filter** auf Deribit. Belegte Varianzprämie, aber Tail-Risiko, für Bitget nicht umsetzbar, und der Zugang aus Österreich/EU muss geprüft werden.
   5. *(Bedingt, Forschung)* **Token-Unlock-Shorts** auf Early-Stage-Token. Ereignisstudien sind konsistent negativ (−4,85 % Monats-Excess), aber es gibt kaum Live-Belege, und Borrow/Funding sowie Squeeze-Risiko kommen dazu.
5. **Nicht empfohlen** (Evidenz klar negativ oder für Retail nicht erreichbar):
   - Market Making
   - Grid-Bots
   - Cross-Exchange-Arbitrage
   - Cross-Exchange-Funding-Spreads (aktiv)
   - Liquidation-/OI-Signale
   - Intraday-ML
   - Pairs-Trading
   - Saisonalität
   - Copy-Trading

---

## 1. Methode und Evidenz-Kennzeichnung

| Kürzel | Bedeutung |
|---|---|
| **[B-PR]** | **Belegt, peer-reviewed** (Journal), Zahlen aus dem Paper selbst gelesen |
| **[B-WP]** | **Belegt, Working Paper/Preprint** (SSRN/arXiv/BIS), Zahlen aus dem PDF gelesen, noch nicht begutachtet |
| **[B-EIG]** | **Eigene Nachrechnung** mit Binance-Vision-Daten (Code unter `/workspace/research/oos/`) |
| **[R]** | **Research-Blog/Practitioner** mit nachvollziehbarer Methodik, nicht begutachtet |
| **[S]** | **Sekundärquelle/Zusammenfassung**. Zahl nicht im Original verifiziert |
| **[M]** | **Nur behauptet / Marketing**. Kein Beleg |
| **[H]** | **Nur Hinweis** (X, Reddit, Foren, GitHub-Einzelprojekte) |

Kosten-Referenz Bitget (Quelle: [Bitget Fee-FAQ](https://www.bitget.com/support/articles/12560603892734)):
- **USDT-M Perps VIP0:** Maker 0,02 %, Taker 0,06 %
- **Spot:** 0,10 % für Maker und Taker, bzw. 0,08 % mit BGB-Rabatt

Ein Round-Trip kostet also mindestens 0,04 % (Maker/Maker) bzw. 0,12 % (Taker/Taker), jeweils plus Slippage. Ein Cash-and-Carry-Round-Trip (Spot + Perp, alles Maker, mit BGB) kostet ≈ 0,20 %.

Wo eine Quelle **keine Nettozahl** oder **keine OOS-Zahl** liefert, steht das ausdrücklich da.

---

## 2. Warum die Literatur „besser" aussieht als deine Backtests

Sieben Gründe, jeweils mit Beleg:

1. **Zeitraum / Alpha-Decay.**
   - McLean & Pontiff (JF 2016) zeigen für Aktien-Anomalien −26 % Out-of-Sample und −58 % nach Publikation.
   - Für Krypto ganz konkret:
     - Grobys et al. 2025 [B-PR]: Momentum bei den Top-30-Coins von 2016–07/2020 1,74 %/Woche (nur 10 %-signifikant), **danach negativ und insignifikant**.
     - Fieberg/Liedtke/Zaremba 2024 [B-PR]: Alphas in der zweiten Stichprobenhälfte sind 9–76 % niedriger.
     - Funding: Median-Funding nach Vine 2026 [R] lag 2024 bei +13,4 %, 2025 bei +2,8 % und 2026 bei +0,6 %.
2. **Universum.**
   - Viele Studien (Liu/Tsyvinski/Wu 2022, Dobrynskaya 2023, Cakici 2024) nutzen tausende Coins inkl. Microcaps. Dort sitzt das Alpha, aber es gibt keine Perps, keine Short-Möglichkeit und keine Liquidität.
   - Cakici et al. 2024: Alpha vor allem in kleinen, illiquiden Coins.
3. **Kosten.**
   - Häufig sind Ergebnisse brutto (Zarattini Tab. 1, Dobrynskaya, Starkiller-Overlay) oder rechnen mit Maker-Fills und VIP-Gebühren.
   - He et al. nennen ihren „High"-Tier „small individual trader", der setzt aber > 1 Mio. $ Spot- und > 15 Mio. $ Perp-Volumen in 30 Tagen voraus.
   - Maker-Fills selbst sind adversely selected (Albers et al. 2025).
4. **Perp-spezifische Kosten.**
   - Spot-Backtests ignorieren Funding. Meine Nachrechnung: Die Trend-Strategie auf BTC-Perps zahlte 2021–03/2025 **3,8 % p.a. Funding**, weil Long-Trends genau dann laufen, wenn Funding hoch ist (siehe Abschnitt 4).
5. **Kapazität.** Basis- und Funding-Spreads wurden durch Ethena (USDe), ETFs (−3 % Carry laut BIS) und Arbitrage-Kapital wegarbitriert.
6. **Data-Mining.**
   - Hudson & Urquhart 2019 testen fast 15.000 Regeln. In-Sample ist alles signifikant, OOS (H1 2018) verliert die beste BTC-Regel.
   - Vine 2026 misst für den Funding-Faktor PBO 0,81.
7. **Benchmark-Problem.** In einem Markt, der 2015–2024 mehrfach um 100–300 % pro Jahr stieg, sieht jede Long-Strategie gut aus. Gegen BTC-Buy&Hold verlieren die meisten Trend-Strategien in Bullenjahren, so auch deine 20 % CAGR < BTC.

**Fazit:** Deine Backtests sind nicht „falsch". Sie messen den heutigen, effizienteren und teureren Markt. Die Literatur misst überwiegend einen vergangenen.

---

## 3. Strategie für Strategie

### 3.1 Trendfolgen / Time-Series-Momentum (TSMOM)

| Quelle | Daten/Zeitraum | Ergebnis | Kosten | OOS | Level |
|---|---|---|---|---|---|
| [Zarattini, Pagani & Barbon 2025, „Catching Crypto Trends"](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5209907) | CMC-Spot, 01/2015–19.03.2025, survivorship-frei, long-only, Vol-Target 25 % | BTC-Combo (9 Donchian-Fenster): CAGR 30 %, Sharpe 1,58, MDD 19 %, Alpha 14 % · Top-20-Portfolio: CAGR 18 %, Vol 9 %, Sharpe 1,57, MDD 11 %, Beta 0,08 · Long/Short Top-20: CAGR 16 %, Sharpe 1,24 | BTC-Tabelle **ohne Kosten**. Portfolio mit 10 bp + 20 %-Rebalance-Schwelle. Bei 50 bp fällt das 5-Tage-Modell von 34 % auf 18 % CAGR | **Kein OOS-Test.** Die Autoren nennen schwache Phasen 2015–16 und 2022–23 | [B-WP] |
| **Eigene Nachprüfung** (Abschnitt 4) | Binance-Perps 2021–10/2026 | Overlap bis 03/2025: Sharpe 0,6–0,8. **OOS nach Publikation: Sharpe −0,18 bis +0,25** | Bitget-Gebühren + Funding | **Ja (19 Monate)** | [B-EIG] |
| [Liu & Tsyvinski, RFS 2021](https://academic.oup.com/rfs/article/34/6/2689/5912024) | BTC u. a., bis 2018 | TSMOM über 1–4 Wochen signifikant | Gross | Nein. Stichprobe endet 2018 | [B-PR] |
| [Hudson & Urquhart 2019, Annals of OR](https://link.springer.com/article/10.1007/s10479-019-03357-1) | ~15.000 technische Regeln, BTC/ETH/LTC/XRP | In-Sample signifikant | teils | **OOS H1 2018: beste BTC-Regel −0,1 % bzw. −0,9 % p.a.**, LTC/XRP/ETH positiv | [B-PR] |
| [Le & Ruthbah (SSRN 4551518)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4551518) | MA-Regeln BTC/ETH/Index bis 01/2023 | Risikoadjustiert besser als Buy&Hold | Bei 0,1–0,5 % noch besser, Überrendite schrumpft mit den Kosten | Nein | [B-WP] |
| [Huang, Sangiorgi & Urquhart (SSRN 4825389)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4825389) | Volumengewichtetes TSMOM | 0,94 %/Tag, Sharpe 2,17 (laut Suchzusammenfassung) | nicht geprüft | nicht geprüft | **[S]**, nicht verifiziert, unplausibel hoch |
| [Bysik & Ślepaczuk, arXiv 2606.00060](https://arxiv.org/abs/2606.00060) | BTC stündlich 2018–2025, 27 Walk-Forward-Folds, 10 bp | 24h-Momentum long-only **−45,9 % ARC** nach Kosten. Kostenbewusster ML-Filter: 65 % ARC, Sharpe 1,09, MDD −67 %, **nicht signifikant besser als Buy&Hold (56 %)**. 16/27 Folds profitabel | Ja | Ja (WF) | [B-WP] |
| [Man Group, „In Crypto We Trend" (2024)](https://www.man.com/insights/in-crypto-we-trend) | illustrativ | Beste Sharpe mit ~10–15 Coins | – | – | [R], **keine Performance-Zahlen** |
| [Bitwise Trendwise BITC (Live-ETF)](https://bitcetf.com/) | Live seit 20.03.2023, 10/20-EMA, CME-Futures vs. T-Bills | NAV bis 29.09.2026: 1 J. **−12,28 %**, 3 J. **+37,34 %**, seit Auflage +27,99 %. TER 0,85–0,88 %, AUM ~14 Mio. $ | Echt (live) | **Live** | [B-Live] |

Hinweis: Der Blog/Paper „Trend: When Published Edge Ages" (Karaptic, SSRN 7405060) ordnet Grobys 2025 als TSMOM ein. Das Paper behandelt aber **cross-sektionales** Momentum, das ist eine Fehleinordnung.

**Retail-Tauglichkeit bei Bitget:** Ja. Turnover ≈ 8× p.a. (eigene Messung), das ergibt bei 0,10 % pro Seite ≈ 0,8 % p.a. Kosten. Das größere Problem ist das **Funding** (Abschnitt 4).

Mindestgrößen: Bei 1000 USDT, 20 Coins und Vol-Target liegen die Einzelpositionen oft bei nur 5–20 USDT. Das ist knapp an Bitgets Mindest-Notional. Realistisch sind deshalb eher 5–10 Coins oder ein höheres Vol-Target.

**Risiken:**
- lange Seitwärtsphasen mit Verlusten (2022, 2025)
- Whipsaw
- Underperformance vs. BTC in Bullenjahren (2023: +30 % vs. +156 %)

**Backtestbar mit Binance Vision:** Ja, vollständig (klines 1d + fundingRate).

---

### 3.2 Cross-sektionales Momentum (Gewinner kaufen / Verlierer shorten)

| Quelle | Daten/Zeitraum | Ergebnis | Kosten | OOS/Replikation | Level |
|---|---|---|---|---|---|
| [Liu, Tsyvinski & Wu, JF 2022](https://onlinelibrary.wiley.com/doi/10.1111/jofi.13119) | Breites Universum inkl. Small-Caps, bis 2018 | 2,5–4,1 %/Woche | Gross | – | [B-PR] |
| [Dobrynskaya, J. Alternative Investments 2023](https://www.pm-research.com/content/iijaltinv/26/1/65) | 2.000 Coins, 2014–2020 | 2/2-Wochen-Momentum ~70 % p.a., Umkehr nach ~1 Monat (getrieben von Verlierern) | **Keine Kostenanalyse** | Autorin warnt vor Subsample-Instabilität | [B-PR] |
| [Grobys & Sapkota 2019, Econ. Letters](https://doi.org/10.1016/j.econlet.2019.03.028) | 143 Coins 2014–2018 | **Kein Momentum** | – | Widerlegung | [B-PR] |
| [Grobys, Kolari, Sandretto, Shahzad & Äijö 2025, FMPM](https://link.springer.com/article/10.1007/s11408-025-00474-9) | Top-30 Large Caps, EW Long/Short | 01/2016–07/2020: 1,74 %/Woche (nur 10 %-sign.). **Danach negativ/insignifikant.** Gesamt 0,90 %/Woche insign. Eine Coin verursachte −255 % in einer Woche (12/2020) | – | Regime-Split = Decay | [B-PR] |
| [Fieberg, Liedtke & Zaremba 2024, IRFA](https://www.sciencedirect.com/science/article/abs/pii/S1057521924001509) | 3.956 Coins 2014–2022 | Funktioniert bei Large Caps, braucht bis 85 % Wochen-Turnover. Alpha v. a. im Short-Leg und in Bullenmärkten | **Kosten senken Alpha um 26–53 %** | 2. Hälfte: Alpha 9–76 % niedriger | [B-PR] |
| [Fieberg et al., „CTREND", JFQA 2025](https://doi.org/10.1017/S0022109024000747) | 3.000+ Coins 04/2015–05/2022, wertgewichtet, wöchentlich (ML-Aggregat technischer Signale) | H-L 3,87 %/Woche brutto, **2,90 % netto** (30/40 bp). Top-100: 3,39 %/Woche, Break-even-Kosten 1,41 % | Ja | Endet 2022 | [B-PR] |
| [Arefev 2026 (SSRN 7404139)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7404139) · [Blog](https://karaptic.com/blog/cross-sectional-momentum-net-of-costs/) | **832 Binance USDⓈ-M Perps, 01/2020–07/2026, vorregistriert**, 338 Wochen | Brutto +0,573 %/Woche, **netto +0,173 %/Woche** (0,40 pp RT) | Ja, realistisch | **Keiner der 3 Signifikanztests bestanden.** 2-Wochen-Variante wechselt je nach Startwoche das Vorzeichen (+0,429/−0,076) | [B-WP] |
| [Starkiller Capital (Drogen/Hoffstein/Otte 2023)](https://www.starkiller.capital/post/cross-sectional-momentum-in-cryptocurrency-markets) | Long-only Top-Quintil, 30/7 Tage, 04/2018–11/2022 | Gesamt 37,8 % p.a. vs. BTC 28,7 %. **OOS ab 03/2021: −2,35 %** (BTC −37,82 %). MDD > 75 %. Mit BTC-Trend-Overlay 93,3 % p.a., DD 45 %, **aber ohne Kosten** | 125 bp → unter BTC | Ja | [R] |

**Bewertung:** Die einzige Studie, die genau deinen Use-Case abbildet (Binance-Perps, 2020–2026, vorregistriert, realistische Kosten), findet **kein signifikantes Edge**. Für Retail auf Bitget **nicht empfohlen**: hoher Turnover (Taker-Kosten) und extremes Short-Squeeze-Risiko einzelner Coins.

**Backtestbar:** Ja.

---

### 3.3 Funding-/Basis-Arbitrage (Cash-and-Carry: Spot long + Perp short)

| Quelle | Daten/Zeitraum | Ergebnis | Kosten | OOS | Level |
|---|---|---|---|---|---|
| [He, Manela, Ross & von Wachter, arXiv 2212.06888](https://arxiv.org/abs/2212.06888) | Binance 01/2020–11.03.2024 | BTC „High"-Tier: Sharpe 3,27, Rendite 12,55 %, Vol 3,84 %, MDD −2,63 %. ETH: Sharpe 4,45, 18,18 % | Maker. „High"-Tier = Spot 0,0675 % / Perp 0,0144 %, das braucht > 1 Mio. $ Spot- und 15 Mio. $ Perp-Volumen | Abweichungen schrumpfen um ~22 pp pro Jahr | [B-WP] |
| [Schmeling, Schrimpf & Todorov, „Crypto Carry", BIS WP 1087 / Mgmt. Science](https://www.bis.org/publ/work1087.pdf) | 04/2019–07/2024 | Carry im Mittel ~7 % p.a. (Spitzen > 40–60 %). CME-Cash-and-Carry 2019–01/2022: Sharpe ~0,59 **vor Kosten**, MDD 8 % | brutto | Hoher Carry sagt Crashes/Liquidationen voraus. Bei 10× Hebel wäre das Futures-Leg in > 50 % der Monate liquidiert worden. ETFs senkten den Carry um ~3 % | [B-PR] |
| [Vine 2026, „Alpha Research Paper 2"](https://bryanvine.github.io/alpha-research/paper2.html) | 30 Binance-Perps 2023–05/2026 | Cash-and-Carry-Sharpe 8,5 ist ein **Artefakt** (glatter Zahlungsstrom). **Netto +5,6 % p.a., 2026 negativ** | Ja | – | [R] |
| [SafeArbitrage: Funding-Leg BTC/ETH](https://safearbitrage.com/en/blog/usde-yield-funding-rate/) | Binance, 2021–09/2026, ohne Gebühren | 2021 34,10 % · 2022 2,48 % · 2023 8,04 % · 2024 12,50 % · 2025 5,03 % · 2026 YTD 1,77 % | **ohne Gebühren** | – | [R] (Anbieter mit Interessenkonflikt) |
| **Eigene Nachrechnung** | Binance Vision fundingRate BTC/ETH | Jahressumme Ø BTC/ETH: 2021 **34,07 %** · 2022 **2,48 %** · 2023 **8,06 %** · 2024 **12,48 %** · 2025 **5,03 %** · 2026 bis Sep **1,82 %**. Monatlich 2026: Feb −0,19 %, Mär −0,09 %, Apr −0,16 % | brutto | – | **[B-EIG], bestätigt SafeArbitrage exakt** |
| Ethena sUSDe (live, Milliarden-Skala) | 2024–2026 | ~11 % (2024), ~5 % (2025), ~3,7–4,8 % (2026) | live | live | [S] |

**Rechnung für dich:**
- Bitget-Round-Trip ≈ 0,20 % (Spot 0,08 % mit BGB ×2 + Perp-Maker 0,02 % ×2), mit Taker deutlich mehr.
- Bei 1,8 % Brutto-Funding (2026) und gelegentlichen negativen Monaten bleibt nach Kosten, Kapitalbindung (Spot + Margin) und Basis-Risiko praktisch nichts. Das deckt sich mit deinem 0 %-OOS-Ergebnis.

Ethena hat mit Milliarden genau diesen Trade industrialisiert. Ein Retail-Bot konkurriert damit um dieselbe Prämie.

**Risiken:**
- negatives Funding
- Basis-Ausweitung in Crashes
- ADL/Liquidation des Short-Legs
- Exchange-Risiko

**Backtestbar:** Ja (fundingRate, premiumIndexKlines, Spot-Klines).

---

### 3.4 Cross-sektionaler Funding-Carry-Faktor (long niedriges / short hohes Funding)

| Quelle | Ergebnis | OOS | Level |
|---|---|---|---|
| [Vine 2026](https://bryanvine.github.io/alpha-research/paper2.html), 30 Binance-Perps, 2023–05/2026, wöchentlich, 6 bp/Seite | In-Sample-Sharpe 0,71, **Walk-Forward-OOS-Sharpe 0,39**, alle 36 Konfigurationen positiv, **PBO 0,81**, MDD −35 %. Funding sagt Preisrenditen **nicht** voraus (IC −0,005). Die Rendite ist der Funding-Strom selbst | Ja (WF), aber PBO hoch | [R] |
| BIS „Crypto Carry" (s. o.) | Carry-Spread als Risikoprämie, Crash-Risiko bei hohem Carry | – | [B-PR] |

**Bewertung:** Die einzige mir bekannte Variante mit positivem Walk-Forward-OOS auf heutigen Daten. Der Effekt ist klein und hat einen hohen Overfitting-Verdacht. Dollar-neutral, wöchentlich, also wenig Turnover.

**Kritisch:**
- MDD −35 % bei Sharpe 0,39 ist für „moderat" grenzwertig.
- Short-Squeeze-Risiko auf Coins mit hohem Funding.
- Mit 1000 USDT und 2×5 Positionen werden Bitgets Mindestgrößen knapp.

**Backtestbar:** Ja.

---

### 3.5 Basis- und Calendar-Spreads (Delivery-Futures)

- BIS „Crypto Carry" [B-PR]: Die CME-Basis ist dieselbe Prämie wie der Perp-Funding-Carry, mit identischem Decay (ETFs −3 %).
- Bitget hat seit 03.09.2026 Coin-M-BTC/ETH-Delivery-Futures. Die Historie ist zu kurz und die Liquidität unklar.
- Spezifische Studien zu Calendar-Spreads mit Nettozahlen für Retail habe ich **nicht gefunden**. Auch keine Zahl.

**Backtestbar:** Binance Vision hat Coin-M-Delivery-Klines (`futures/cm`), also eingeschränkt ja.

**Bewertung:** Derselbe ausgedünnte Carry. Kein eigenständiges Edge.

---

### 3.6 Cross-Exchange-Funding-Spreads

| Quelle | Ergebnis | Level |
|---|---|---|
| DavidAyusoPita (GitHub-Forschungsrepo), BTC/ETH/SOL auf Binance/Bybit/OKX/Hyperliquid, 07/2024–07/2026 | CEX-DEX-Spread strukturell 8,5–11,4 % ann., aber Halbwertszeit nur 1,5–3,5 h. **Aktive Schwellenregel: −9 bis −15 % p.a.** Passive 30-Tage-Regel: +2,7–5,4 % netto, DD < 2 %, Spread schrumpft | [H]/[R] |
| Kaleb0719 (GitHub), Binance–Bybit Retail | Brutto 0,0043 % vs. Kosten 0,294 % pro Event, 0 % Trefferquote, auch ohne Gebühren negativ | [H] |
| MDPI „Two-Tiered Structure" (2026) | Nur ~40 % der Top-Gelegenheiten nach Kosten profitabel | [B-PR] (Zahl aus Abstract) |
| Springer Digital Finance (2026) | CEX-DEX-Funding-Arb als Basis-Trade modelliert | [B-PR] (keine Retail-Nettozahl entnommen) |

**Bewertung:** Aktiv nicht profitabel. Passiv bestenfalls wenige Prozent, mit Counterparty-Risiko auf zwei Börsen und doppeltem Margin-Bedarf. **Mit Binance Vision nur teilweise backtestbar** (Daten von Bybit/OKX/Hyperliquid nötig).

---

### 3.7 Cross-Exchange-Preisarbitrage

- [Makarov & Schoar, JFE 2020](https://doi.org/10.1016/j.jfineco.2019.07.001) [B-PR]: große, persistente Preisunterschiede **bis 2018**, vor allem über Ländergrenzen und durch Kapitalverkehrskontrollen begrenzt.
- Kimchi-Premium 2025–26 ≈ 1–10 % [S], aber für Nicht-Koreaner nicht handelbar.
- Zwischen großen westlichen Börsen liegen die Spreads heute im Bereich weniger Basispunkte. HFT-Firmen mit Co-Location dominieren.

**Für Retail: nein.** Backtest mit Binance Vision allein ist nicht möglich.

---

### 3.8 Market Making (inkl. Inventory-Management)

| Quelle | Ergebnis | Level |
|---|---|---|
| Daru/Gatto (SSRN 7461901) | Quoting „last in queue" am Touch auf Bybit/Binance/Hyperliquid: **Adverse Selection > halber Spread schon vor Gebühren** (−0,84 / −0,39 / −0,46 bp) | [B-WP] |
| [Albers et al., arXiv 2502.18625](https://arxiv.org/abs/2502.18625) (live Binance-BTC-Perp) | Maker-Fill-Wahrscheinlichkeit ist negativ mit der Rendite nach dem Fill korreliert. Gängige Strategien sind „highly unprofitable" | [B-WP] |
| Stoikov et al. (SSRN 5066176) | Hummingbot-Live-Test nur 24 h, keine belastbare Aussage | [B-WP] |
| GitHub-Avellaneda-Stoikov-Backtest | Brutto +0,045 vs. Gebühren 0,169 USDT, also netto negativ | [H] |
| Hummingbot-Community/Reddit | Überwiegend Break-even/Verlust, außer bei Liquidity-Mining-Rewards | [H] |
| Hyperliquid HLP (Protokoll-Vault) | ~10–13 % APR 2025, 24/26 Monate positiv. **Nicht replizierbar:** privilegierter Liquidations-Flow | [S] |
| Hyperliquid User-Vaults (doesitpay-Analyse) | 9.469 Vaults, **22,8 % über ihre Lebenszeit profitabel**, ~70 Mio. $ Nettoverlust | [R] |

**Bewertung:** Bei 0,02 % Maker-Gebühr (VIP0) und ohne Rebates ist Market Making für Retail **strukturell unprofitabel**: Profis zahlen negative Maker-Gebühren und haben Latenzvorteile. Inventory-Modelle (Avellaneda-Stoikov, GLFT) lösen das Adverse-Selection-Problem nicht.

**Backtest:** Binance Vision `bookTicker`/`bookDepth` sind möglich, aber Queue-Position und Fill-Simulation sind ohne L3-Daten unzuverlässig, und Backtests überschätzen systematisch.

---

### 3.9 Mean Reversion / Pairs / Stat-Arb

| Quelle | Daten | Ergebnis | Level |
|---|---|---|---|
| [Fil & Kristoufek, IEEE Access 2020](https://doi.org/10.1109/ACCESS.2020.3024619) | 26 Binance-Coins, 01/2018–09/2019 | Distanz-Methode täglich −0,07 %/Monat, stündlich 3,1 %, 5-Min 11,61 % (Sharpe 22!). Kointegration täglich 1,36 %/Monat, Sharpe 1,1. Kosten max. 30 bp one-way. **Sehr kosten- und latenzsensitiv, schlechter als Benchmarks** | [B-PR] |
| Pindza & Mba 2026, Quant. Finance & Economics | Adaptive Copula, 10 Binance-Perps, stündlich 2021–2023, 0,08 % RT | **Marktneutral netto negativ** | [B-PR] |
| Dobrynskaya 2023 | Umkehr nach ~1 Monat | Kurzfristige Reversal-Komponente, keine Kosten | [B-PR] |

**Bewertung:** Die hohen Zahlen gibt es nur auf Hochfrequenz, wo Retail-Latenz und Taker-Gebühren alles auffressen. Auf Tagesbasis ist kein Edge vorhanden. **Nicht empfohlen.**

**Backtestbar:** Ja (klines bis 1m).

---

### 3.10 Liquidation-Cascade- und Open-Interest-Signale

| Quelle | Ergebnis | Level |
|---|---|---|
| EdgeDepth (vorregistriert, 7.975 Kaskaden, Binance 09/2024–09/2026) | Halbwegs-Rebound zuerst: 48,1 % vs. 51,0 % bei vergleichbaren Drops. **„Kaskadenende kaufen" verlor nach Kosten (typ. Trade −1,65 %).** Das Deep-Cascade-„Edge" stammte von einem einzigen Tag (10.–11.10.2025) | [R] |
| Tickfloor | 6 Funding-/OI-Regeln 2017–2025, alle scheitern (Benchmark: EW-Long ohne Kosten) | [R] |
| Karaptic (24 Tests) | Derivate-Features bringen keine Prognoseverbesserung über Preis/Vol hinaus | [R] |
| Gate Research | Bedingte Rebound-Evidenz, nicht robust | [M]/[R] |

**Achtung Look-ahead:** Die Binance-Vision-`metrics` (OI, Long/Short-Ratios) sind ~5 Minuten früher gestempelt als real verfügbar.

**Bewertung:** **Nicht empfohlen.**

---

### 3.11 Token-Unlocks und Listings

| Quelle | Ergebnis | Level |
|---|---|---|
| Keyrock (16.000 Unlock-Events) | ~90 % zeigen negativen Preisdruck | [R] |
| Tokenomist (236 Events 2024–26) | −4,85 % Ein-Monats-Excess vs. gematchte Peers. Nur Early-Stage-Token betroffen. Drift von −14,7 % schon *vor* dem Event | [R] |
| Kim (SSRN 6632838) | 52 Events, 88,5 % negativ binnen 72 h | [B-WP], kleine Stichprobe |
| Animoca Research | 1 % Unlock ≈ −0,3 % Woche davor und −0,3 % Woche danach | [R] |
| [Ante 2019 (SSRN 3450301)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3450301) | 327 Listings, +5,7 % abnormale Rendite am Listing-Tag. Binance: +14,7 % am Tag, dann −6,3 % (Tage +1 bis +3) | [B-WP] |
| Cross-Listing-Studie 2021 | Binance-Listing +16,3 % | [B-PR] (Sekundärzitat) |

**Bewertung:**
- **Unlocks:** konsistente, mehrfach unabhängig gefundene Richtung. Aber der Großteil passiert vor dem Event (Front-Running), Funding auf Shorts kann teuer sein, und es braucht Unlock-Kalenderdaten (Tokenomist/CryptoRank, nicht in Binance Vision).
- **Listings:** Edge liegt in der Geschwindigkeit (News-Latenz), für Retail nicht realistisch.
- Mit Binance Vision nur zusammen mit externem Unlock-Kalender backtestbar.

---

### 3.12 Wochentags-, Wochenend- und Session-Saisonalität

- [Mueller 2024, Finance Research Letters](https://www.sciencedirect.com/science/article/pii/S1544612324004598) [B-PR]: **keine robuste Renditesaisonalität.** Der Montagseffekt verschwindet nach 2015.
- Quantpedia 2022 [R]: „BTC 21–23 Uhr UTC kaufen" bringt 33 % p.a., Vol 20,9 %, MDD −22,45 %, aber **ohne Kosten, in-sample**.
- Shanaev et al. 2023, Heliyon [B-PR]: „Turn-of-the-candle" mit 0,58 bp/Minute. Mit Gebühren nicht handelbar.
- Wochenendeffekte gibt es nur bei Volatilität und Volumen, nicht bei der Rendite.

**Nicht empfohlen** als eigenständige Strategie. Allenfalls als Ausführungs-Timing nützlich.

---

### 3.13 On-Chain-Signale

- Grobys, Näsman & Sandretto 2026, RIBAF [B-PR]: MVRV-Z-Score-Timing bringt Sharpe 1,28 vs. 0,45 Buy&Hold über 3 Zyklen. **Sehr wenige Trades**, das ist reines Zyklus-Timing mit kaum statistischer Aussagekraft.
- [Chi et al., arXiv 2411.06327](https://arxiv.org/abs/2411.06327) [B-WP]: USDT-Exchange-Inflows sagen BTC/ETH auf 1–6 h voraus, BTC-Inflows meist nicht. Keine Nettozahl.
- JRFM 2024 [B-PR]: Keine On-Chain-Metrik sagt die monatliche BTC-Rendite out-of-sample voraus.

**Bewertung:** Höchstens als langsamer Regime-Filter denkbar. **Nicht mit Binance Vision backtestbar** (On-Chain-Daten von Glassnode/CryptoQuant nötig, meist kostenpflichtig).

---

### 3.14 Grid-Bots und DCA

- Arefev (SSRN 7376359) [B-WP]: Ein klassischer Grid hat **vor Kosten einen Erwartungswert von null**. Die „Outperformance" dynamischer Grids kommt aus direktionalem Exposure, und Gebühren können das Vorzeichen drehen.
- [Chen et al., arXiv 2506.11921](https://arxiv.org/abs/2506.11921) [B-WP]: Dynamic Grid BTC/ETH 2021–07/2024. Das Ergebnis hängt am Bullenmarkt.
- DCA: senkt das Timing-Risiko, Lump-Sum schlägt DCA aber meist. DCA ist eine Investitionsform, keine Alpha-Strategie.
- Bitgets Grid-Bot-Marketing („Top-Bots +X %") [M]: Survivorship, kein Beleg.

**Nicht empfohlen** als Edge-Quelle.

---

### 3.15 Volatilitätsstrategien (Optionen)

| Quelle | Ergebnis | Level |
|---|---|---|
| Deribit Insights, „Selling Weekend Vol" | 01/2020–08/2024, 0,35-Delta-Strangle, inkl. Gebühren + 5 % Slippage: +124,85 %, APR 27,4 %, MDD 23,8 %, 169/212 Trades gewonnen | [R] (Börsen-Blog, Interessenkonflikt) |
| Hysteresis Research | DVOL − RV30: +9,7 (2022), +7,9, +6,6, +5,1, **2026 YTD −2,1**. Mit Filterregel Sharpe 1,80 | [R], **Prämie schrumpft, 2026 negativ** |
| Quantitative Finance 2024 (Deribit, delta-gehedgt) | Varianzrisikoprämie signifikant negativ, also Vol-Verkauf langfristig profitabel | [B-PR] |

**Umsetzbarkeit:**
- Bitget bietet vor allem USDC-margined europäische Optionen mit geringer Liquidität. Die 2026 neu gestarteten Optionen waren US-Aktienoptionen, keine Krypto-Optionen.
- Deribit (jetzt Teil von Coinbase) ist die liquide Venue. Der **Zugang für österreichische Privatkunden unter MiCA/ESMA muss geprüft werden.**
- Mindestgrößen: BTC-Optionen 0,1 BTC. Mit 1000 USDT kaum sinnvoll, da ein Short-Strangle Margin von mehreren tausend USD braucht.

**Risiken:** Tail-Events (März 2020, Okt 2025), negative Prämie in Phasen wie 2026.

**Backtest:** **nicht mit Binance Vision.** Binance-Optionen-Daten sind dort nur sehr eingeschränkt verfügbar (EOHSummary), Deribit-Historie kostenpflichtig (Tardis) bzw. teilweise frei über die API.

---

### 3.16 Machine Learning

| Quelle | Ergebnis | Level |
|---|---|---|
| [Cakici et al., IRFA 2024](https://www.sciencedirect.com/science/article/abs/pii/S1057521924001765) | 2017–2023, kombiniert Long/Short 2,37 %/Woche, Sharpe 1,66. **Kosten fressen über die Hälfte.** Alpha in kleinen, illiquiden Coins, DD 70–80 % | [B-PR] |
| CTREND (JFQA 2025) | s. 3.2: robusteste ML-Variante, aber endet 2022 und wirkt vor allem bei kleineren Coins | [B-PR] |
| Bysik & Ślepaczuk 2026 | Naive ML-Strategien kollabieren nach Kosten. Bester Filter nicht signifikant besser als Buy&Hold | [B-WP] |
| Reviews (MDPI Forecasting 2025, Springer 2025) | Transaktionskosten werden selten realistisch modelliert, Look-ahead ist häufig | [B-PR] |

**Bewertung:** ML erhöht vor allem die Overfitting-Gefahr. Sinnvoll höchstens als **Kosten-/Regime-Filter** auf einer ohnehin robusten Basisstrategie, nicht als Alpha-Quelle. Backtestbar ja, aber nur mit strengem Walk-Forward, PBO/Deflated Sharpe und Purging/Embargo.

---

## 4. Eigene Out-of-Sample-Nachprüfung: Donchian-Trend-Ensemble (Zarattini et al. 2025)

**Warum diese Strategie:** Die Regeln im Paper sind vollständig spezifiziert und haben **keine fit-baren Parameter**:
- 9 Donchian-Fenster: 5/10/20/30/60/90/150/250/360 Tage
- Einstieg, wenn der Schlusskurs das obere Band erreicht
- Ausstieg bei Schluss unter einem Trailing-Stop. Der Stop ist das Mittelband und wird nie nach unten angepasst
- Gewicht = min(25 % / σ90, 200 %)
- Ensemble als Mittelwert der 9 Fenster
- 20 %-Rebalance-Schwelle nur für Vol-Anpassungen

Die Datenstichprobe endet am 19.03.2025. **Alles danach ist echter Out-of-Sample.**

**Setup** (Code: `/workspace/research/oos/bt.py`, Ergebnisse: `oos/results.txt`):
- Binance USDT-M Perp Tages-Klines und Funding (Binance Vision)
- Long-Positionen zahlen das tatsächliche Funding
- Kosten: (a) Bitget-Maker 0,02 %/Seite, (b) Bitget-Taker 0,06 % + 0,04 % Slippage = 0,10 %/Seite
- Portfolio: monatlich die Top-10 bzw. Top-20 nach Median-Quote-Volumen des Vormonats, je 1/B Kapital (wie im Paper)
- Einschränkung: Das Kandidatenuniversum sind ~50 heute gelistete große Perps (leichte Survivorship-Verzerrung, im OOS-Zeitraum gering)

| Zeitraum | Strategie | CAGR | Vol | Sharpe | Max DD |
|---|---|---|---|---|---|
| **Overlap 2021-01-01–2025-03-19** | BTC Buy&Hold | 29,7 % | 61,8 % | 0,73 | −76,7 % |
| | BTC-Combo (Taker+Slip) | 8,4 % | 15,1 % | 0,61 | −22,6 % |
| | Top-20-Combo (Taker+Slip) | 5,2 % | 7,0 % | 0,76 | −11,8 % |
| | Top-20 EW Buy&Hold | 5,7 % | 83,0 % | 0,49 | −85,4 % |
| **OOS 2025-03-20–2026-10-17** | BTC Buy&Hold | −3,9 % | 41,7 % | 0,11 | −53,0 % |
| | BTC-Combo (Maker / Taker) | −1,6 % / −2,4 % | 10,6 % | −0,10 / −0,18 | −15,6 % / −16,3 % |
| | Top-10-Combo (Maker / Taker) | −0,9 % / −1,3 % | 6,4 % | −0,11 / −0,18 | −9,1 % / −9,6 % |
| | Top-20-Combo (Maker / Taker) | +1,4 % / +1,0 % | 6,2 % | 0,25 / 0,18 | −8,0 % / −8,4 % |
| | Top-20 EW Buy&Hold | −16,2 % | 69,6 % | 0,09 | −68,6 % |
| **2022 (Bärenmarkt)** | BTC Buy&Hold | −64,2 % | | | −66,9 % |
| | Top-20-Combo (Taker) | −5,1 % | | | −5,4 % |

Zusätzlich die BTC-Combo auf **Binance-Spot** (ohne Funding, 10 bp), um die Jahre vor 2021 abzudecken:

| Jahr | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 YTD |
|---|---|---|---|---|---|---|---|---|---|
| Combo | −5,3 % | +33,8 % | +60,3 % | +11,9 % | −10,1 % | +29,8 % | +33,7 % | −6,9 % | +1,2 % |
| BTC | −73,0 % | +94,3 % | +302,0 % | +59,8 % | −64,2 % | +155,6 % | +121,3 % | −6,3 % | −4,6 % |

Sharpe nach Teilperiode: 2018–2020 **1,75**, 2021–03/2025 **0,87**, OOS ab 20.03.2025 **0,01**.

**Interpretation:**
1. Die Paper-Sharpe von ~1,6 wird zu einem großen Teil von **2015–2020** getragen. Ab 2021 halbiert sie sich ungefähr, nach Publikation liegt sie bei ≈ 0. Das ist Alpha-Decay bzw. Regimeabhängigkeit, genau wie bei deinem TSMOM-Walk-Forward.
2. **Funding-Drag:** Die BTC-Combo auf Perps zahlte 2021–03/2025 **3,8 % p.a.** Funding (OOS: 1,2 % p.a.). Das erklärt den Großteil der Lücke Spot (Sharpe 0,87) vs. Perp (0,61). **Long-only-Trend gehört eher auf Spot als auf Perps.** Alternativ könnte man Funding als Filter nutzen, das wäre aber ein neuer, zu testender Parameter.
3. Gebühren sind bei diesem Turnover (~8× p.a.) **nicht** das Hauptproblem: Maker vs. Taker macht nur ~0,5–1 pp p.a. aus.
4. Der robuste Nutzen ist der **Drawdown-Schutz**: 2022 −5 % statt −64 bis −76 %, OOS −8 % statt −69 %. Bei Sharpe ≈ 0,6–0,8 (langfristig) entspricht das einem Risiko-Overlay, nicht einer Geldmaschine.

Einschränkungen dieser Nachprüfung:
- Universum ex post gewählt
- Perps erst ab 09/2019, deshalb sind lange Fenster 2020 noch inaktiv
- Exit-Regeln für illiquide Coins aus dem Paper nicht implementiert
- Tagesschluss-Ausführung ohne Intraday-Slippage-Modell
- Keine Monte-Carlo-/Bootstrap-Konfidenzintervalle

**19 Monate OOS sind statistisch kurz.** Ein Sharpe von 0 widerlegt eine langfristige Sharpe von 0,7 nicht sicher, bestätigt sie aber auch nicht.

---

## 5. Live-Track-Records (echte, öffentliche Ergebnisse)

| Track Record | Zeitraum | Ergebnis | Level |
|---|---|---|---|
| **Bitwise BITC (Trend-ETF)** | 03/2023–09/2026 | +37,34 % (3 J.), −12,28 % (1 J.), seit Auflage +27,99 %. Zum Vergleich (eigene Rechnung, Binance-Perp-Schlusskurse): BTC 20.03.2023→29.09.2026 ca. +202 % (27.704→83.625 USD), letzte 12 Monate ca. −27 % (114.257→83.625). BITC verlor also weniger im Abschwung, blieb über 3 Jahre aber weit hinter BTC | [B-Live] |
| **Ethena sUSDe** (industrielles Cash-and-Carry) | 2024–2026 | ~11 % → ~5 % → ~4 % p.a. | [S] |
| **Hyperliquid HLP** | 2023–2025 | ~10–13 % APR, aber privilegierter Flow | [S] |
| **Hyperliquid User-Vaults** | Lebenszeit | 22,8 % von 9.469 profitabel, ~70 Mio. $ Nettoverlust | [R] |
| **VisionTrack Krypto-Fonds-Indizes** | 2024 / 2025 | 2024: Quant Directional +53,7 %, Market Neutral ~+18,5 %. 2025: Composite −12,6 %, Quant −7,51 %, **Market Neutral +13,1 %** | [S]. Market Neutral funktioniert bei Profis mit VIP-Gebühren/Rebates, Leverage-Zugang und Kapazität |
| **Copy-Trading (YieldFund-Analyse)** | 100.236 Follower-Ergebnisse, 90 Tage | **48,48 % profitabel**. 97 % der Leader im Plus, aber nur 43,6 % brachten Followern Gewinn | [R] |
| Dorfleitner et al. 2018 | Social Trading | Kopieren der Top-Rangliste verlor deutlich | [B-PR] |
| Bitget „93 % der Copy-Trader profitabel" | H1 2023 | **Unverifiziertes Marketing** | [M] |
| Freqtrade/Hummingbot-Berichte | – | Die Freqtrade-Doku selbst warnt vor Lookahead/Recursive-Bias und Dry-Run-vs.-Live-Lücken. Community-Berichte über dauerhaft profitable Live-Bots sind anekdotisch und nicht verifiziert | [H] |

Verifizierte Copy-Trading-Historien über 2+ Jahre mit unabhängiger Prüfung habe ich **nicht gefunden**. ESMA verlangt für solche Werbung 5 Jahre Historie; Börsen-Ranglisten sind survivorship-verzerrt.

---

## 6. Ranking der vielversprechendsten Ansätze (für dich konkret)

| # | Ansatz | Erwartung (realistisch) | Evidenz | Warum |
|---|---|---|---|---|
| **1** | **Diversifiziertes Long/Flat-Trendfolgen** (Donchian-Ensemble, Vol-Target, Top-10–20, täglich) – **bevorzugt auf Spot** oder auf Perps mit Funding-Filter | Langfristig Sharpe ~0,5–0,9, MDD 10–25 %, in Seitwärtsjahren ~0 % | Mehrere Papers [B-PR/B-WP], Live-ETF, eigene Nachprüfung | Robustestes Muster, wenig Turnover, vertretbare Kosten. **Ziel: Drawdown-Reduktion statt BTC schlagen** |
| **2** | **Cross-sektionaler Funding-Carry**, dollar-neutral, wöchentlich | OOS-Sharpe ~0,4, MDD bis −35 % | 1 Walk-Forward-Studie [R] + BIS-Theorie | Einziger Carry-Ansatz mit positivem OOS auf aktuellen Daten. Overfitting-Risiko (PBO 0,81) |
| **3** | **BTC/ETH-Trendfilter als Exposure-Steuerung** einer passiven Position (BITC-artig) | Senkt DD stark, kostet Bull-Rendite | Live-ETF, Le & Ruthbah, eigene Daten | Einfach, wenige Trades, gut kontrollierbar. Faktisch eine Vereinfachung von #1 |
| **4** | *(bedingt)* **Vol-Verkauf mit Regime-Filter** (Deribit) | Positive VRP langfristig, 2026 negativ | [B-PR] + [R] | Nicht auf Bitget. Rechtlicher Zugang und Kapitalbedarf (≫ 1000 USDT) sind Hürden |
| **5** | *(Forschung)* **Token-Unlock-Short** auf Early-Stage-Token | −4,85 % Excess/Monat (Event-Studie) | Mehrere unabhängige [R] | Benötigt externe Daten. Squeeze- und Funding-Kosten unklar, kaum Live-Belege |

**Ehrliche Erwartung:** Selbst der beste Ansatz wird mit 100–1000 USDT keine nennenswerten absoluten Gewinne erzeugen; bei Sharpe 0,7 und 10 % Vol sind das ~7 % p.a., also 7–70 USDT/Jahr. Er kann aber **verhindern, dass ein Krypto-Bärenmarkt das Kapital halbiert**.

---

## 7. Konkreter Backtest-Plan (nächste Schritte)

Allgemein für alle Tests:
- Binance-Vision-Daten (klines 1d/1h, fundingRate, premiumIndexKlines)
- **Bitget-Kosten**: Perp 0,02/0,06 %, Spot 0,08–0,10 %, plus 0,03–0,05 % Slippage
- Funding exakt
- Walk-Forward mit fixen Regeln bzw. höchstens einem frei gewählten Parameter
- **PBO (CSCV)**, **Deflated Sharpe**, Block-Bootstrap-Konfidenzintervalle
- Benchmark: BTC Buy&Hold und 50/50 BTC/Cash
- Mindestorder- und Lot-Größen von Bitget simulieren (100 / 500 / 1000 USDT)

**A) Trend-Ensemble (Priorität 1).** Code-Basis: `/workspace/research/oos/bt.py`.
1. Spot- vs. Perp-Variante vergleichen (Funding-Drag quantifizieren).
2. Funding-Filter testen: keine neuen Longs, wenn das 7-Tage-Funding über X liegt. X *a priori* festlegen, nicht optimieren.
3. Universum survivorship-frei aufbauen: alle jemals gelisteten Perps aus Binance Vision, inkl. delisteter wie LUNA/FTT.
4. Top-5/10/20, Vol-Target 25 % vs. 40 %.
5. Exit-Regeln für Illiquidität aus dem Paper ergänzen.
6. Erfolgskriterium: Sharpe > 0,5 und MDD < 25 % über 2021–2026 **und** in jedem Walk-Forward-Block kein Verlust > 15 %.

**B) Cross-sektionaler Funding-Carry (Priorität 2).**
- Replikation von Vine 2026: wöchentlich, Top-30 Perps, Quintile, 6 bp + Bitget-Kosten.
- Zusätzlich Funding-Kosten/-Erträge beider Legs, Bitget-Mindestgrößen bei 1000 USDT (max. 3+3 Positionen?).
- PBO und Deflated Sharpe berechnen.
- Kill-Kriterium: OOS-Sharpe < 0,3 oder PBO > 0,5.

**C) Kombination A + Cash/Carry** (Priorität 3). Trend-Sleeve und, wenn B besteht, Carry-Sleeve. Korrelation prüfen, ob die Kombination die Seitwärtsphasen (2022, 2025) glättet.

**D) Optional:** Token-Unlock-Event-Studie mit Tokenomist/CryptoRank-Kalender und Binance-Perp-Preisen und Funding (Short −14 Tage bis +7 Tage). Nur, wenn ein kostenloser bzw. bezahlbarer Unlock-Datensatz verfügbar ist.

**Explizit nicht weiter verfolgen:**
- Funding-Level-Arbitrage (Cash-and-Carry): Daten 2025/26 zeigen ~2–5 % brutto
- Market Making, Grid
- Cross-Exchange-Arb
- Liquidation/OI
- Intraday-ML
- Pairs
- Saisonalität

**Prozess:** Alles nur als Backtest bzw. Paper-Trading. Kein Merge oder Deploy ohne deine ausdrückliche Freigabe, keine Secrets im Code, kein Push auf main.

---

## 8. Quellenverzeichnis

### Peer-reviewed / Journals
1. [Liu, Tsyvinski (2021): Risks and Returns of Cryptocurrency, Review of Financial Studies](https://academic.oup.com/rfs/article/34/6/2689/5912024)
2. [Liu, Tsyvinski, Wu (2022): Common Risk Factors in Cryptocurrency, Journal of Finance](https://onlinelibrary.wiley.com/doi/10.1111/jofi.13119)
3. [Fieberg, Liedtke, Metko, Zaremba (2025): Cryptocurrency Trend (CTREND), JFQA](https://doi.org/10.1017/S0022109024000747)
4. [Fieberg, Liedtke, Zaremba (2024): Cryptocurrency anomalies and economic constraints, IRFA](https://www.sciencedirect.com/science/article/abs/pii/S1057521924001509)
5. [Grobys, Kolari, Sandretto, Shahzad, Äijö (2025): Momentum in large-cap cryptocurrencies, Financial Markets and Portfolio Management](https://link.springer.com/article/10.1007/s11408-025-00474-9)
6. [Grobys, Sapkota (2019): Cryptocurrencies and momentum, Economics Letters](https://doi.org/10.1016/j.econlet.2019.03.028)
7. [Dobrynskaya (2023): Cryptocurrency Momentum and Reversal, Journal of Alternative Investments](https://www.pm-research.com/content/iijaltinv/26/1/65)
8. [Hudson, Urquhart (2019): Technical trading and cryptocurrencies, Annals of Operations Research](https://link.springer.com/article/10.1007/s10479-019-03357-1)
9. [Makarov, Schoar (2020): Trading and arbitrage in cryptocurrency markets, Journal of Financial Economics](https://doi.org/10.1016/j.jfineco.2019.07.001)
10. [Fil, Kristoufek (2020): Pairs Trading in Cryptocurrency Markets, IEEE Access](https://doi.org/10.1109/ACCESS.2020.3024619)
11. [Cakici, Shahzad, Będowska-Sójka, Zaremba (2024): Machine learning and the cross-section of cryptocurrency returns, IRFA](https://www.sciencedirect.com/science/article/abs/pii/S1057521924001765)
12. [Mueller (2024): Cryptocurrency seasonality, Finance Research Letters](https://www.sciencedirect.com/science/article/pii/S1544612324004598)
13. [Schmeling, Schrimpf, Todorov: Crypto Carry, BIS Working Paper 1087 / Management Science](https://www.bis.org/publ/work1087.pdf)
14. [McLean, Pontiff (2016): Does Academic Research Destroy Stock Return Predictability?, Journal of Finance](https://onlinelibrary.wiley.com/doi/10.1111/jofi.12365)
15. [Bailey, Borwein, López de Prado, Zhu: The Probability of Backtest Overfitting, Journal of Computational Finance](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253)
16. [Bailey, López de Prado (2014): The Deflated Sharpe Ratio, Journal of Portfolio Management](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551)
17. Shanaev et al. (2023): Turn-of-the-candle effect in Bitcoin, Heliyon. Zitiert nach Abstract
18. Grobys, Näsman, Sandretto (2026): MVRV-Timing, Research in International Business and Finance. Zitiert nach Abstract
19. Pindza, Mba (2026): Adaptive Copula Pairs Trading, Quantitative Finance and Economics
20. Dorfleitner et al. (2018): Social Trading, Journal of Banking & Finance. Sekundärzitat
21. Quantitative Finance (2024): Variance risk premium on Deribit. Zitiert nach Abstract

### Working Papers / Preprints
22. [Zarattini, Pagani, Barbon (2025): Catching Crypto Trends, SSRN 5209907](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5209907) · [PDF](https://concretumgroup.com/wp-content/uploads/2026/02/Catching-Crypto-Trends.pdf)
23. [He, Manela, Ross, von Wachter: Fundamentals of Perpetual Futures, arXiv 2212.06888](https://arxiv.org/abs/2212.06888)
24. [Arefev (2026): Cross-Sectional Momentum Net of Costs, SSRN 7404139](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7404139)
25. [Arefev: Grid-Trading-Erwartungswert, SSRN 7376359](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7376359)
26. [Bysik, Ślepaczuk (2026): ML-Strategien BTC stündlich, arXiv 2606.00060](https://arxiv.org/abs/2606.00060)
27. [Albers et al. (2025): Market Making im Krypto-Perp, arXiv 2502.18625](https://arxiv.org/abs/2502.18625)
28. [Chen et al.: Dynamic Grid Trading, arXiv 2506.11921](https://arxiv.org/abs/2506.11921)
29. [Chi et al.: On-Chain-Flows und Renditen, arXiv 2411.06327](https://arxiv.org/abs/2411.06327)
30. [Le, Ruthbah: Trend-Following for Crypto, SSRN 4551518](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4551518)
31. [Huang, Sangiorgi, Urquhart: Volume-weighted TSMOM, SSRN 4825389](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4825389)
32. [Ante (2019): Listing-Effekte, SSRN 3450301](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3450301)
33. [Daru/Gatto: Queue-Position und Adverse Selection, SSRN 7461901](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7461901)
34. [Stoikov et al.: Hummingbot-Live-Test, SSRN 5066176](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5066176)
35. [Kim: Token-Unlock-Event-Studie, SSRN 6632838](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6632838)
36. [Karaptic: Trend – When Published Edge Ages, SSRN 7405060](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7405060)

### Practitioner-Research / Live-Daten
37. [Man Group: In Crypto We Trend (2024)](https://www.man.com/insights/in-crypto-we-trend)
38. [Starkiller Capital: Cross-Sectional Momentum in Cryptocurrency Markets (2023)](https://www.starkiller.capital/post/cross-sectional-momentum-in-cryptocurrency-markets)
39. [Bryan Vine: Alpha Research Paper 2 – Funding Carry (2026)](https://bryanvine.github.io/alpha-research/paper2.html)
40. [Karaptic Blog: Cross-sectional momentum net of costs](https://karaptic.com/blog/cross-sectional-momentum-net-of-costs/)
41. [Bitwise Trendwise BITC – Fondsseite](https://bitcetf.com/)
42. [SafeArbitrage: USDe-Rendite und Funding-Rate-Historie](https://safearbitrage.com/en/blog/usde-yield-funding-rate/)
43. [Bitget Trading Fees FAQ](https://www.bitget.com/support/articles/12560603892734) · [Bitget Fee-Seite](https://www.bitget.com/fee)
44. [Binance Vision – historische Marktdaten](https://data.binance.vision/)
45. [Freqtrade-Dokumentation: Lookahead-Analyse](https://www.freqtrade.io/en/stable/lookahead-analysis/) · [Recursive-Analyse](https://www.freqtrade.io/en/stable/recursive-analysis/)
46. [Hummingbot-Dokumentation](https://hummingbot.org/)
47. [Quantpedia: Bitcoin intraday seasonality (2022)](https://quantpedia.com/)
48. [Deribit Insights: Selling Weekend Vol](https://insights.deribit.com/)
49. EdgeDepth: Liquidation-Cascade-Studie (vorregistriert, 2026). Blog-Studie [R]
50. Tickfloor: Funding-/OI-Regeln 2017–2025. Blog-Studie [R]
51. Hysteresis Research: DVOL-RV-Spread. Blog-Studie [R]
52. Keyrock: Token-Unlock-Studie (16.000 Events) [R]
53. Tokenomist: Unlock-Event-Studie 2024–26 [R]
54. Animoca Brands Research: Unlock-Effekte [R]
55. YieldFund: Copy-Trading-Analyse (100.236 Ergebnisse) [R] · doesitpay.org: Copy-Trading- und Hyperliquid-Vault-Analysen [R]
56. VisionTrack: Krypto-Hedgefonds-Indizes 2024/2025 [S]
57. MDPI (2026): Two-Tiered Structure of Cross-Exchange Funding Arbitrage [B-PR, Abstract]
58. Springer Digital Finance (2026): CEX-DEX Funding Arbitrage [B-PR, Abstract]
59. GitHub DavidAyusoPita: Cross-Venue-Funding-Studie [H] · GitHub Kaleb0719: Binance–Bybit-Funding-Arb [H]
60. Zenodo, Lau: Replikationspaket Hyperliquid-vs.-CEX-Funding [H]

*Hinweis: Quellen ohne Link wurden über Suchergebnisse oder Abstracts erschlossen. Ihre Zahlen sind entsprechend gekennzeichnet und sollten vor einer Investitionsentscheidung im Original geprüft werden. X/Reddit/Forenbeiträge wurden nur als Hinweisgeber genutzt und tauchen nicht als Beleg auf.*
