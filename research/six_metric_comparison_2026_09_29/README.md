# App V1.5 vs six-advantage model — 2026

Captured 2026-09-29T19:36:44.433857+00:00. Week 5 picks were generated before every listed kickoff.

## Rules

Equal-weight five statistical advantages plus home venue; neutral venue awards neither; metric ties award neither; equal total means no pick. P4/P4 and G6/G6 only; Notre Dame P4. Earlier-week current-season FBS histories.

Five statistical metrics: rushing matchup estimate, completion matchup estimate, defensive YPC allowed, defensive completion percentage allowed, turnover margin per game. One additional point for home venue. Equal weights. No predicted win probability is inferred from the count.

## Historical same-game comparison

| Week | Games | App W–L | Six-metric W–L |
|---|---:|---:|---:|
| 2 | 9 | 1–8 | 3–6 |
| 3 | 30 | 23–7 | 22–8 |
| 4 | 40 | 25–15 | 26–14 |
| Total | 79 | 49–30 (62.0%) | 51–28 (64.6%) |

| Scope | App | Six-metric |
|---|---:|---:|
| P4 vs P4 | 21–18 (53.8%) | 24–15 (61.5%) |
| G6 vs G6 | 28–12 (70.0%) | 27–13 (67.5%) |

On 16 disagreements, app won 7 and six-metric won 9. Two extra correct picks is insufficient evidence to replace the app model. Metrics overlap and are not six independent signals. This research informed the rule, so historical performance is exploratory, not untouched holdout validation.

## Coverage

Week 1 has no comparable picks: this version requires current-season earlier-week FBS history. Across Weeks 1–4 there were 140 in-scope games: 44 missing sufficient data, 96 assessed, and 17 equal-count abstentions, leaving 79 paired picks. Week 2 is especially sparse and unstable. Historical predictions are reconstructed using present copies of earlier-week summaries, not archived real-time predictions. Source revisions/adjusted aggregates may differ from what was available then. Results measure winner accuracy, not betting profit.

## Week 5 forward test

56 FBS games; 53 same-group matchups assessed; 47 six-metric picks and 6 equal-count abstentions; 3 outside scope. Among the 47 picks, 38 agree and 9 disagree. Frozen selections are in week5_frozen_picks.csv and comparison.json. Grade these exact selections after finals; do not regenerate the snapshot. No automatic settlement job was added.

| Matchup | App | Six-metric | Home–away advantages |
|---|---|---|---|
| North Texas at Tulsa | North Texas | Tulsa | 5–1 |
| Navy at Air Force | Navy | Air Force | 4–2 |
| Ohio State at Iowa | Ohio State | Iowa | 4–2 |
| Kentucky at South Carolina | South Carolina | Kentucky | 2–4 |
| Oregon State at Colorado State | Oregon State | Colorado State | 4–2 |
| UL Monroe at South Alabama | South Alabama | UL Monroe | 2–4 |
| Texas Tech at Colorado | Texas Tech | Colorado | 3–2 |
| Cincinnati at Arizona | Arizona | Cincinnati | 2–4 |
| San José State at Hawai'i | San José State | Hawai'i | 4–2 |

Production model/picks and risk logic were not changed. Input and code hashes are retained with the snapshot; upstream data URLs are in run.py. Raw source CSVs are not committed.

For an independent rerun, copy run.py into a new directory, create inputs/, and copy app.py, model_v1_5.py and matchup_advantages.py from the recorded repository commit into that directory. Install pandas, numpy and scipy. The script downloads fresh feeds; source revisions may change reconstructed results. It refuses to overwrite an existing snapshot.
