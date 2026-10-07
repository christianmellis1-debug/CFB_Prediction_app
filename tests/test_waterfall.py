import unittest
import math
import pandas as pd
from matchup_advantages import (build_waterfall_profiles, build_tier5_four_factor, select_waterfall,
                                normalize_fbs_schedule, weather_tier_candidate_ids, cross_tier_matches)
from model_v1_5 import add_waterfall_value, waterfall_scenario_rows


class WaterfallTests(unittest.TestCase):
    def six_check(self, exact=True):
        if exact:
            return {
                'status': 'ok',
                'home': [6.0, .70, 3.0, .55, 1.0],
                'away': [4.0, .60, 5.0, .65, 0.0],
                'home_games': 2, 'away_games': 2, 'group': 'P4',
            }
        return {
            'status': 'ok',
            'home': [4.0, .58, 5.0, .65, 0.0],
            'away': [5.0, .64, 4.0, .58, 1.0],
            'home_games': 2, 'away_games': 2, 'group': 'P4',
        }

    def fixture(self, stage=1, gid=1):
        g = dict(
            game_id=gid, season=2026, week=3, season_type='regular',
            home_id=10, away_id=20, home_team='Home', away_team='Away',
            home_division='fbs', away_division='fbs',
            home_conference='ACC', away_conference='ACC',
            neutral_site=False, completed=False,
            home_points=None, away_points=None,
            start_date='2026-09-19T12:00:00Z',
        )
        p = {
            'Game ID': gid, 'DK Home ML': '+120', 'DK Away ML': '-140',
            'Home Spread': '-9.5', 'Away Spread': '+9.5',
            'Home Spread Odds': '-110', 'Away Spread Odds': '-110',
            'Spread Source': 'Draft Kings',
            'Predicted Winner': 'Away', 'Confidence': .75,
        }
        rec = {
            'status': 'ok',
            'home': dict(off_run=6, def_run=3, margin=1, games=2),
            'away': dict(off_run=4, def_run=5, margin=0, games=2),
        }
        check = self.six_check(stage == 1)
        if stage == 4:
            g.update(week=4, start_date='2026-09-26T12:00:00Z')
            p.update({'DK Home ML': '-600', 'DK Away ML': '+425', 'Predicted Winner': 'Away'})
        elif stage == 5:
            p.update({'DK Home ML': '-250', 'DK Away ML': '+220', 'Predicted Winner': 'Home'})
        elif stage == 3:
            p.update({'Home Spread': 'Unavailable', 'Away Spread': 'Unavailable'})
        return g, p, rec, check

    def select(self, g, p, r, check=None, weather=None, tier5=None, **kw):
        checks = {str(g['game_id']): check or self.six_check(False)}
        weather_checks = {str(g['game_id']): weather} if weather else {}
        tier5_checks = {str(g['game_id']): tier5} if tier5 else {}
        return select_waterfall(
            pd.DataFrame([p]), pd.DataFrame([g]), {str(g['game_id']): r},
            advantage_checks=checks, weather_checks=weather_checks,
            tier5_checks=tier5_checks, **kw)

    def test_five_stages(self):
        for stage in (1, 2, 3, 4, 5):
            g, p, r, check = self.fixture(stage)
            weather = {'status': 'ok', 'inclement': True, 'weather_type': 'Wet/snow only'} if stage == 2 else None
            tier5 = {'status': 'ok', 'qualifies': True, 'through_week': 2} if stage == 5 else None
            card = self.select(g, p, r, check, weather=weather, tier5=tier5)
            self.assertEqual(card[0]['Value Stage'], stage)
        g, p, r, check = self.fixture(1)
        self.assertEqual(self.select(g, p, r, check)[0]['Value Market'], 'Spread')

    def test_weather_tier_requires_locked_ats_gates(self):
        g, p, r, check = self.fixture(2)
        weather = {'status': 'ok', 'inclement': True, 'weather_type': 'Wind only'}
        card = self.select(g, p, r, check, weather=weather)
        self.assertEqual(card[0]['Value Stage'], 2)
        self.assertEqual(card[0]['Value Market'], 'Spread')
        self.assertEqual(card[0]['Value Pick'], 'Home')
        self.assertEqual(card[0]['Value Line'], '-9.5')
        self.assertEqual(card[0]['Value Band'], 'Wind only')

        for mutate in ('ordinary', 'heavy', 'run_defense', 'turnover', 'neutral'):
            g2, p2, r2, check2 = self.fixture(2)
            w2 = dict(weather)
            if mutate == 'ordinary':
                w2['inclement'] = False
            elif mutate == 'heavy':
                p2['Home Spread'] = '-14'
            elif mutate == 'run_defense':
                r2['home']['def_run'] = r2['away']['def_run']
            elif mutate == 'turnover':
                r2['home']['margin'] = r2['away']['margin']
            elif mutate == 'neutral':
                g2['neutral_site'] = True
            card2 = self.select(g2, p2, r2, check2, weather=w2)
            self.assertFalse(card2 and card2[0]['Value Stage'] == 2, mutate)

    def test_weather_candidate_ids_apply_non_weather_gates(self):
        g, p, r, _ = self.fixture(2)
        ids = weather_tier_candidate_ids(pd.DataFrame([p]), pd.DataFrame([g]), {'1': r})
        self.assertEqual(ids, [1])
        p['Home Spread'] = '-14'
        self.assertEqual(weather_tier_candidate_ids(pd.DataFrame([p]), pd.DataFrame([g]), {'1': r}), [])


    def test_six_of_six_spread_bands_and_priority(self):
        spreads = [('-9.5', 'Prime 6/6'), ('-3.5', 'Standard 6/6'),
                   ('+2.5', '6/6 Market Disagreement'), ('-21.5', '6/6 Heavy Favorite')]
        games, preds, profiles, checks = [], [], {}, {}
        for gid, (spread, _) in enumerate(spreads, 1):
            g, p, r, check = self.fixture(1, gid)
            p['Home Spread'] = spread
            games.append(g); preds.append(p); profiles[str(gid)] = r; checks[str(gid)] = check
        card = select_waterfall(pd.DataFrame(preds[::-1]), pd.DataFrame(games), profiles, advantage_checks=checks)
        self.assertEqual([x['Value Band'] for x in card], [x[1] for x in spreads])
        self.assertTrue(all(x['Value Market'] == 'Spread' for x in card))

    def test_six_of_six_requires_actionable_spread_and_home_field(self):
        g, p, r, check = self.fixture(1)
        p.update({'Home Spread': 'Unavailable', 'DK Home ML': 'Unavailable', 'DK Away ML': 'Unavailable'})
        self.assertEqual(self.select(g, p, r, check), [])
        g, p, r, check = self.fixture(1)
        g['neutral_site'] = True
        p.update({'DK Home ML': 'Unavailable', 'DK Away ML': 'Unavailable'})
        self.assertEqual(self.select(g, p, r, check), [])
        g, p, r, check = self.fixture(1)
        check['home'][0] = check['away'][0]
        p.update({'DK Home ML': 'Unavailable', 'DK Away ML': 'Unavailable'})
        self.assertEqual(self.select(g, p, r, check), [])

    def test_moneyline_boundaries_remain(self):
        # Tier 3 is keyed to the favorite price, while Tiers 4/5 are selected favorites.
        for favorite_line in (-110, -150):
            g, p, r, check = self.fixture(3)
            p['DK Away ML'] = str(favorite_line)
            self.assertTrue(self.select(g, p, r, check), favorite_line)
        for favorite_line in (-109, -151):
            g, p, r, check = self.fixture(3)
            p['DK Away ML'] = str(favorite_line)
            self.assertFalse(self.select(g, p, r, check), favorite_line)

        specs = [
            (4, [-505, -600, -1000], [-504, -1001]),
        ]
        for stage, good, bad in specs:
            for line in good + bad:
                g, p, r, check = self.fixture(stage)
                p['DK Home ML'] = str(line)
                self.assertEqual(bool(self.select(g, p, r, check)), line in good, (stage, line))

    def test_tier3_requires_p4_and_turnover_edge_at_least_one(self):
        g, p, r, check = self.fixture(3)
        card = self.select(g, p, r, check)
        self.assertEqual(card[0]['Value Stage'], 3)
        self.assertEqual(card[0]['Value Market'], 'Moneyline')
        self.assertEqual(card[0]['Value Pick'], 'Home')
        self.assertEqual(card[0]['Value Line'], '+120')
        self.assertIn('turnover margin/game edge +1.00', card[0]['Value Reason'])

        # The strong-turnover threshold is inclusive at +1.0 and fails below it.
        r2 = {**r, 'home': dict(r['home']), 'away': dict(r['away'])}
        r2['home']['margin'] = 0.99
        r2['away']['margin'] = 0.0
        self.assertFalse(self.select(g, p, r2, check))

        # Both teams must be P4; Notre Dame remains P4 through conference_group().
        g2 = dict(g)
        g2['home_conference'] = 'Mountain West'
        self.assertFalse(self.select(g2, p, r, check))

        # Neutral-site P4 games remain eligible; venue was not a gate in the validated rule.
        g3 = dict(g)
        g3['neutral_site'] = True
        self.assertTrue(self.select(g3, p, r, check))

    def test_tier4_is_week4_plus_price_only_straight_up(self):
        g, p, r, check = self.fixture(4)
        # Model disagreement and missing profile data do not block Tier 4.
        p.update({'Predicted Winner': 'Away', 'Confidence': .51})
        r = {'status': 'missing'}
        card = self.select(g, p, r, check)
        self.assertEqual(card[0]['Value Stage'], 4)
        self.assertEqual(card[0]['ValuePick'] if 'ValuePick' in card[0] else card[0]['Value Pick'], 'Home')
        self.assertEqual(card[0]['Value Market'], 'Moneyline')
        self.assertEqual(card[0]['Value Band'], 'Straight Up')

        # Week 3 does not qualify even at an eligible price.
        g2, p2, r2, check2 = self.fixture(4)
        g2.update(week=3, start_date='2026-09-19T12:00:00Z')
        self.assertFalse(self.select(g2, p2, {'status': 'missing'}, check2))

        # FCS opponents are outside Tier 4.
        g3, p3, r3, check3 = self.fixture(4)
        g3['away_division'] = 'fcs'
        self.assertFalse(self.select(g3, p3, {'status': 'missing'}, check3))

    def test_missing_fcs_and_bad_profiles_fail_closed(self):
        g, p, r, check = self.fixture(1)
        g['away_division'] = 'fcs'
        self.assertFalse(self.select(g, p, r, check))
        g, p, r, check = self.fixture(3)
        r['home']['margin'] = float('nan')
        self.assertFalse(self.select(g, p, r, check))

    def test_cross_tier_game_of_week_requires_same_team_consensus(self):
        g, p, r, check = self.fixture(4)
        p.update({
            'DK Home ML': '-600', 'DK Away ML': '+425',
            'Home Spread': '-9.5', 'Away Spread': '+9.5',
        })
        exact = self.six_check(True)
        tier5 = {'1': {'status': 'ok', 'qualifies': True, 'through_week': 3}}
        overlap = cross_tier_matches(
            pd.DataFrame([p]), pd.DataFrame([g]), {'1': r},
            advantage_checks={'1': exact}, tier5_checks=tier5,
        )['1']
        self.assertTrue(overlap['qualifies'])
        self.assertEqual(overlap['team'], 'Home')
        self.assertEqual(overlap['stages'], [1, 4, 5])
        self.assertEqual(overlap['count'], 3)

        # Two tiers pointing at opposite teams are not a Game of the Week.
        g2, p2, r2, _ = self.fixture(3, gid=2)
        g2['week'] = 4
        p2.update({'DK Home ML': '-140', 'DK Away ML': '+120',
                   'Home Spread': 'Unavailable', 'Away Spread': 'Unavailable'})
        r2['away']['margin'] = 2.0
        r2['home']['margin'] = 0.0
        conflict = cross_tier_matches(
            pd.DataFrame([p2]), pd.DataFrame([g2]), {'2': r2},
            advantage_checks={'2': self.six_check(False)},
            tier5_checks={'2': {'status': 'ok', 'qualifies': True, 'through_week': 3}},
        )['2']
        self.assertFalse(conflict['qualifies'])

    def test_waterfall_volume_guidance_does_not_hide_qualifiers(self):
        cases = [
            ((20, 20, 20, 20, 20), (20, 20, 20, 20, 20)),
            ((13, 20, 20, 20, 20), (13, 20, 20, 20, 20)),
            ((4, 20, 20, 20, 20), (4, 20, 20, 20, 20)),
            ((4, 3, 20, 20, 20), (4, 3, 20, 20, 20)),
            ((4, 3, 2, 20, 20), (4, 3, 2, 20, 20)),
            ((4, 3, 2, 1, 20), (4, 3, 2, 1, 20)),
        ]
        for sizes, expected in cases:
            games, pred, profiles, checks, weather_ids = [], [], {}, {}, []
            gid = 0
            for stage, n in enumerate(sizes, 1):
                for _ in range(n):
                    gid += 1
                    g, p, r, check = self.fixture(stage, gid)
                    games.append(g); pred.append(p); profiles[str(gid)] = r; checks[str(gid)] = check
                    if stage == 2:
                        weather_ids.append(str(gid))
            weather_checks = {gid: {'status': 'ok', 'inclement': True, 'weather_type': 'Wet/snow only'}
                              for gid in weather_ids}
            tier5_checks = {}
            offset = sum(sizes[:4])
            for game in games[offset:offset + sizes[4]]:
                tier5_checks[str(game['game_id'])] = {'status': 'ok', 'qualifies': True, 'through_week': 2}
            card = select_waterfall(pd.DataFrame(pred[::-1]), pd.DataFrame(games), profiles,
                                    advantage_checks=checks, weather_checks=weather_checks,
                                    tier5_checks=tier5_checks)
            self.assertEqual(tuple(sum(x['Value Stage'] == i for x in card) for i in (1, 2, 3, 4, 5)), expected)
            self.assertEqual(len({x['Game ID'] for x in card}), len(card))

    def history(self, final=False, home_points=30, away_points=20):
        g, _, _, _ = self.fixture()
        g.update(game_id=3, week=3, completed=final,
                 home_points=home_points if final else None,
                 away_points=away_points if final else None)
        old = dict(g, game_id=1, week=1, start_date='2026-09-01T12:00:00Z',
                   completed=True, home_points=28, away_points=14)
        fcs = dict(old, game_id=2, week=2, away_id=30, away_team='FCS',
                   away_division='fcs', away_conference='FCS')
        b = pd.DataFrame([
            dict(game_id=1, team_id=10, rushingYards=240, rushingAttempts=40,
                 completionAttempts='24-32', turnovers=0, fumblesLost=0, interceptions=0),
            dict(game_id=1, team_id=20, rushingYards=120, rushingAttempts=30,
                 completionAttempts='15-30', turnovers=2, fumblesLost=1, interceptions=1),
            dict(game_id=2, team_id=10, rushingYards=999, rushingAttempts=10,
                 completionAttempts='10-10', turnovers=0, fumblesLost=0, interceptions=0),
        ])
        return pd.DataFrame([old, fcs, g]), b

    def test_profiles_exclude_fcs_and_no_pass_dependency(self):
        s, b = self.history()
        r = build_waterfall_profiles(s, b, 3)['3']
        self.assertEqual(r['home'], dict(off_run=6, def_run=4, margin=2, games=1))

    def test_incomplete_history_fails_closed(self):
        s, b = self.history()
        for bad in [b.iloc[:1], pd.concat([b, b.iloc[:1]]), b.assign(turnovers=9), pd.DataFrame()]:
            self.assertNotEqual(build_waterfall_profiles(s, bad, 3).get('3', {}).get('status'), 'ok')

    def test_no_future_same_week_or_other_season(self):
        s, b = self.history()
        for col, value in [('season', 2025), ('week', 3), ('start_date', '2026-09-20T12:00:00Z')]:
            changed = s.copy(); changed.loc[0, col] = value
            self.assertEqual(build_waterfall_profiles(changed, b, 3)['3']['status'], 'missing')

    def test_sac_season_override(self):
        g, _, _, _ = self.fixture()
        g.update(home_team='Sacramento State', home_division='fcs')
        self.assertEqual(len(normalize_fbs_schedule(pd.DataFrame([g]))), 1)
        g.update(season=2025, home_division='fbs')
        self.assertTrue(normalize_fbs_schedule(pd.DataFrame([g])).empty)

    def test_official_tier5_uses_exact_prior_week_snapshot_and_strict_p4(self):
        g, _, _, _ = self.fixture(5)
        summaries = pd.DataFrame([
            dict(team_id=10, through_week=2, red_zone_success_off=.60, red_zone_success_def=.30,
                 explosive_off=.15, explosive_def=.07),
            dict(team_id=20, through_week=2, red_zone_success_off=.50, red_zone_success_def=.40,
                 explosive_off=.10, explosive_def=.09),
            # Better-looking current-week values must never be used for a Week 3 pick.
            dict(team_id=10, through_week=3, red_zone_success_off=.10, red_zone_success_def=.90,
                 explosive_off=.01, explosive_def=.30),
            dict(team_id=20, through_week=3, red_zone_success_off=.90, red_zone_success_def=.10,
                 explosive_off=.30, explosive_def=.01),
        ])
        check = build_tier5_four_factor(pd.DataFrame([g]), summaries, 3)['1']
        self.assertTrue(check['qualifies'])
        self.assertEqual(check['through_week'], 2)

        nd = dict(g, home_team='Notre Dame', home_conference='FBS Independents')
        self.assertFalse(build_tier5_four_factor(pd.DataFrame([nd]), summaries, 3)['1']['qualifies'])

        neutral = dict(g, neutral_site=True)
        self.assertFalse(build_tier5_four_factor(pd.DataFrame([neutral]), summaries, 3)['1']['qualifies'])

    def test_tier5_is_straight_up_and_does_not_require_market_line(self):
        g, p, r, check = self.fixture(5)
        p.update({'DK Home ML': 'Unavailable', 'DK Away ML': 'Unavailable'})
        tier5 = {'status': 'ok', 'qualifies': True, 'through_week': 2}
        card = self.select(g, p, r, check, tier5=tier5)
        self.assertEqual(card[0]['Value Stage'], 5)
        self.assertEqual(card[0]['Value Pick'], 'Home')
        self.assertEqual(card[0]['Value Market'], 'Moneyline')
        self.assertEqual(card[0]['Value Band'], 'Straight Up')

    def test_moneyline_annotation_and_scenario_do_not_change_model(self):
        s, b = self.history(final=True)
        _, p, _, _ = self.fixture(3)
        p.update({'Game ID': 3, 'Status': 'Final', 'Actual Winner': 'Home',
                  'Home Win %': .25, 'Away Win %': .75})
        out = add_waterfall_value(pd.DataFrame([p]), s, b, 3)
        self.assertEqual(out.iloc[0]['Predicted Winner'], 'Away')
        self.assertEqual(out.iloc[0]['Value Market'], 'Moneyline')
        self.assertEqual(out.iloc[0]['Value Result'], 'Correct')
        sim = waterfall_scenario_rows(out)
        self.assertEqual(sim.iloc[0]['Predicted Winner'], 'Home')
        self.assertEqual(sim.iloc[0]['Bet Line'], '+120')
        self.assertEqual(out.iloc[0]['Predicted Winner'], 'Away')

    def test_six_of_six_ats_grading_and_push(self):
        for home_points, expected in [(30, 'Incorrect'), (31, 'Push'), (35, 'Correct')]:
            s, b = self.history(final=True, home_points=home_points, away_points=24)
            _, p, _, _ = self.fixture(1)
            p.update({'Game ID': 3, 'Status': 'Final', 'Actual Winner': 'Home',
                      'Home Win %': .70, 'Away Win %': .30,
                      'Home Spread': '-7', 'Away Spread': '+7'})
            out = add_waterfall_value(pd.DataFrame([p]), s, b, 3)
            self.assertEqual(out.iloc[0]['ValueMarket'] if 'ValueMarket' in out else out.iloc[0]['Value Market'], 'Spread')
            self.assertEqual(out.iloc[0]['Value Result'], expected)

    def test_weather_tier_ats_grading_and_push(self):
        weather = {'3': {'status': 'ok', 'inclement': True, 'weather_type': 'Wet/snow only'}}
        for home_points, expected in [(30, 'Incorrect'), (31, 'Push'), (35, 'Correct')]:
            s, b = self.history(final=True, home_points=home_points, away_points=24)
            b.loc[b['team_id'].eq(10), 'completionAttempts'] = '10-30'
            b.loc[b['team_id'].eq(20), 'completionAttempts'] = '20-30'
            _, p, _, _ = self.fixture(2)
            p.update({'Game ID': 3, 'Status': 'Final', 'Actual Winner': 'Home',
                      'Home Win %': .70, 'Away Win %': .30,
                      'Home Spread': '-7', 'Away Spread': '+7'})
            out = add_waterfall_value(pd.DataFrame([p]), s, b, 3, weather_checks=weather)
            self.assertEqual(out.iloc[0]['Value Stage'], 2)
            self.assertEqual(out.iloc[0]['Value Market'], 'Spread')
            self.assertEqual(out.iloc[0]['Value Result'], expected)


