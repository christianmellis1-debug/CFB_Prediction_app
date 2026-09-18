# V1.5 conference calibration validation

Date: September 18, 2026. Decision: deploy conference calibration only.
The EPA alternatives tested here did not justify replacing the existing EPA logic.

## Design and predeclared gate

Reconstruct pregame-week predictions for completed regular-season FBS games:
2022 (734), 2023 (750), 2024 (752), 2025 (762): 2,998 games total.
Fit conference log-odds offsets on 2022–23; select a candidate using 2024;
evaluate the selected candidate on 2025 without refitting. The previous audit
already examined 2025, so it is not a pristine unseen season. Existing model
parameters may also have been developed using these historical seasons.

Candidates: existing EPA logic, independently standardizing adjusted/raw EPA
before fallback, and using raw EPA consistently. Each was tested with no,
half-strength, or full fitted conference correction (eight alternatives total).
Select the lowest 2024 overall Brier score among candidates passing the gate:
both Brier and log loss must improve overall and in cross-group games, with
accuracy dropping by no more than 1 percentage point overall and 3 points in
cross-group games. Apply the same gate to 2025.

## Results

The selected candidate retains existing EPA logic and adds 1.2610042485353463
to the power team's log odds in eligible cross-group matchups. This is a
probability calibration, not a fixed percentage bonus or guaranteed favorite.

| Sample | Metric | V1.4 | V1.5 |
|---|---|---:|---:|
| 2024 cross-group, 86 games | Brier | 0.10614 | 0.06626 |
| 2024 cross-group | Log loss | 0.34852 | 0.22610 |
| 2024 cross-group | Correct winners | 73 | 79 |
| 2025 cross-group, 89 games | Brier | 0.10909 | 0.08509 |
| 2025 cross-group | Log loss | 0.36393 | 0.27876 |
| 2025 cross-group | Correct winners | 80 | 78 |
| 2024 all 752 games | Brier | 0.19444 | 0.18988 |
| 2024 all | Log loss | 0.56957 | 0.55557 |
| 2024 all | Winner accuracy | 68.48% | 69.28% |
| 2025 all 762 games | Brier | 0.18432 | 0.18151 |
| 2025 all | Log loss | 0.54573 | 0.53578 |
| 2025 all | Winner accuracy | 73.10% | 72.83% |

Across the two evaluation seasons, cross-group correct picks increase from
153/175 to 157/175, but the improvement is not uniform by year. The change
passes the gate; it does not establish improved betting profitability.

The game-level bootstrap 95% interval for 2025 overall Brier difference is
[-0.00635, +0.00088]. It includes zero. Games share teams and weeks, so this
simple resampling is descriptive and does not establish statistical certainty.

## Conference classification and limits

Use each game's recorded season/conferences. In 2022–23, Pac-12 belongs to the
power group; in 2024–25, the two-member Pac-12 is excluded. In 2026 onward,
Pac-12 belongs to the group side. This 2026 extension is prospective, not directly
validated on a completed season under the new membership.

Other power conferences: ACC, Big Ten, Big 12, SEC. Other group conferences:
American Athletic, Conference USA, Mid-American, Mountain West, Sun Belt.
Independents, unknown/missing classifications, FCS games, postseason games,
and seasons before 2022 receive no correction. Same-group games are unchanged.
Uploads missing classification columns receive no correction.

Historical power-over-group records: 2022 71/81, 2023 76/90, 2024 78/86,
2025 77/89. These base rates describe scheduled matchups, not causal conference
effects and not a universal win probability for every power team.

On the September 18 data snapshot, Texas–UTSA Week 3 moves from 61.4849% to
84.9252% (High). It still uses the original team-strength inputs. Missing
adjusted EPA remains a limitation; the tested replacements did not improve
later-season scoring. Recalculated historical scenarios will use the new model;
actual recorded bet stakes, moneylines and results are unchanged.

## Verification and reproduction

`test_conference_calibration.py` verifies era classification, home/away symmetry,
excluded game types, probability bounds, and exact parity with the independent
candidate calculation for all 1,514 games in the two evaluation seasons.

Sources: SportsDataverse schedule CSVs at
https://github.com/sportsdataverse/cfbfastR-data/tree/main/schedules/csv
and weekly summaries at
https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/cfb_team_summaries_weekly

Place schedules 2022–25 at the repo root as scheduleYYYY.csv, and summaries
2021–25 as summaryYYYY.csv. Install pandas/numpy/scipy. Run
`python backtests/extended_calibration.py`, then
`python backtests/test_conference_calibration.py`. Delete extended_*.csv caches
before rerunning with changed data. The script uses the frozen V1.4 reference,
not the now-updated production model. Input SHA-256 hashes, all candidate scores,
and gate results are in extended_results.json. Source feeds can revise history;
these are reconstructed predictions, not timestamped pre-kickoff forecasts.
