# P4 short underdogs: focused validation

Question: in P4 vs P4 games whose favorite closes between −110 and −150 inclusive, do underdogs perform differently based on pregame offensive YPC, defensive YPC allowed, home venue or turnover margin? Notre Dame treated as P4. No G6, no passing metrics, no six-advantage selection rule.

## Scope

2024 and 2025 regular seasons, 2026 through Week 5. 159 priced qualifying games: 89 in 2024, 55 in 2025, 15 in 2026. Underdogs overall: 78–81 (49.1%). Both wins and losses included. Market favorite determined from both same-provider implied probabilities; equal-price games excluded. P4 schedule-wide missing price pairs: 8 in 2024 and 12 in 2025; whether these belonged in the odds window is unknown.

2024–2025 prices: ESPN BET via ESPN archives. 2026: DraftKings via ESPN. These are archived closing labels, not independently timestamp-verified snapshots. Opening/closing timing and provider differences prevent an exact replication of Google’s unspecified sample. We cannot validate its exact 676-game totals without its underlying data.

## Pregame definitions

Earlier-week completed current-season FBS games only, before target kickoff. Offensive YPC = total rushing yards / total rushing attempts. Defensive YPC allowed = opponent total rushing yards / opponent rushing attempts. Compare directly with the favorite’s corresponding metric. These are raw rates, not offense/defense blended matchup estimates. Turnover margin = (takeaways − giveaways) / prior FBS games, compared with the favorite’s margin per game. Venue uses neutral-site flag, not merely designated home team. Prior FCS games excluded. NCAA rushing stats include sacks; no neutral-situation filter in this test.

15 games lack sufficient earlier-week metric history, including 8 underdog wins. They stay in the overall and venue tables but are separately missing in stat comparisons; no imputation. All three stat comparisons have 144 qualifying observations. Winning underdogs with known stats: 70.

## All underdogs by condition

Each entry is W–L (win rate), followed by net hypothetical profit at $10 per bet. Groups overlap; do not add group profits together.

| Condition | 2024–2025 | 2026 through Week 5 | Combined |
|---|---:|---:|---:|
| Home team | 26–30 (46.4%); $-5.46 | 3–6 (33.3%); $-25.94 | 29–36 (44.6%); $-31.40 |
| Away team | 38–41 (48.1%); $+18.50 | 3–3 (50.0%); $+1.02 | 41–44 (48.2%); $+19.52 |
| Neutral site | 8–1 (88.9%); $+79.50 | No games | 8–1 (88.9%); $+79.50 |
| Higher offensive YPC | 29–26 (52.7%); $+62.52 | 4–3 (57.1%); $+10.28 | 33–29 (53.2%); $+72.80 |
| Lower offensive YPC | 35–41 (46.1%); $-14.48 | 2–4 (33.3%); $-15.20 | 37–45 (45.1%); $-29.68 |
| Lower defensive YPC allowed | 31–31 (50.0%); $+31.02 | 1–6 (14.3%); $-50.48 | 32–37 (46.4%); $-19.46 |
| Higher defensive YPC allowed | 33–36 (47.8%); $+17.02 | 5–1 (83.3%); $+45.56 | 38–37 (50.7%); $+62.58 |
| Better turnover margin/game | 32–20 (61.5%); $+151.04 | 2–1 (66.7%); $+10.52 | 34–21 (61.8%); $+161.56 |
| Worse turnover margin/game | 28–43 (39.4%); $-111.00 | 4–5 (44.4%); $-5.44 | 32–48 (40.0%); $-116.44 |
| Equal turnover margin/game | 4–4 (50.0%); $+8.00 | 0–1 (0.0%); $-10.00 | 4–5 (44.4%); $-2.00 |
| Home + higher offensive YPC | 10–7 (58.8%); $+43.02 | 1–1 (50.0%); $-0.74 | 11–8 (57.9%); $+42.28 |
| Home + higher YPC + lower allowed YPC | 4–1 (80.0%); $+33.02 | 0–1 (0.0%); $-10.00 | 4–2 (66.7%); $+23.02 |
| All four advantages | 3–0 (100.0%); $+30.52 | No games | 3–0 (100.0%); $+30.52 |

## Google winner-characteristic claims

Google said 182/311 winning underdogs were home (58.5%). Our different, identified sample: 29/78 winners were home (37.2%), 41 away (52.6%), and 8 neutral (10.3%). Excluding neutral games gives 29/70 = 41.4% home, still not a majority.

Google said 193/311 winners entered with higher YPC (62.1%). Our known-stat winner sample: 33/70 (47.1%) had higher raw offensive YPC, 37 had lower YPC; another 8 winners lacked usable earlier-week statistics. Importantly, among ALL underdogs with higher YPC the actual record is 33–29 (53.2%), versus 37–45 (45.1%) with lower YPC. A winner-only percentage is not predictive accuracy.

For the requested additional checks, 32/70 known-stat winners had lower defensive YPC allowed (45.7%). 34/70 had better turnover margin/game (48.6%); 32 worse and 4 tied. These winner-only counts should not replace the full records above. No completion percentage inference made.

## Interpretation

Home-field advantage alone did not identify more successful underdogs in this cohort: home 29–36 versus away 41–44. Higher offensive YPC shows a modest association: 53.2% versus 45.1%. Lower defensive YPC allowed did not help: 46.4% versus 50.7% for worse run defenses. Turnover margin shows the largest separation: better 61.8%, worse 40.0%; 2026 qualifying advantage sample is only three games.

Home + higher YPC: 11–8, not enough to establish a reliable edge. All four: 3–0, all from 2024–2025, with zero examples in 2026. Do not treat 3–0 as certainty. These retrospective, overlapping exploratory comparisons are not causal or untouched holdout validation. No production changes.

## Files and audit

game_details.csv provides every underdog, opponent, quoted price, result, pregame raw metric, sample size and source URL. records.csv includes annual and pooled full-cohort records; winner_characteristics.csv separately answers the Google winner-only questions. coverage.csv preserves excluded pricing cases. Profit: $10 ×100/abs(negative price), or $10 × positive price/100, for wins; −$10 for losses, rounded to cents per bet. No parlays or promos.