class IntegrationTests(unittest.TestCase):
    def api_functions(self):
        import ast
        from pathlib import Path
        tree = ast.parse(Path('backend/main.py').read_text())
        wanted = {'attach_market_context', '_implied', 'json_rows'}
        ns = {'pd': pd, 'json': __import__('json')}
        ns['odds'] = lambda _: {'quotes': {'1': {'DraftKings': dict(
            home_id='10', away_id='20', home='+120', away='-140',
            home_spread='-3.5', away_spread='+3.5',
            home_spread_odds='-110', away_spread_odds='-110')}}}
        body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
        exec(compile(ast.Module(body=body, type_ignores=[]), 'backend/main.py', 'exec'), ns)
        return ns

    def test_api_preserves_dk_moneyline_and_spread(self):
        g, p, _, _ = WaterfallTests().fixture(2)
        p.update({'Home Team': 'Home', 'Away Team': 'Away', 'Predicted Side': 'Away'})
        ns = self.api_functions()
        out = ns['attach_market_context'](pd.DataFrame([p]), pd.DataFrame([g]))
        self.assertEqual(out.iloc[0]['DK Home ML'], '+120')
        self.assertEqual(out.iloc[0]['DK Home Spread'], '-3.5')
        self.assertEqual(out.iloc[0]['Home Spread'], '-3.5')
        self.assertNotIn('Bet Signal', out)
        self.assertEqual(len(ns['json_rows'](out)), 1)

    def test_app_parser_reads_side_specific_spreads(self):
        import ast
        from pathlib import Path
        tree = ast.parse(Path('app.py').read_text())
        wanted = {'format_moneyline', 'format_spread', 'parse_draftkings'}
        ns = {'math': math}
        body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
        exec(compile(ast.Module(body=body, type_ignores=[]), 'app.py', 'exec'), ns)
        payload = {'events': [{'id': '1', 'competitions': [{
            'competitors': [
                {'homeAway': 'home', 'team': {'id': '10'}},
                {'homeAway': 'away', 'team': {'id': '20'}},
            ],
            'status': {'type': {'completed': False}},
            'odds': [{
                'provider': {'name': 'Draft Kings'},
                'moneyline': {
                    'home': {'close': {'odds': '-345'}, 'open': {'odds': '-340'}},
                    'away': {'close': {'odds': '+275'}, 'open': {'odds': '+270'}},
                },
                'pointSpread': {
                    'home': {'close': {'line': '-9.5', 'odds': '-110'}, 'open': {'line': '-8.5', 'odds': '-110'}},
                    'away': {'close': {'line': '+9.5', 'odds': '-110'}, 'open': {'line': '+8.5', 'odds': '-110'}},
                },
            }],
        }]}]}
        quote = ns['parse_draftkings'](payload)['1']['Draft Kings']
        self.assertEqual(quote['home_spread'], '-9.5')
        self.assertEqual(quote['away_spread'], '+9.5')
        self.assertEqual(quote['home_spread_odds'], '-110')
        self.assertEqual(quote['home_spread_open'], '-8.5')

    def test_scenario_profit_uses_selected_price_and_grade(self):
        import ast
        import numpy as np
        from pathlib import Path
        from decimal import Decimal, ROUND_HALF_UP
        ns = dict(pd=pd, np=np, math=math, Decimal=Decimal, ROUND_HALF_UP=ROUND_HALF_UP)
        tree = ast.parse(Path('app.py').read_text())
        names = {'simulate_stakes', 'format_moneyline', 'payout_outcomes'}
        exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names],
                               type_ignores=[]), 'app.py', 'exec'), ns)
        s, b = WaterfallTests().history(final=True)
        _, p, _, _ = WaterfallTests().fixture(3)
        p.update({'Game ID': 3, 'Week': 3, 'Home Team': 'Home', 'Away Team': 'Away',
                  'Status': 'Final', 'Actual Winner': 'Home', 'Home Win %': .25, 'Away Win %': .75})
        rows = waterfall_scenario_rows(add_waterfall_value(pd.DataFrame([p]), s, b, 3))
        out = ns['simulate_stakes'](rows, {x: 10 for x in ('High', 'Moderate', 'Lean', 'Toss-up')})
        self.assertEqual(out.iloc[0]['Net Profit'], 12)
        self.assertTrue(out.iloc[0]['Won'])


if __name__ == '__main__':
    unittest.main()
