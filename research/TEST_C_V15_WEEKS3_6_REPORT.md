# Test C vs V1.5 — 2026 Weeks 3–6 head-to-head

**Research completed October 13, 2026; no production app/model/tier changes.**

## Definition and fairness

The previously selected Test C **warning** is:
`V1.5 chosen winner confidence >=70% AND same-side no-vig DraftKings moneyline probability <55%`.

A warning alone is not an alternative winner-picking model; with a warning-only display, **winner records remain identical to V1.5**. For an actual head-to-head, evaluated:
1. **C market switch:** when warned **and** sportsbook favorite is opposite V1.5, switch to that favorite; otherwise keep V1.5.
2. **C skip/abstain:** omit warned games, and report accuracy **and coverage** on the retained games; skipping does not turn losses into wins.
3. **Automatic fade:** reverse *every* warned winner, even when the sportsbook favorite agrees with V1.5 (diagnostic, not a recommendation).
4. **Previously tracked market blend:** recompute winner from the no-vig home-win probability = `0.16927926947215113 × V1.5 + 0.8307207305278489 × DraftKings`. This existing market blend was not newly fitted on Weeks 3–6, but the user has studied it previously.
5. **Full market** and **50/50** for comparison.

**Odds:** Match event ID to public cfbfastR-cfb-raw `cfb/betting/json/{game_id}.json`, with both sides' DraftKings `open.moneyLine.american` from the same record and two-sided overround 0–16%. No-vig market implied probabilities. The archived opening quote may have been revised, and the exact originally available quote timestamp was not independently authenticated. Closing odds were evaluated as a sensitivity, not substituted into the primary result.

**Model predictions:** Weeks 3 and 4 retrospectively reconstructed with current code and published weekly summaries, using only earlier-week snapshots, **115 games**. Weeks 5 and 6 obtained from locked pre-kickoff original V1.5 snapshots with final-score agreement, **112 games**. Both sources use the same model definition; however, reconstruction and original captures do differ in some games. Replaying the current model against the frozen Week 5–6 cohort changes **7 of 112 predicted winners**, mean home-probability absolute difference ~**2.85 percentage points**, emphasizing historical reconstruction limitations.

**Coverage:** 229 completed regular-season model-eligible matchups in 2026 Weeks 3–6 schedule. Two completed Week 6 matchups lack frozen pregame V1.5 records (**Stanford at Notre Dame** and **Maryland at Ohio State**) and are excluded. This yields **227** baseline games. Six Week 3–4 baseline games lack qualifying DraftKings opening price pairs (Kent State at Ohio State; Buffalo at Penn State; UTEP at Michigan; Western Kentucky at Indiana; Sam Houston at Texas Tech; Central Michigan at Miami). Those six baseline picks all happened to be correct. Main head-to-head is therefore **221 same-game, same-quote matchups**, distributed Weeks 3/4/5/6 as **53/56/56/56**.

## Primary headline

| Prediction method | Correct / 221 | W–L | Accuracy | Brier |
|---|---:|---:|---:|---:|
| Official V1.5 | 158 | **158–63** | 71.49% | 0.187794 |
| Test C warning only, no change | 158 | 158–63 | 71.49% | 0.187794 |
| C switch to market favorite when warning and opposite side | 157 | **157–64** | 71.04% | 0.186644 |
| Fade every warning | 156 | 156–65 | 70.59% | 0.192705 |
| Market only (opening odds) | 166 | 166–55 | 75.11% | 0.169937 |
| Previous 16.93% model / 83.07% market blend | **169** | **169–52** | **76.47%** | **0.170147** |
| 50% / 50% blend | 165 | 165–56 | 74.66% | 0.173864 |

The fixed 16.93/83.07 blend made 29 different winner predictions from V1.5: 20 corrections and nine newly wrong picks, net **+11**. The paired exact two-sided McNemar/binomial p-value is approximately **0.061**, meaning the apparent edge is encouraging but below neither a conventional 0.05 threshold nor a prospective validation standard. The pure market Brier is slightly better than the blend (0.169937 vs. 0.170147) despite having three fewer correct winners.

The C market switch made **7** pick changes: **3 corrections, 4 newly wrong**, net **−1**.

## Week-by-week

