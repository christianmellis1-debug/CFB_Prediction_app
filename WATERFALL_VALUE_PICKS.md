# Value Picks waterfall v2 — 6/6 ATS first

The production Value Picks layer now starts with **exact 6/6 ATS Dominance** and keeps the prior moneyline waterfall underneath it. The core V1.5 winner model is unchanged.

## Stage 1 — exact 6/6 ATS Dominance

A game qualifies when the **home team** owns all five pregame statistical advantages and also owns home field:

1. Better rushing matchup estimate
2. Better completion matchup estimate
3. Lower defensive rushing yards per carry allowed
4. Lower defensive completion percentage allowed
5. Better turnover margin per game
6. Home-field advantage

The statistical comparison uses only completed, earlier-week, current-season FBS games available before kickoff. Ties do not count as advantages. The comparison applies only to P4-vs-P4 and G6-vs-G6 games; Notre Dame is treated as P4. Neutral-site games cannot be 6/6.

The sportsbook spread does **not** determine whether a team is 6/6. A spread is required only to publish an actionable ATS selection.

### Stage 1 ranking bands

- **Prime 6/6**: spread from -7 through -13.5
- **Standard 6/6**: short favorite, greater than -7 through pick'em
- **6/6 Market Disagreement**: the 6/6 home team is an underdog
- **6/6 Heavy Favorite**: more than -13.5

Every exact 6/6 qualifier remains eligible. These bands rank the selections; they do not weaken or strengthen the statistical gate.

## Lower waterfall stages

If Stage 1 produces fewer than the target card size of 12, the existing moneyline rules fill toward 12:

2. **Gold Standard Underdog**: DraftKings +100 through +170 with the existing rushing/turnover sweep rules.
3. **Moneyline Parlay Anchor**: DraftKings -600 through -280, core model selects the favorite at 70%+, with the existing defensive rushing and turnover gates.
4. **Moderate Favorite Clear**: DraftKings -275 through -205 with both rushing gates and the better turnover margin.

The card remains capped at 18. Gates are never relaxed merely to hit the target.

## Spread support

The ESPN sportsbook payload supplies side-specific point-spread values, opening spreads, and spread prices. DraftKings is preferred; another sportsbook may be used as a clearly labeled fallback when DraftKings is unavailable.

The Streamlit app and API now retain both markets simultaneously:

- Home / away moneyline
- Home / away spread
- Spread price
- Moneyline source
- Spread source
- Opening spread when supplied by the feed

Game cards and the comparison table show spreads alongside moneylines. Stage 1 displays the selected spread and sportsbook source.

## Grading

Moneyline tiers continue to grade the selected straight-up winner.

Stage 1 grades ATS from the selected side's final scoring margin plus its stored/displayed spread:

- Positive adjusted margin: **Correct**
- Negative adjusted margin: **Incorrect**
- Zero adjusted margin: **Push**

Pushes are excluded from win/loss accuracy.

## Historical and prospective interpretation

The 2026 research sample that motivated Stage 1 produced 12-2 straight-up and 10-4 ATS across the first 14 exact 6/6 qualifiers. That is promising but remains a small sample and is not a guarantee of future performance.

Historical cards in the live app are recalculated from archived/currently retrievable source data. They are not immutable proof of a line captured before kickoff unless a separate frozen snapshot exists.

## Implementation points

- matchup_advantages.py: exact 6/6 selection, ranking bands, and lower waterfall rules.
- model_v1_5.py: combines the six-metric checks with the waterfall and grades spread selections ATS.
- app.py: parses and displays spreads, passes spread prices into Value Picks, and supports ATS settlement in scenarios.
- backend/main.py: exposes the same spread fields to API consumers.
- tests/test_waterfall.py: validates all four stages, Stage 1 ranking, missing-line behavior, ATS covers/pushes, spread parsing, API spread fields, and scenario settlement.

Validation on the feature branch: **31 unit/integration tests passed**, and Python syntax compilation passed for the production modules.
