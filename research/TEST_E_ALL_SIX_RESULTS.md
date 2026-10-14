# Saturday Forecast — Test E: All six matchup characteristics

**Research completed October 13, 2026. No deployment: V1.5, primary Test C 16.9279%/83.0721% and the six betting tiers were not modified.**

## Design: same-game comparisons with a season-separated check

One hundred and one explicitly specified candidate rules were evaluated in **six separate test families**. All outcomes use the same matchup, identical archived opening-moneyline book source and identical completed final score as the existing Test C predictor:

- 2024: **717** matched FBS games with historical ESPN BET two-sided opening prices; current-code retrospective V1.5. **Development year**, use only 2024 Brier to choose one representative rule per family.
- 2025: **720** matched FBS games with historical ESPN BET two-sided opening prices; current-code retrospective V1.5. **Separate later-year historical comparison** (not a clean model-wide holdout since previous model development used 2025).
- 2026 Weeks 3–6: **221** matched FBS games with historical DraftKings two-sided opening prices; Weeks 3–4 have reconstructed V1.5, Weeks 5–6 have original locked pregame V1.5 probabilities. **112 Week 5–6 games** have the frozen V1.5 baseline, but their *odds in this specific comparison are archived opening prices*, not necessarily the bookmaker quotes originally captured in the forward tracker.

The same 16.927926947215113% V1.5 and 83.072073052784887% bookmaker probabilities were used as the baseline for every comparison. The altered models used only prior-week team and game statistics (or same-matchup pregame bookmaker prices) to form their signals. Candidate weights and thresholds were declared before evaluating outcomes, but the 2024-selected conditions are still development-tuned and not reliable estimates of future effects.

**Baseline:** 2024 **509–208 (70.99%, Brier .1834894)**, 2025 **527–193 (73.19%, Brier .1822763)**, 2026 **169–52 (76.47%, Brier .1701468)**. On the 112 frozen-V1.5 2026 Week 5–6 events, the cohort baseline with these archived opening prices was **78–34**.

## Main results: 2024-selected candidate for each feature

| Family | Selected rule | Rules tested | 2024 W–L | 2025 W–L | 2026 W3–6 W–L | 2026 W5–6 (frozen V1.5) |
|---|---|---:|---:|---:|---:|---:|
| **E1 close market** | If market home probability in 40–60%, use 10% V1.5 / 90% market | 12 | **510–207 (+1)** | **528–192 (+1)** | 168–53 (−1) | 76–36 (−2) |
| **E2 model/market disagreement** | Difference ≥20 points: 35% V1.5 / 65% market | 20 | 505–212 (−4) | 523–197 (−4) | 168–53 (−1) | 78–34 (0) |
| **E3 weak opponents + strong offense** | For the *same team*, prior opponent SOS ≤−1 z with prior offense ≥+0.5 z: transfer 10 points from offense to SOS inside V1.5 | 9 | **510–207 (+1)** | 527–193 (0) | 169–52 (0) | 78–34 (0) |
| **E4 unit mismatch** | Difference in absolute offense/defense matchup ratings ≥0.50 z; transfer 10 points from weaker-impact unit to stronger-impact unit | 12 | 509–208 (0) | 526–194 (−1) | 168–53 (−1) | 77–35 (−1) |
| **E5 home/road performance** | Venue signal ≥0.25 in absolute value with ≥2 prior relevant home and road games; reduce venue weight by 5 points, share across offense/defense | 24 | 509–208 (0) | 526–194 (−1) | 169–52 (0) | 78–34 (0) |
| **E6 statistical reliability** | Either team has fewer than 3 prior FBS games: raise V1.5 share to 35% (market 65%) | 24 | 506–211 (−3) | **528–192 (+1)** | 165–56 (−4) | 77–35 (−1) |

Parenthetical values give changes in correct winners relative to the corresponding same-game baseline. The six selections were made independently *on 2024 Brier only*, not cherry-picked for 2025/2026 winner totals.

### Probability-score changes relative to the baseline (positive is good; lower raw Brier better)

| Family | 2024 Brier improvement | 2025 Brier improvement | 2026 Brier improvement |
|---|---:|---:|---:|
| E1 | +0.0001012 | −0.0000486 | −0.0002253 |
| E2 | +0.0001541 | −0.0011473 | −0.0008984 |
| E3 | **+0.0000068** | −0.0000027 | +0.0000209 |
| E4 | +0.0000828 | +0.0002675 | −0.0000279 |
| E5 | +0.0000437 | −0.0000704 | +0.0000107 |
| E6 | +0.0004013 | −0.0005487 | −0.0020712 |

**No selected candidate improved both winner accuracy and Brier score in all three seasons.** Inspecting **all 101 candidates** rather than just the six selected finalists also found **zero** candidates with both an improvement in Brier and non-decreasing winner accuracy in **each of 2024, 2025 and 2026**. Post-hoc, some unselected rules achieved isolated +1 or +2 correct picks on a later season, but those gains did not have stable calibration or winner effects across all three periods.

