import ast
from pathlib import Path
import unittest
import pandas as pd
from pandas.testing import assert_frame_equal
from performance_cache import cache_calculation, clear_calculations
from model_v1_5 import COMPONENT_SPEC, predict_week, add_waterfall_value
from matchup_advantages import build_advantages, build_waterfall_profiles
from test_matchup_advantages import AdvantageTests


class CacheTests(unittest.TestCase):
    def setUp(self):
        clear_calculations()

    def test_invalidation_and_isolation(self):
        calls = []
        def calculate(frame, factor):
            calls.append(1)
            return frame.assign(result=frame.x * factor)
        cached = cache_calculation('v1')(calculate)
        frame = pd.DataFrame({'x': range(60000)})
        first = cached(frame, 2)
        first.loc[0, 'result'] = -99
        self.assertEqual(cached(frame, 2).loc[0, 'result'], 0)
        self.assertEqual(len(calls), 1)
        frame.loc[59999, 'x'] = 7
        self.assertEqual(cached(frame, 2).loc[59999, 'result'], 14)
        cached(frame, 3)
        cache_calculation('v2')(calculate)(frame, 3)
        self.assertEqual(len(calls), 4)
        clear_calculations()
        cached(frame, 3)
        self.assertEqual(len(calls), 5)

    def test_failure_is_retried(self):
        calls = []
        def flaky():
            calls.append(1)
            if len(calls) == 1:
                raise ValueError('temporary')
            return 42
        cached = cache_calculation('v1')(flaky)
        with self.assertRaises(ValueError):
            cached()
        self.assertEqual(cached(), 42)
        self.assertEqual(cached(), 42)
        self.assertEqual(len(calls), 2)

    def test_prediction_tier_and_result_parity(self):
        fixture = AdvantageTests(); fixture.setUp()
        schedule, boxes = fixture.s, fixture.b
        schedule['home_team'] = 'Home'; schedule['away_team'] = 'Away'
        schedule['home_pregame_elo'] = 1600; schedule['away_pregame_elo'] = 1400
        schedule['neutral_site'] = False
        current = pd.DataFrame([dict(season=2026, team_id=tid, through_week=1,
            **{spec[0]: val for spec in COMPONENT_SPEC.values()})
            for tid, val in [(10, .6), (20, .4)]])
        prior = current.assign(season=2025)
        names = {'augment_missing_summaries', 'predict_all_games', 'attach_results'}
        tree = ast.parse((Path(__file__).parents[1] / 'app.py').read_text())
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        for n in nodes:
            n.decorator_list = []
        ns = dict(__name__='app', pd=pd, predict_week=predict_week)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'app.py', 'exec'), ns)
        raw = ns['predict_all_games']; cached = cache_calculation('test')(raw)
        for week in (1, 2):
            expected = raw(current, prior, schedule, week)
            for _ in range(2):
                actual = cached(current, prior, schedule, week)
                assert_frame_equal(actual, expected, check_exact=True)
                assert_frame_equal(ns['attach_results'](actual, schedule[schedule.week.eq(week)]),
                                   ns['attach_results'](expected, schedule[schedule.week.eq(week)]))
        for function in (build_advantages, build_waterfall_profiles):
            cached = cache_calculation('test')(function)
            for _ in range(2):
                self.assertEqual(cached(schedule, boxes, 2), function(schedule, boxes, 2))
        predictions = raw(current, prior, schedule, 2)
        cached = cache_calculation('test')(add_waterfall_value)
        expected = add_waterfall_value(predictions, schedule, boxes, 2, published_summary=current)
        for _ in range(2):
            assert_frame_equal(cached(predictions, schedule, boxes, 2, published_summary=current), expected, check_exact=True)
        raw = ns['augment_missing_summaries']; cached = cache_calculation('test')(raw)
        expected, meta = raw(current.iloc[:0], prior, schedule, 2)
        actual, actual_meta = cached(current.iloc[:0], prior, schedule, 2)
        assert_frame_equal(actual, expected, check_exact=True)
        self.assertEqual(meta, actual_meta)
