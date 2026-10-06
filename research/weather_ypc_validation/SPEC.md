# Weather × rushing-efficiency validation — locked specification

## Question

In FBS-vs-FBS games played in inclement outdoor weather, how often did the team with:

1. higher pregame offensive rushing yards per carry win;
2. lower pregame defensive rushing yards per carry allowed win; and
3. both advantages win?

## Scope

- 2024 regular season.
- 2025 regular season.
- 2026 regular season through Week 5.
- FBS vs FBS only.
- Indoor venues excluded using ESPN venue metadata.
- Week 1 and any other game without complete earlier-week current-season FBS rushing histories are not used for YPC outcome rates.

## Pregame metrics

Use the same raw rushing profiles already implemented in matchup_advantages.build_waterfall_profiles:

- Offensive YPC = prior current-season FBS rushing yards / rushing attempts.
- Defensive YPC allowed = prior opponents' current-season FBS rushing yards / rushing attempts against the team.
- Only completed games from earlier weeks and before the target kickoff count.
- No prior-season fallback.
- Metric ties produce no selection for that metric.
- "Both" requires one team to have both higher offensive YPC and lower defensive YPC allowed.

## Weather source and game window

- ESPN venue metadata supplies venue address and indoor/outdoor status.
- Open-Meteo Historical Weather supplies hourly precipitation, snowfall, wind speed, wind gusts and WMO weather code.
- Venue city/postal coordinates are resolved through Open-Meteo geocoding.
- Weather window = the kickoff hour through four hours after kickoff.

## Inclement-weather definition

A game is inclement if the outdoor game window meets at least one condition:

- total precipitation >= 1.0 mm; OR
- any snowfall > 0; OR
- maximum sustained 10 m wind >= 20 mph; OR
- maximum 10 m wind gust >= 30 mph; OR
- thunderstorm weather code 95, 96 or 99 occurs.

Weather categories are also retained as wet/snow only, wind only, or both wet/snow and wind.

These thresholds are fixed before outcome analysis.

## Comparisons

Report:

- overall inclement record and win rate for each YPC signal;
- ordinary-weather outdoor control record;
- difference in win rate;
- season splits;
- weather-type splits;
- P4/P4 and G6/G6 splits where sample permits;
- sample/coverage counts and unresolved venues/weather.

No production changes are authorized by this test.
