# G6 Home Underdog Research — 2024–2026 audit (October 20, 2026)

**Status:** EXPERIMENTAL research flag only; *not* a new official Value Pick tier, parlay leg, or instruction to bet.

## Fixed research screen

- Both participants are Group-of-Six FBS members for the **relevant season**. The reorganized Pac-12 is G6 in 2026; the Pac-12 is **not** G6 in 2024–2025. Notre Dame is P4.
- Independent, unblended V1.5 forecasts the **home team** to win outright (home probability >= 50%).
- The same sportsbook provides a plausible matched two-sided home/away moneyline; home team is the sportsbook underdog, at +150 or longer.
- Forecast probabilities are from before the game and odds are no-vig comparisons.
- **2026 excludes Weeks 1–2** by decision; includes retrospectively reconstructed Weeks 3–4 and forward-frozen Weeks 5–7. 2024–2025 historical study includes Week 2.

## Returns at the recorded prices

| Season | Games | Wins–losses | Flat $100 P/L | ROI | Source |
|:--|--:|:--|--:|--:|:--|
| 2024 | 9 | 4–5 | +$465 | +51.7% | Retrospective independent V1.5 and ESPN BET opening prices |
| 2025 | 8 | 6–2 | +$805 | +100.6% | Retrospective independent V1.5 and ESPN BET opening prices |
| 2026 W3–4 | 1 | 0–1 | −$100 | −100.0% | Retrospective V1.5 and archived DraftKings opening prices |
| 2026 W5–7 | 1 | 1–0 | +$170 | +170.0% | Frozen original V1.5 and pregame DraftKings prices |
| **All** | **19** | **11–8** | **+$1,340** | **+70.5%** | Mixed retrospective/prospective |

**Correction:** An earlier note incorrectly stated +75.8%. The right result is **+$1,340 ÷ $1,900 = +70.5%**.

## All eleven winning underdogs

| Year | Week | Away team at selected home team | Home odds | Final (away–home) |
|--:|--:|:--|--:|:--|
| 2024 | 4 | Memphis at Navy | +360 | 44–56 |
| 2024 | 7 | UTSA at Rice | +165 | 27–29 |
| 2024 | 10 | Coastal Carolina at Troy | +170 | 24–38 |
| 2024 | 13 | Western Michigan at Central Michigan | +270 | 14–16 |
| 2025 | 2 | Liberty at Jacksonville State | +190 | 24–34 |
| 2025 | 2 | Tulsa at New Mexico State | +150 | 14–21 |
| 2025 | 9 | South Florida at Memphis | +175 | 31–34 |
| 2025 | 10 | Marshall at Coastal Carolina | +165 | 27–44 |
| 2025 | 10 | Tulane at UTSA | +150 | 26–48 |
| 2025 | 11 | Louisiana Tech at Delaware | +175 | 24–25 |
| 2026 | 7 | East Carolina at UAB | +170 | 17–30 |

## Eight losses for a fair comparison

| Year | Week | Away team at selected home team | Home odds | Final (away–home) |
|--:|--:|:--|--:|:--|
| 2024 | 3 | Western Kentucky at Middle Tennessee | +250 | 49–21 |
| 2024 | 5 | New Mexico at New Mexico State | +220 | 50–40 |
| 2024 | 6 | Texas State at Troy | +450 | 38–17 |
| 2024 | 6 | Western Michigan at Ball State | +260 | 45–42 |
| 2024 | 8 | Colorado State at Air Force | +260 | 21–13 |
| 2025 | 8 | Southern Miss at Louisiana | +160 | 22–10 |
| 2025 | 11 | Southern Miss at Arkansas State | +175 | 27–21 |
| 2026 | 4 | Massachusetts at Sacramento State | +185 | 35–6 |

## Pregame-only distinguishing characteristics

Historic schedules provide ESPN pregame Elo, previously completed FBS-vs-FBS scores, and records. Prior FBS games used here satisfy kickoff **before** the target game, same season, completed regular-season FBS/FBS. No result from the target game or any future game was used in these metrics.

