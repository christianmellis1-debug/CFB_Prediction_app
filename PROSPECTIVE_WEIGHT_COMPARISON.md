# Saturday Forecast — prospective comparison: internal weights

**Research-only, no change to the official V1.5 predictions or five Value tiers.**

Starting from the first successful scheduled capture after deployment, GitHub Actions records all four model estimates simultaneously on the **same game**:

| Model | Offense EPA / success / explosive / red zone | Defense EPA / success / explosive / red zone |
|---|---|---|
| V1.5 current | 40 / 30 / 15 / 15 | 40 / 30 / 15 / 15 |
| Offensive EPA 60% | 60 / 20 / 10 / 10 | 40 / 30 / 15 / 15 |
| Defensive red zone 30% | 40 / 30 / 15 / 15 | 30 / 25 / 15 / 30 |
| Balanced defense 25% | 40 / 30 / 15 / 15 | 25 / 25 / 25 / 25 |

All other model weights stay exactly the same: 35% offense, 35% defense, 20% historical home/road, and 10% SOS. The 25%-efficiency/75%-Elo preseason prior, season weight schedule, conference correction, and sigmoid probability calibration also remain fixed.

## Capture and scoring

- Workflow: .github/workflows/prospective-weights.yml, every six hours at 00:29, 06:29, 12:29, 18:29 UTC, with an optional manual Actions run.
- Collector: capture_prospective_weights.py (imports production model_v1_5.py but **does not** import app.py).
- Prediction engine: prospective_weights.py (checks standardized per-week features against production, only uses completed earlier-week statistics).
- Archive and UI: prospective_weights_archive.py; immutable storage at data/prospective_weights_2026.json.
- First **verified pregame** observation within 18 hours of scheduled kickoff, only if ESPN confirms both team identities and an unambiguously future kickoff. Games outside this window, rescheduled games, or unavailable feeds may be missed.
- Original prediction and capture provenance are never overwritten, including a saved snapshot of all four probabilities and weights. Final score and actual winning side are stored separately after an ESPN-confirmed final. Earlier weeks are **not** backfilled or retroactively inferred.
- Main app → Model Results → **Forward test · four model weight configurations**. Select week or full 2026 season, then review same-game win accuracy, Brier score, >=80%-confidence accuracy, individual locked predictions, and optional CSV export.
- The same set of verified decisive games is used in every model's metrics. Missing data, pending results and ties are not counted as losses.
- The ledger is for **straight-up winner predictions only**, not live betting suggestions, spread picks, ROI, or the Value Shortlist.
- The official app cards and selections remain V1.5; no prediction is changed by this test.
- All source data may be revised by providers after the snapshot. Prospectively captured outcomes remain independent; results from the previous 39 retrospective alternatives are **not** copied into this archive.

## How to compare

Weekly monitoring is informational. Evaluate after an adequate, shared, truly prospective sample (initial goal roughly 200 finalized captured games), and inspect the distribution by week, high-confidence performance, accuracy and probability calibration. Do **not** select a model merely because it wins a single week or scores highest in a retrospective search.

The initial check was permitted to create an empty ledger; a successful workflow does not imply any game was eligible that day. GitHub Actions schedules can be delayed, and model/feed failures should appear in run_summary rather than be counted as game results.

Unit tests are in tests/test_prospective_weights.py and the normal GitHub app checks must continue to pass.
