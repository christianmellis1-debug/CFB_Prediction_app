# Saturday Forecast — Test F: Real rushing and passing efficiency matchups

**Completed October 13, 2026 (Central). Research only; production V1.5, Test C blend, six independent betting tiers unchanged.**

## Purpose and data

Test whether actual opponent-specific run and pass efficiency provides incremental information beyond V1.5 and the current **16.927926947% V1.5 / 83.072073053% sportsbook market Test C**.

All opponent profiles use only completed **earlier-week FBS-vs-FBS games** played before the target matchup's kickoff, matched by both teams' ESPN box-score IDs. Game-level raw metrics: rushing yards and carries, passing **net** yards, completions and attempts. Prior opponent allowed rates represent defensive performance.

For each matchup, estimated home rushing YPC = (home own offensive YPC + away own defensive YPC allowed) / 2. Away estimate reverses sides. The difference, home minus away, is the additional *run* signal. Similarly compute offense passing completion % versus defensive completion % allowed, and **net passing yards per attempt (YPA)** versus YPA allowed. Per-game raw yards and attempts are **pooled across all usable earlier FBS box scores** to avoid game-size weighting errors. All three estimates require valid two-sided paired team boxes; missing histories are *not* filled with guessed averages.

**Actual pressure and pass blocking could not be tested:** the accessible ESPN team-box CSV has no reliable sacks/pressure/pass-blocking columns. None were fabricated or relabeled.

Historical matched cohort, each model evaluated on exactly the same market-quoted game IDs:
- 2024: **717 FBS games**, archived ESPN BET opening odds, reconstructed current V1.5.
- 2025: **720 FBS games**, archived ESPN BET opening odds, reconstructed current V1.5.
- 2026 Weeks 3–6: **221 FBS games**, archived DraftKings opening odds. Week 3–4 V1.5 reconstructed; Week 5–6 (112 games) V1.5 source is the genuine locked pregame model prediction. The challenger correction remains **retrospectively reconstructed**, and the archive opening quote is not necessarily the same captured originally in the app's forward tracker.

In current V1.5 prediction cohorts, **645/717** (2024), **649/720** (2025), and **220/221** (2026) had both teams' usable prior FBS offensive and defensive box histories. Unqualified games continue using the original forecast.

## Part 1: Add matchup information inside independent V1.5, then apply locked Test C blend

Compute standardized independent signals using **fixed interpretable scales**, no response-year refit: rushing YPC difference / 2, completion probability difference / 0.15, and YPA difference / 3, clipped to ±3. Then:

`P_new_v15 = logistic(logit(P_original_v15) + beta × signal)`

`P_new_TestC = 0.16927926947215113 × P_new_v15 + 0.8307207305278489 × P_market`

For each family (run YPC, completion %, pass YPA, run+completion, run+YPA, all three) screen 4 minimum prior-FBS game requirements × 8 coefficients (**192 variants total**), select the smallest Brier in 2024 and test the frozen same choice in 2025 and 2026.

### Results on identical priced games, final Test C winners

| 2024-selected football feature | 2024 W–L / 717 | 2025 W–L / 720 | 2026 W3–6 / 221 | 2026 frozen W5–6 / 112 |
|---|---:|---:|---:|---:|
| **Official Test C baseline** | **509–208** | **527–193** | **169–52** | **78–34** |
| Run YPC versus run defense | 505–212 | 524–196 | 167–54 | 76–36 |
| Passing completion versus completion allowed | 509–208 | 526–194 | 168–53 | 76–36 |
| **Passing net YPA versus YPA allowed** | **510–207** | **529–191** | 168–53 | 77–35 |
| Combined rushing + completions | 508–209 | 528–192 | 169–52 | 77–35 |
| Combined rushing + YPA | 507–210 | **530–190** | 167–54 | 76–36 |
| All three together | 509–208 | 527–193 | **170–51** | **78–34** |

No family selected in 2024 improved the *win count* on **every** subsequent check when its new statistic is added **inside V1.5**. The YPA-only candidate gave +1 in 2024, +2 in 2025 and −1 in 2026; although Brier improved slightly across all three (and on the 2026 frozen cohort), the additional 2026 winner error makes it uncertain. The combined three-signal candidate added +1 in 2026 W3–6 but did not improve 2024 or 2025 winner counts and had inconsistent Brier.

**Independent V1.5:** a few candidates increase independent winner accuracy, but effects remain inconsistent by year and are generally diluted because it receives only ~17% weight in Test C.

## Part 2: Add a small *direct* passing matchup correction to final Test C

The football signal is a separate, independent predictor; adding it only inside V1.5 may dilute it unnecessarily. A direct residual experiment therefore used:

`P_candidate = logistic(logit(P_original_TestC) + beta × clip[(estimated_home_net_YPA − estimated_away_net_YPA)/3, −3, +3])`.

If either team's earlier FBS box history is unavailable, **unchanged original Test C** is returned. All Test C original coefficients and bookmaker inputs remain untouched; this is an *additional* matchup residual, not a reoptimized sportsbook blend or a claim of betting value.

