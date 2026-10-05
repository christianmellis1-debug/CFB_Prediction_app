# Three-stage Value Picks waterfall

Selection method: waterfall-v1. This replaces the probability-edge labels in the Streamlit app and Python API. It is a rule-based selection layer, not a retrained or newly calibrated probability model. No claim of a higher hit rate or positive returns has been validated.

## Exact integration points

- `matchup_advantages.py`: `normalize_fbs_schedule`, `build_waterfall_profiles`, `select_waterfall`. The existing five-metric research risk flag remains separate.
- `model_v1_5.py`: `predict_week` is the core aggregation function. Its output is annotated by `add_waterfall_value` after DraftKings quotes are attached. `waterfall_scenario_rows` adapts selected sides/prices on a copy for the existing simulator. `build_prior_profiles` excludes Sacramento State's pre-2026 efficiency profile and neutralizes its 2026 prior vector.
- `app.py`: `predict_all_games` → `attach_results` → `attach_odds` → `add_betting_value` (diagnostic fields only) → `add_waterfall_value`. The Value Picks tab, count, game-card badge and best-opportunities scenario consume `Value Selected`. `Predicted Winner`, `Confidence`, and model grading remain separate.
- `backend/main.py`: `/api/predictions` now uses V1.5 and the same annotation function after `attach_market_context`. API responses include `value_card`, `value_card_status`, and a feed error if box scores cannot load. Backend dependencies already include SciPy.
- `tests/test_waterfall.py`: boundary, gates, missing-data, leakage, classification, ordering, cap and integration tests.

## Statistics contract

Input fields are `rushingYards`, `rushingAttempts`, `turnovers`, `fumblesLost`, `interceptions`, `game_id`, and `team_id` from the existing team box-score feed. Schedule metadata supplies season, week, kickoff, completion and subdivision.

| Profile key | Calculation |
| --- | --- |
| `off_run` | Own total rushing yards / own total rushing attempts |
| `def_run` | Opponents' total rushing yards / opponents' total rushing attempts |
| `margin` | (Opponents' turnovers − own turnovers) / eligible games |
| `games` | Number of eligible prior FBS games |

Both participating teams must be FBS in the season of the game. For every target, profiles use only completed current-season games in an earlier week and before target kickoff. FCS games never enter sums or denominators. The target game's stats and prior-season profiles never enter these gates. Missing/inconsistent/duplicate box-score rows fail closed instead of averaging partial histories. Turnover totals must match interceptions plus fumbles lost. Passing data are not required.

Sacramento State is FBS from 2026 and FCS before 2026 even if supplied metadata is stale. Official announcement: https://getsomemaction.com/news/2026/2/16/sacramento-state-joins-mid-american-conference-as-football-only-member.aspx . All other teams use season-specific schedule subdivision metadata; missing metadata is excluded. No conference-group restriction is imposed beyond FBS vs FBS, consistent with this requested waterfall.

## Selection rules and volume

1. **Tier 1: Gold Standard Underdog**: DraftKings +100 through +170 inclusive. Higher offensive YPC, lower defensive YPC allowed and strictly better turnover margin/game than favorite. Must be home or a true away Road Sweep; neutral sites do not qualify.
2. **Tier 2: Moneyline Parlay Anchor**: DraftKings −600 through −280 inclusive. Core model selects favorite at 0.70–1.00 confidence; favorite defensive YPC allowed < underdog offensive YPC; favorite turnover margin/game >= underdog's.
3. **Tier 3: Moderate Favorite Clear**: DraftKings −275 through −205 inclusive. Favorite offensive YPC > underdog defensive YPC allowed AND favorite defensive YPC allowed < underdog offensive YPC; strictly better turnover margin/game.

Both sides must have valid DraftKings prices from a matched quote, with a negative favorite and positive underdog. Generic/fallback-book lines do not qualify. Moneyline gaps remain gaps. Missing stats never pass a gate. No model-agreement requirement is added to tiers 1 or 3.

Volume interpretation: take all Tier 1 qualifiers up to the maximum 18. If fewer than 12, fill toward 12 with Tier 2, then Tier 3. Stop once within the 12–18 window; never weaken gates to reach 12. Within each stage order by kickoff then game ID. A short card displays its count and shortfall. These parameters are not tuned against outcomes.

`Value Pick`, `Value Side`, `Value Line`, `Value Tier`, `Value Stage`, `Value Reason`, `Value Rank`, `Value Selected`, and `Value Result` explicitly distinguish waterfall selections from core model predictions. Historical results and what-if payouts grade the waterfall-selected side and its DraftKings price. The core performance tab still grades core predictions.

## Limits and verification

- 22 tests pass (14 new waterfall/integration tests plus 8 existing risk-flag tests). Syntax compilation passes for all four production files.
- A saved-data Week 5 integration smoke run produced 56 core predictions and 6 selections with locally available DraftKings quotes. This was not an exhaustive current-feed scan or an accuracy backtest.
- The local runtime lacks FastAPI, so full HTTP startup was not run. The API market function and JSON output were tested in isolation; deployed requirements already list FastAPI and SciPy.
- The shortlist recalculates with available prices and box scores. It is not a durable, locked record of selections issued before kickoff. Completed cards are retrospective; latest/live prices may change card membership. A future prospective performance claim requires timestamped pregame snapshots.
- Model chance, implied probability and EV fields remain available to other existing tools (such as the parlay finder), but never determine waterfall membership.
- A high favorite hit rate alone does not establish profit. Odds ranges constrain prices but cannot guarantee protection from statistical outliers.
