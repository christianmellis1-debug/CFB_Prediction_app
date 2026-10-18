# Saturday Forecast moneyline audit — matchup-advantage candidates
Date: 2026-10-18. Research only; no production app changes.

## Objective and methodology
Evaluate whether the prior research ATS candidates have **positive straight-up moneyline return** rather than only covering the point spread:
1. Home team with better run-defense YPC allowed **and** higher turnover margin per earlier-week FBS game (pair).
2. Pair + home underdog (positive market home spread).
3. Pair + exactly 3 of Saturday Forecast's 5 binary advantages (all spreads).
4. Pair + exactly 3 of 5 + home underdog.
5. Pair + all 5 advantages (existing 6/6 Tier1 home-team scenario).
6. Price categories of pair favorites and underdogs.

Reconstructed flags with production `build_advantages` and `assess`, using exclusively earlier-week FBS box-score data. Only same-group P4/P4 or G6/G6 games at nonneutral sites. Team's *outright home win* determined from final scores. Historical quoted home/away American moneylines sourced from sportsdataverse's `cfbfastR-cfb-raw` per-game betting JSON, selecting ESPN BET in 2024–2025 and DraftKings in 2026, first valid two-sided quotes, checking sum of implied probabilities in [0.99,1.35]. For consistency, no prices inferred from spreads. All moneyline numbers are archival snapshots; **we cannot verify their availability at the actual pregame decision point, or whether opening, live, revised, or closing odds apply to all sources**. Actual results are not actual placed bets.

Simulate a flat **$10 risk per wager**, return profit +$10 × (American ML /100) when positive, or +$10 × (100 / abs(American ML)) when negative, and -$10 for a loss. At -110, win profit $9.09. Missing prices excluded from ROI calculations, but included in unpriced straight-up record. All games from 2026 are through Week 7 only. The post-hoc cohort search creates material multiple-testing/data-mining risk.

Fetched 402 pair games; archived moneyline coverage **391/402 (97.3%)**. No fetch failures, 11 games had no valid two-sided designated provider odds.

## Moneyline win rates and hypothetical returns

| Predefined research cohort | All SU W-L | ML-priced games | Priced SU W-L | Median home ML | Hypothetical -$10 stake per match ROI | Hypothetical profit |
|---|---:|---:|---:|---:|---:|---:|
| Pair, all home teams | 295-107 (73.4%) | 391 | 285-106 (72.9%) | -320 | **-0.36%** | -$14.06 |
| Pair, home underdog | 25-33 (43.1%) | 57/58 | 25-32 (43.9%) | +125 | **+6.19%** | +$35.27 |
| Pair, all home favorites | 270-74 (78.5%) | 334/344 | 260-74 (77.8%) | -400 | **-1.48%** | -$49.33 |
| Pair + exactly 3/5 advantages | 68-23 (74.7%) | 91/91 | 68-23 (74.7%) | -210 | **+16.87%** | +$153.50 |
| Pair + exactly 3/5 + home dog | 13-13 (50.0%) | 26/26 | 13-13 (50.0%) | +167 | **+24.90%** | +$64.74 |
| Pair + all 5 (Tier1 6/6) | 154-38 (80.2%) | 182/192 | 144-38 (79.1%) | -600 | **-2.52%** | -$45.95 |
| Pair + 4/5 | 63-40 (61.2%) | 102/103 | 63-39 (61.8%) | -255 | **-15.12%** | -$154.21 |
| Pair + favored by 14+ | 134-10 (93.1%) | 134/144 | 124-10 (92.5%) | -1400 | -0.17% | -$2.29 |
| Pair + favored by 7–13.5 | 68-21 (76.4%) | 89/89 | 68-21 (76.4%) | -360 | -2.75% | -$24.45 |
| Pair + favored by up to 6.5 | 68-43 (61.3%) | 111/111 | 68-43 (61.3%) | -165 | -2.04% | -$22.59 |

**Crucial:** A home underdog with the two flags covered **37-20-1 ATS**, but only won outright **25-33** (25-32 on 57 priced games). Winning while priced at plus-money can make money despite losing more matches, but volatility is very high.

## Annual moneyline ROI: wins are not the same as value

| Cohort | 2024 priced W-L / ROI | 2025 priced W-L / ROI | 2026 through W7 priced W-L / ROI |
|---|---|---|---|
| Pair all | 130-37 / +6.37% | 111-47 / **-3.27%** | 44-22 / **-10.41%** |
| Pair + home dog | 10-10 / +24.10% | 12-14 / +10.21% | **3-8 / -35.89%** |
| Pair + exactly 3/5 | 34-4 / +39.95% | 24-13 / +1.05% | 10-6 / -1.37% |
| Pair + exactly 3/5 + dog | 5-2 / +89.57% | 5-7 / +1.27% | 3-4 / +0.75% |
| Pair + all 5 | 64-16 / -1.41% | 58-13 / +0.20% | 22-9 / -11.63% |

Median home moneyline for pair home dogs +125. Their mean available sportsbook raw implied home win probability was **41.18%** (no-vig normalization 39.53%); actual priced outright wins 25/57 = 43.86%. The observed sample outperforming fair market probability by ~4.3 points is too thin to establish true edge, and 2026 performs much worse. Median for pair+3/5 all lines -210; 2024 34-4/89.5% dwarfed price expectations (mean book implied ~68.7%) and drove almost all the pooled ROI. 2025 and 2026 basically broke even or lost.

Pooled home underdog price buckets (post-hoc exploration; very small samples, not deployable):
- +100 to +150: 12-16, -8.2% ROI (28 priced)
- +151 to +250: 8-9, +36.5% ROI (17 priced); 2024 3-0, 2025 4-6, 2026 1-3
- above +250: 1-5, -35% ROI (6 priced)
- six home underdogs according to spread nevertheless had negative moneyline prices in the archived feeds, consistent with different snapshots/close-run divergence. Avoid claiming spreads and ML are synchronized.

## Conclusion and deployment decision

The home underdog + run-defense+turnover flag **could offer real plus-money upset opportunities**, but is not sufficiently validated: full-sample home underdog ML ROI +6.2% on 57 priced games, and 2026 -35.9% on 11 priced games. Pair+3/5 16.9% ROI is largely one anomalous 2024 season (34-4 SU; 2025 +1%, 2026 -1%). Heavy favorites and 6/6 winning ~80-93% do not translate into profitable moneyline bets. **No rule should be promoted to official picks or parlay legs yet.** The strongest next prospective shadow-moneyline candidate is home dogs with both flags; record odds from the same available bookmaker before kickoff, with fair-market probabilities, win rate, and flat-stake P/L. A second tentative comparator is pair+exactly3/5; its striking 2024 win rate must replicate in untouched future seasons.

Test implementation `tests/test_candidate_moneylines_2026_10_18.py`, runner GitHub Actions #39148213858. The standalone audit passes; the broader app regression suite includes unrelated stale UI assertions. PR intentionally not merged into production.