Six signal families × four minimum-game filters × 13 fixed residual coefficients (including 0) = **312 hypotheses**. Choose one per family by minimum 2024 Brier; apply unchanged on 2025 and 2026. This was independently executed and reproducibly validated.

### Main result — passing YPA residual chosen on 2024 alone

Selected rule: both teams have at least **one previous matched FBS game**; **beta = +0.10** in log odds; YPA differential scaled by 3 and clipped to ±3.

| Cohort | Official Test C | Test C + passing YPA | Extra winners | Brier baseline → candidate |
|---|---:|---:|---:|---:|
| 2024 | 509–208 | **511–206** | +2 | 0.1834894 → **0.1833969** |
| 2025 | 527–193 | **529–191** | +2 | 0.1822763 → **0.1822193** |
| 2026 Weeks 3–6 | 169–52 | **170–51** | +1 | 0.1701468 → **0.1699793** |
| 2026 frozen original V1.5, W5–6 | 78–34 | 78–34 | 0 | 0.1978725 → **0.1974862** |

**Total:** across the three main season/window cohorts, 17 predictions switch winners: **11 original mistakes corrected and 6 original correct predictions turned wrong**, a net **five extra correct selections** on **1,658** matched games. Two-sided exact paired binomial test **p ≈ 0.332**; this small number of altered winners is **not statistical proof** of prospective superiority. Brier gains range ~0.000057 to ~0.000168 for the full cohorts, which are positive but small.

### What changed in 2026?

The three winner changes all occurred in **retrospectively reconstructed Weeks 3–4**:

| Week | Game | Original Test C winner | YPA residual winner | Outcome |
|---|---|---|---|---|
| 3 | Florida at Auburn | Auburn | **Florida** | Fix: Florida won |
| 4 | Ole Miss at Florida | Ole Miss | **Florida** | Fix: Florida won |
| 4 | Oklahoma State at West Virginia | Oklahoma State | **West Virginia** | New error: Oklahoma State won |

The selected YPA residual **did not switch any winner in the frozen Week 5–6 2026 games**; Brier alone improved. This distinction matters when interpreting the apparent 2026 winner improvement.

### Other direct-residual families (2024-selected each)

| Signal | Change in correct winners: 2024 | 2025 | 2026 W3–6 |
|---|---:|---:|---:|
| Rushing YPC | −2 | −2 | 0 |
| Passing completion % | −2 | −4 | −6 |
| **Passing YPA** | **+2** | **+2** | **+1** |
| Rushing + completion | −1 | +1 | −2 |
| Rushing + YPA | −3 | 0 | −3 |
| All three | 0 | 0 | 0 |

The passing YPA residual is the **only 2024-selected direct adjustment that has positive winner improvements in all three main cohorts, and positive Brier gains in all three**. But because six families and hundreds of coefficients were screened, this result must not be mistaken for a pristine discovery.

## Decision

**Keep production Test C unchanged today. Promote the direct +0.10 passing YPA residual as the leading research-only Test F challenger.** It is a new, genuinely football-specific signal with consistent *historical* directional improvements, unlike Test E's attempts simply to juggle existing composite weights. The gains are nevertheless small, source vintages are retrospective, the model itself has previously used 2025 for related tuning, and the apparent 2026 extra correct winner occurred only in reconstructed—not truly frozen original—weeks.

A better proof would be a new immutable pregame capture of: eligible FBS historical box samples, estimated home/away passing YPA, original Test C probability, adjusted probability, prediction side, sportsbook source/time, and postgame score. Assess a **meaningful new future cohort** without changing beta, eligibility or scoring after outcomes arrive. Also check whether passing net YPA information is already reflected in available EPA metrics, and whether independent pregame pressure stats add *additional* predictive signal without source leakage.

**Do not silently use a market-heavy probability as an independent betting edge against the same bookmaker. Do not modify the six waterfall tiers from a straight-up predictor experiment.**

## Reproduce

- `research/test_f_rush_pass_matchups.py` — downloads ESPN team-box records, joins each previous FBS game with both teams' box scores, creates FBS-only offensive and opposing defensive profiles, and evaluates 192 alternatives through the unchanged Test C blend.
- `research/test_f_matchups_results.json`, `research/test_f_matchups_games.csv` — detailed candidate scoreboards and full game-level features.
- `research/test_f_direct_residual.py` — evaluates 312 direct blended-log-odds residual configurations and fixes the same pass-YPA candidate from 2024 Brier.
- `research/test_f_direct_residual_results.json`, `research/test_f_direct_changed_games.csv` — complete alternative/paired outcomes and exact switched games.
- `.github/workflows/test-f-rush-pass.yml`, `.github/workflows/test-f-direct-residual.yml` — completed successful reproducible isolated research actions.
- `.github/workflows/test-f-inspect-source.yml` — source-column audit confirming **no direct pass pressure / sack field** in the available team boxes.

**Production app, V1.5 weights, Test C blend coefficient and six tier rules untouched.**
