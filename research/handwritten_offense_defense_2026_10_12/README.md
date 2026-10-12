# User's handwritten 40/25/15/10/10 offense and defense formula — October 12, 2026

**Research only. No changes to Saturday Forecast V1.5 production model, official value tiers, or prospective comparison.**

## Exactly what was tested

The weights were read from the handwritten photograph; each internal unit totals 100%. The existing 35% offense + 35% defense + 20% venue + 10% strength-of-schedule overall model remains unchanged.

| Internal input | Offense weight | Defense weight | Definition |
|---|---:|---:|---|
| Adjusted EPA/play | 40% | 40% | Production adjusted EPA standardized; defensive EPA is sign-reversed |
| Run | 25% | 25% | Prior completed FBS rushing yards / attempts; on defense opponent rushing yards per attempt allowed, sign-reversed |
| Pass | 15% | 15% | Prior completed FBS pass completions / attempts; on defense opponent completion percentage allowed, sign-reversed |
| Turnovers | 10% | 10% | On offense giveaways per prior FBS game, sign-reversed; on defense opponent giveaways forced per prior FBS game, positive orientation |
| Explosive plays | 10% | 10% | Prior-week production explosive-play rate, sign-reversed on defense |

This directly replaces the **current-season** internal 40% EPA, 30% success, 15% explosive, 15% red-zone unit weights. The previous-season rating/Elo prior is intentionally unchanged, as are the calibrated sigmoid and model weighting of offense vs defense. The user's hypothesis is tested *as written*, without hyperparameter optimization or after-the-fact adjustments.

Each box-score metric requires completed earlier-week games, consistent turnovers, unambiguous team IDs, and both teams' box scores. Teams with any missing past FBS box history are excluded. Every game in the A/B comparison is identical, so the model-accuracy differences are paired. These are historical reconstructions based on currently downloadable datasets, not the immutable pregame forward archive.

## Results on identical games

| Year | Games | V1.5 record | Handwritten record | Change in correct winners | V1.5 Brier | Handwritten Brier |
|---|---:|---:|---:|---:|---:|---:|
| 2022 | 630 | 431–199 (68.4%) | 414–216 (65.7%) | −17 | .204945 | .210099 |
| 2023 | 646 | 474–172 (73.4%) | 478–168 (74.0%) | +4 | .183542 | .182212 |
| 2024 | 659 | 470–189 (71.3%) | 456–203 (69.2%) | −14 | .188922 | .192771 |
| 2025 | 663 | 474–189 (71.5%) | 470–193 (70.9%) | −4 | .185770 | .186667 |
| 2026 Weeks 3–6 | 228 | 164–64 (71.9%) | 164–64 (71.9%) | 0 | .180809 | .180122 |
| **Total** | **2,826** | **2,013–813 (71.2%)** | **1,982–844 (70.1%)** | **−31** | — | — |

2026 Week 6 specifically, retrospective cohort of 58 eligible games: baseline 37–21 (63.8%), handwritten 32–26 (55.2%). Different from the 56-game V1.5 immutable forward archive. Five Week 6 loser flips:

- UCF at Oklahoma State: V1.5 Oklahoma State correct; handwritten UCF incorrect
- Tulane at Army: V1.5 Army correct; handwritten Tulane incorrect
- Ole Miss at Vanderbilt: V1.5 Ole Miss correct; handwritten Vanderbilt incorrect
- UConn at Temple: V1.5 UConn correct; handwritten Temple incorrect
- Boise State at Fresno State: V1.5 Boise State correct; handwritten Fresno State incorrect

2026 Weeks 3–6 showed 16 changed picks, 8 fixed and 8 newly incorrect, so season accuracy tied. High-confidence (>or=80%) hit rate improved from 69/78 to 72/78, but confidence sets can contain different games. Brier was modestly lower in 2023 and 2026, but worse in 2022, 2024, 2025.

## Interpretation / next decisions

The five-season historical evidence **does not support immediately adopting the user's entire handwritten formula**. It does not prove the user's qualitative rushing premise wrong: other prior tests showed higher rushing offense and better run defense are associated with win likelihood; the new formula may simultaneously overemphasize turnover volatility and raw completion percentage and remove predictive success-rate/red-zone information.

Next isolate each proposed change while keeping every other part of V1.5 constant: (a) run offense 25%, (b) run defense 25%, (c) completion percentage 15%, (d) giveaways/forced turnovers 10%, and (e) reduce explosive from 15 to 10%. Compare the exact handwritten mix to the stronger defense-run-only control from the previous 33-scenario run. Then require new archived future games to support any replacement. Distinguish plain winning percentage and Brier calibration from sportsbook ATS/ML return.

## Reproducibility

- Exact code: run.py
- Full year-by-year results, early-week complete FBS coverage, and every changed 2026 winner: results.json
- Validation tests: tests/test_handwritten_offense_defense.py
- GitHub Actions: .github/workflows/handwritten-weights.yml

No changes to production app.py, model_v1_5.py, or frozen pregame forward archives.