### How often each selected rule triggered

| Family | 2024 events | 2025 events | 2026 events |
|---|---:|---:|---:|
| E1 | 180 | 171 | 55 |
| E2 | 82 | 74 | 32 |
| E3 | 9 | 10 | 3 |
| E4 | 319 | 323 | 100 |
| E5 | 293 | 304 | 9 |
| E6 | 188 | 196 | 118 |

A few observations:
- **E1 close games:** A 40–60% market bucket contains many genuine tossups, so a special coefficient has potential leverage; however, this development-year choice lost two originally correct picks on the frozen-model Week 5–6 2026 slice.
- **E2 disagreement:** Increasing the independent V1.5 input to 35% when it differs markedly from the market is actively worse on all three complete year/window checks.
- **E3 weak opposition:** The **same team** must have strong prior offensive rating and weak historical opponent rating; mixing one team's strong offense with another team's weak opponents would falsely trigger games. This corrected definition fires on just 22 historical events across all three periods, fixes a single 2024 game and none in later years.
- **E4 offense/defense:** This operationalization uses V1.5's *overall offense/defense unit ratings*; it is **not a fully matchup-specific rushing-versus-rushing-defense or passing-versus-pass-defense test**. The observed impact is too small/inconsistent to implement.
- **E5 venue:** The previous venue signal from average home/road margins is highly dependent on prior venue samples; threshold + sample criteria activate very few games early in 2026. The previously tested universal venue coefficient of 20% stays justified.
- **E6 reliability:** The 2024 calibration gain of this rule did not generalize; the 2026 sample produced **four newly wrong picks net**. Exploratory 2026-only alternatives with less V1.5 influence in thin data samples are not enough to justify another model revision.

## Combined scenario: applying all six 2024-selected rules together

For an additional *exploratory* check, the per-family market-weight differences were added around the existing 16.93% Test C weight and capped between 5% and 65%; the three football-specific V1.5 log-odds effects were added before the market blend. **No new coefficients were fitted to 2025 or 2026.**

| Model | 2024 / 717 | 2025 / 720 | 2026 W3–6 / 221 |
|---|---:|---:|---:|
| **Official Test C** | **509–208** | **527–193** | **169–52** |
| **All six selected rules combined** | 509–208 | **519–201 (−8)** | **164–57 (−5)** |
| Football-only E3+E4+E5 | 509–208 | 526–194 (−1) | 168–53 (−1) |
| Market-only E1+E2+E6 | 509–208 | 522–198 (−5) | 163–58 (−6) |

Combined all-six Brier: **2024 0.1829545** (baseline 0.1834894), **2025 0.1840274** (baseline 0.1822763), **2026 0.1737195** (baseline 0.1701468). Thus combining these individually tuned rules is **worse** in both later-year checks and is **not an upgrade**.

## Decision and the next useful hypothesis

**Keep Saturday Forecast's current 16.93%/83.07% Test C blend, unchanged V1.5 base, and the independent waterfall tier logic.** Conditional weighting alone did not reveal a proven advantage. The research showed positive signals in isolated Brier or winner cells but **no stable rule** over 2024/2025/2026.

The next candidate should use richer, *actually paired football-specific data*, especially pass blocking/pass-rush pressure, rushing offense versus yards-per-carry allowed, explosive passing and defensive coverage, **instead of only reweighting the model's four broad composite inputs**. We should evaluate each using strictly prior-week observations, 2024 development, 2025/2026 validation and market-quote-matched V1.5/Test C outcomes. Any apparent gain should survive both independent model and market-blended scoring before production.

## Reproduction and limitations

- `research/test_e_all_six_matchup_factors.py` implements all six feature families and **101 frozen parameter combinations**, builds strictly prior-week 2024–2026 football features and matches archived odds/event IDs.
- `research/test_e_six_signals_results.json` stores every candidate's overall and trigger-only accuracy, Brier, log loss, and weekly provenance by season.
- `research/test_e_six_signals_games.csv` stores each matched game with underlying features and all six 2024-selected rules' predictions and activation flags.
- `research/test_e_combined_selected.py` and `research/test_e_combination_results.json` verify the full combination and football-only/market-only subset combinations.
- `.github/workflows/test-e-six-matchup-factors.yml` and `.github/workflows/test-e-combined-selected.yml` reproduce this research on an isolated branch, without modifying production code.

**Limitations:** The 2024 and 2025 model scores are retrospective, not locked original 2024/2025 pregame snapshots. Historical sportsbook opening prices were retrieved from archived ESPN and DraftKings game files with timestamps not independently established. Source weekly team summaries may have been revised after games. Weeks 5–6 2026 have frozen V1.5 but the modified candidates are retrospective reconstructed deltas on the original pregame probabilities. 2025 is a later chronological check, **not a clean unseen model-wide holdout**, because the overall model has previously been researched using historical 2025 data. The 101-candidate grid imposes multiple-comparison/overfitting risks. No ATS, betting ROI or value-creation benefit has been established.

**No live app changes were performed.**