| Pregame metric, averages | Eleven winners | Eight losers |
|:--|--:|--:|
| V1.5 independent win chance | 60.9% | 59.9% |
| Same-book no-vig home market chance | 33.7% | 29.3% |
| V1.5 minus market gap | 27.1 pp | 30.6 pp |
| Selected home ML | +195 | +245 |
| Home prior FBS offensive points/game | 23.4 | 14.6 |
| Home prior FBS defensive points allowed/game | 27.2 | 37.8 |
| Home prior FBS win rate (for teams with >=1 game) | 37.2% | 8.8% |
| Home pregame ESPN Elo minus away Elo | −74 | +22 |

**Interpretation:** Difference in independent V1.5 confidence is negligible (+1 percentage point for winners); odds/market and the selected home teams' previous scoring and defense appear more useful to investigate. The winning subset had superior prior offense (+8.8 PPG), allowed roughly 10.6 fewer points/game, and had better prior FBS record. Notably, many winning home teams were *worse* by ESPN Elo than their opponents; an Elo advantage was **not** a reliable success criterion.

- Within home dogs +150 to +199: **9–3, +100.8% ROI**. Outside that band (+200 or longer): 2–5, +18.6% ROI. This finer band was selected *after seeing results*, so do not use it as a verified rule.
- Two winning selections were in Week 2 of 2025, one with zero prior eligible FBS games; excluding both games leaves **9–8, +58.8% ROI**. This matters when assessing the quality of earlier-week statistical comparisons.
- None of these 19 selections reached the separate G6 Confidence Conflict threshold of model probability >=70%. The research flag and risk flag remain independent so future overlaps are handled explicitly (the risk filter has priority for official recommendations).
- Some winners were close: Rice by 2, Central Michigan by 2, Memphis by 3, Delaware by 1, New Mexico State by 7. Six winners cleared their opponents by 10+ points. These are descriptions of outcomes, not pregame predictive features.

## Evidence limits and next questions

1. Only **19 matched home-game observations**. The 2024–25 history was reconstructed using later code; odds labelled opening are not independently timestamp-validated. Results are affected by selection and multiple-testing biases. The tiny 2026 prospective portion contains just one home game.
2. Prior FBS points/game are crude proxies and are not opponent adjusted. Two 2025 Week 2 selections have very thin/missing same-season histories. Do not claim that historical offense/defense differences are predictive until compared with a matched market-pricing baseline and time-forward holdout.
3. This audit does **not** establish rushing yards, run-defense superiority, turnover margin, pressure rates, or referee/weather causes. Those require verified pregame box/pbp features and must be tested separately, without hindsight.
4. Recommended next frozen analysis: match candidate vs noncandidate G6 home underdogs by price band, venue and prior-game count; compare before-game points for, points allowed, opponent-adjusted scores, rushing defense and turnovers, and time-forward ROI against price-only benchmarks. Hold the screen constant before reviewing Week 8+ results.
5. The production research flag uses current matched same-book odds before kickoff or original immutable pregame quotes for already started games; if those are unavailable it fails closed. It does **not** recompute labels on historical 2024–25 games without frozen pregame captures.

## Sources

- [2024–25 game-level independent V1.5 and historical ESPN BET odds](https://github.com/christianmellis1-debug/CFB_Prediction_app/blob/research/test-c-historical-blend-2024-2025-2026-10-13/research/test_c_blend_2024_2025_games.csv)
- [2026 Weeks 3–4 reconstructed independent V1.5 and DraftKings opening odds](https://github.com/christianmellis1-debug/CFB_Prediction_app/blob/research/test-c-head-to-head-weeks3-6-2026-10-13/research/test_c_head_to_head_weeks3_6_games.csv)
- [2026 Weeks 5–7 original frozen V1.5 snapshots](https://github.com/christianmellis1-debug/CFB_Prediction_app/blob/main/data/shadow_tracking.json)
- [2024 schedule](https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_2024.csv), [2025 schedule](https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_2025.csv), [2026 schedule](https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_2026.csv)

No change to production winner model, waterfall, or parlay behavior is authorized by these results.
