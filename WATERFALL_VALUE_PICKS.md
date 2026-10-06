# Value Picks waterfall v3 — ATS-first selection

The production Value Picks layer now begins with two explicit ATS tiers. The core V1.5 winner model is unchanged.

## Tier 1 — exact 6/6 ATS Dominance

A game qualifies when the **home team** owns all five pregame statistical advantages and also owns home field:

1. Better rushing matchup estimate
2. Better completion matchup estimate
3. Lower defensive rushing yards per carry allowed
4. Lower defensive completion percentage allowed
5. Better turnover margin per game
6. Home-field advantage

The statistical comparison uses only completed, earlier-week, current-season FBS games available before kickoff. Ties do not count as advantages. Tier 1 applies only to P4-vs-P4 and G6-vs-G6 games; Notre Dame is treated as P4. Neutral-site games cannot be 6/6.

The sportsbook spread does **not** determine whether a team is 6/6. A spread is required to publish the actionable ATS selection.

### Tier 1 ranking bands

- **Prime 6/6**: spread from -7 through -13.5
- **Standard 6/6**: greater than -7 through pick'em
- **6/6 Market Disagreement**: the 6/6 home team is an underdog
- **6/6 Heavy Favorite**: more negative than -13.5

All exact 6/6 qualifiers remain eligible.

## Tier 2 — Weather Defensive Edge ATS

Tier 2 is a **spread recommendation**, not a generic winner or moneyline recommendation.

The app publishes the **home team against the displayed spread** only when every condition is true:

1. The game is non-neutral and outdoors.
2. Verified game-window weather is inclement.
3. The home team has the lower pregame defensive rushing YPC allowed.
4. The home team has the better pregame turnover margin per FBS game.
5. The home spread is available and is **better than -14** (strictly greater than -14).

A qualifying display is explicit, for example: **Tennessee -6 ATS**.

### Locked weather definition

The weather window is the kickoff hour through four hours after kickoff. A game is inclement when at least one condition occurs:

- Total precipitation >= 1.0 mm
- Any snowfall
- Sustained 10 m wind >= 20 mph
- 10 m wind gust >= 30 mph
- Thunderstorm WMO code 95, 96, or 99

ESPN venue metadata supplies indoor/outdoor status and venue location. Open-Meteo supplies hourly historical-forecast or forecast conditions. Missing venue, weather, or spread data fails closed: the game is not published as Tier 2.

### Tier 2 research basis

The frozen football rule (weather + home + better run defense + better turnover margin) identified 29 historical games across 2024, 2025, and 2026 through Week 5:

- Straight-up: **26-3 (89.7%)**
- ATS across all 29: **19-9-1 (67.9% excluding the push)**

Market-bucket analysis then showed a large difference by spread:

- Spread better than -14: **12-2-1 ATS (85.7% excluding the push)**
- Favorite -14 or more: **7-7 ATS**

The -14 exclusion was adopted after this market-bucket analysis, so the resulting 12-2-1 subgroup is **post-hoc and must be tracked prospectively**. The app should not present 85.7% as an expected future accuracy rate.

## Lower waterfall tiers

If Tiers 1 and 2 produce fewer than the target card size of 12, the existing moneyline rules fill toward 12:

3. **Gold Standard Underdog**: DraftKings +100 through +170 with the existing rushing/turnover sweep rules.
4. **Moneyline Parlay Anchor**: DraftKings -600 through -280, core model selects the favorite at 70%+, with the existing defensive rushing and turnover gates.
5. **Moderate Favorite Clear**: DraftKings -275 through -205 with both rushing gates and the better turnover margin.

The card remains capped at 18. Gates are never relaxed merely to hit the target.

## Market display and grading

The Streamlit app shows an explicit **Recommended Bet** for each selected game.

Spread tiers are displayed as the selected team plus its exact spread and ATS. Moneyline tiers are displayed as the selected team plus ML and the selected price.

Spread tiers grade from the selected side's final scoring margin plus its stored/displayed spread:

- Positive adjusted margin: **Correct**
- Negative adjusted margin: **Incorrect**
- Zero adjusted margin: **Push**

Pushes are excluded from win/loss accuracy. Moneyline tiers continue to grade the selected straight-up winner.

## Implementation points

- **weather_context.py**: ESPN venue lookup, Open-Meteo game-window weather, and the locked inclement thresholds.
- **matchup_advantages.py**: Tier 1 and Tier 2 qualification, five-stage priority, and lower moneyline rules.
- **model_v1_5.py**: waterfall annotation and market-aware grading.
- **app.py**: candidate-only cached weather lookup and explicit Recommended Bet display.
- **backend/main.py**: same Tier 2 weather context for API output.
- **tests/test_waterfall.py**: five-stage priority, Tier 2 weather/spread gates, candidate prefilter, and ATS grading.

Feature-branch validation: **34 repository tests passed**, production modules compiled successfully, a known 2026 historical inclement game reproduced the researched weather classification, and a Week 6 outdoor game returned live forecast context successfully.