| Week | matched games | V1.5 | C market switch | 16.93%/83.07% blend | Market only |
|---|---:|---:|---:|---:|---:|
| Week 3 (reconstructed) | 53 | 43–10 | 42–11 | 45–8 | 46–7 |
| Week 4 (reconstructed) | 56 | 38–18 | 37–19 | 46–10 | 45–11 |
| Week 5 (frozen) | 56 | 42–14 | 41–15 | 41–15 | 38–18 |
| Week 6 (frozen) | 56 | 35–21 | 37–19 | 37–19 | 37–19 |
| **Combined** | **221** | **158–63** | **157–64** | **169–52** | **166–55** |

Full baseline even without quotes: **164–63 in 227 games** (72.25%). Do not compare a model on 227 games with an odds-assisted model on only 221 games and attribute that difference solely to model quality.

## Warning itself, historical Weeks 3–6

With **DraftKings opening lines**, C's 70/55 rule flagged **10/221** predictions. Their original V1.5 outcomes were **6 wins, 4 losses**. Unlike the 2024/25 odds replication, the *2026 opening-price* warning did not identify more wrong than correct winners across these four weeks.

- Week 3: 1 warning, **1–0 V1.5**
- Week 4: 3 warnings, **2–1 V1.5**
- Week 5: 2 warnings, **2–0 V1.5**
- Week 6: 4 warnings, **1–3 V1.5**

Of the ten flagged games, **seven** had an opposing bookmaker favorite and therefore qualified for actual C winner switching. The remaining three had both the sportsbook and V1.5 narrowly favoring the same team despite large differences in confidence; warning did not switch those winners.

**Abstention:** skipping 10 warnings retains 211 games with V1.5 **152–59 (72.04%)**, versus 158–63 (71.49%) on the full quoted cohort. It avoids four losses but also six wins. The resulting accuracy difference of just 0.55 points on a *smaller subset* is not equivalent to new correct winners or profitability.

Switches that fixed V1.5 misses:
- Week 4: UConn at Miami (OH) — switched from UConn to Miami (OH).
- Week 6: Sacramento State at Bowling Green — switched from Sacramento State to Bowling Green.
- Week 6: Louisiana at Louisiana Tech — switched from Louisiana to Louisiana Tech.

Switches that broke V1.5 correct winners:
- Week 3: James Madison at San Diego State — switched away from James Madison.
- Week 4: Liberty at Coastal Carolina — switched away from Liberty.
- Week 4: San Diego State at Toledo — switched away from Toledo.
- Week 5: Pittsburgh at Virginia Tech — switched away from Pittsburgh.

**Odds-time sensitivity:** archived DraftKings **closing** prices on the 221 games produce only **seven warnings**, of which V1.5 was **2–5**. Switching the pick in all seven cases would yield **161–60**, net +3 over V1.5; blending gave **170–51**, net +12. This *change from a net loser on opening lines to a winner on closing lines* demonstrates that the warning's effect depends materially on which pregame quote is used. Do **not** silently replace opening prices with historical closing records in any prospective validation.

The earlier frozen Week 5–6 experiment yielded **1–4** flagged on quotes collected by its own pregame capture process. The opening-quote archive in this experiment gives **3–3** in Weeks 5–6 because the captured price times/values and qualifying games differ. These are different cohorts, not contradictory arithmetic.

## Decision

**Do not deploy Test C's 70/55 warning as an automatic winner reversal or a proven pick exclusion.** This exact head-to-head produces −1 correct winner after four weeks and the warning itself covers just ten games; 2026 opening odds show a markedly weaker warning-loss rate than the retrospective 2024–25 analysis.

The **preexisting 16.93% / 83.07% probability blend** is the stronger actual prediction challenger on Weeks 3–6, with **+11 correct winners and lower Brier score** versus V1.5. Nonetheless, Weeks 3–4 use reconstructed model probabilities, the odds archive has unverified original publication timestamps, market-based winner counts are not comparable to live close prices, and statistical evidence is insufficient for deployment. Freeze probabilities prospectively under both methods and assess the next genuinely unseen cohort with an identical quote source/time policy.

No app, main-branch or waterfall-tier code modified.

## Reproduce

`research/test_c_head_to_head_weeks3_6.py` recreates V1.5 reconstruction for Weeks 3–4, joins frozen Week 5–6, retrieves archived DraftKings opening and closing price records by game ID, validates quotes, computes all head-to-head scores, and writes `research/test_c_head_to_head_weeks3_6_results.json` and `research/test_c_head_to_head_weeks3_6_games.csv`.

`.github/workflows/test-c-head-to-head-weeks3-6.yml` runs the research on an isolated branch.
