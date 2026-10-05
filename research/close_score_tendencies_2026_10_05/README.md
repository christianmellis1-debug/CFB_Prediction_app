# Close-score tendency test

2024–2025 regular seasons and 2026 through Week 4. P4/P4 and G6/G6, Notre Dame P4. Original six-metric features and outcomes remain fixed.

## Definition

Prior completed FBS games from earlier weeks only. At the start of each play: margin within 8 points; quarters 1–3; exclude final 120 seconds of Q2. At least 30 classified close-score plays per team, with play-by-play present for every prior FBS game. Sacks counted as dropbacks. Kneels, spikes, no-plays and negated plays removed. Scrambles sought in text, but zero were explicitly identified: unmarked scrambles remain a limitation. Rush-majority >50%, pass-majority <50%, balanced exactly 50%. Thresholds fixed before reading outcome tables.

## Coverage

2,304 of 2,604 team observations are eligible. Excluded: 165 missing at least one prior-game play-by-play record, 135 with fewer than 30 close-score plays. 2024: 980/1,190; 2025: 1,185/1,222; 2026: 139/192. Both teams eligible in 1,041 of the original 1,302 games. No imputation. All figures below use this smaller eligible sample. Each game can contribute two team observations; these are dependent observations, not independent model bets.

## All advantage counts

### P4

| Count | Run-majority | Pass-majority | Balanced |
|---|---:|---:|---:|
| 6 | 31–2 (93.9%) | 36–6 (85.7%) | 1–1 (50.0%) |
| 5 | 67–25 (72.8%) | 47–30 (61.0%) | 4–0 (100.0%) |
| 4 | 74–38 (66.1%) | 63–31 (67.0%) | 1–1 (50.0%) |
| 3 | 61–72 (45.9%) | 61–48 (56.0%) | 2–3 (40.0%) |
| 2 | 33–69 (32.4%) | 43–70 (38.1%) | 1–1 (50.0%) |
| 1 | 27–79 (25.5%) | 29–48 (37.7%) | 1–0 (100.0%) |
| 0 | 4–37 (9.8%) | 11–36 (23.4%) | 1–3 (25.0%) |

### G6

| Count | Run-majority | Pass-majority | Balanced |
|---|---:|---:|---:|
| 6 | 40–9 (81.6%) | 16–3 (84.2%) | 0–1 (0.0%) |
| 5 | 64–32 (66.7%) | 34–21 (61.8%) | 1–1 (50.0%) |
| 4 | 76–54 (58.5%) | 52–33 (61.2%) | 4–1 (80.0%) |
| 3 | 71–48 (59.7%) | 32–47 (40.5%) | 0–2 (0.0%) |
| 2 | 51–70 (42.1%) | 38–67 (36.2%) | 1–4 (20.0%) |
| 1 | 31–51 (37.8%) | 30–45 (40.0%) | 0–2 (0.0%) |
| 0 | 6–37 (14.0%) | 7–23 (23.3%) | 0–1 (0.0%) |

## Same-sample comparison with overall usage

The following restricts both versions to the same eligible team observations and combines five/six advantages. Differences between styles are descriptive, not causal.

| Group | Usage definition | Run-majority | Pass-majority |
|---|---|---:|---:|
| P4 | Overall box-score | 141–40 (77.9%) | 45–24 (65.2%) |
| P4 | Close-score PBP | 98–27 (78.4%) | 83–36 (69.7%) |
| G6 | Overall box-score | 122–49 (71.3%) | 28–18 (60.9%) |
| G6 | Close-score PBP | 104–41 (71.7%) | 50–24 (67.6%) |

## Weighted candidate

Same formula as the pilot: each rushing advantage receives 2 × rush share; passing advantage receives 2 × pass share; other three statistical advantages and venue remain one vote each. Equal totals abstain. No weights fitted to results.

On 857 games where all versions selected a winner: all three went 581–276 (67.8%). Close-score weighting did not change any baseline selection in this paired sample.

Additional selections where baseline abstained: 76–67 (53.1%) over 143 games. G6: 40–25; P4: 36–42. Overall close-weighted candidate: 657–343 on 1,000 selections. Overall-usage weighted candidate: 661–339 on 1,000 selections. Their larger selection sets are not comparable directly with the baseline 857-pick denominator.

## Interpretation

P4 run-majority teams retained higher win rates at five and six advantages; G6 six-advantage teams did similarly well with either preference (19 pass-majority observations). There is no universal run-majority bonus across counts. At three advantages, G6 favors run-majority while P4 favors pass-majority. The six-advantage P4 run-majority sample is only 33. These many exploratory subgroups should not be converted directly into probability estimates.

Five/six combined by season is provided in high_counts_by_season.csv. P4 run-majority direction held in 2024 and 2025, but 2026 samples are small. None of these seasons is an untouched holdout because prior model research used them. Close-score selection reduces score-state distortion but does not control opponent strength, roster quality, down/distance, or coaching decisions. Feed revisions and unresolved scramble classification remain limitations. This measures winner accuracy, not profitability. Recommendation: retain as a research feature, no production weight change justified.

## Sources and reproduction

Source: https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/espn_cfb_pbp (play_by_play_2024/2025/2026.parquet). Earlier six-metric inputs: turnover_test and tendency_test research files. fetch.py retrieves source data; run.py computes prior-game counts and features; report.py summarizes. Scripts expect earlier research directories alongside this directory. Published specification and hashes preserve the test definition. No production or Week 5 frozen prediction edits.
