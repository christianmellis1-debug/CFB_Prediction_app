import copy
import unittest

from shadow_tracking import (
    MODEL_WEIGHT,
    CHALLENGER_NAME,
    make_snapshot,
    settle,
    comparison,
    winner_comparison,
)


class LeadingChallengerTests(unittest.TestCase):
    def setUp(self):
        self.game = {
            'game_id': 1, 'season': 2026, 'week': 7,
            'home_id': 10, 'away_id': 20,
            'home_team': 'Home', 'away_team': 'Away',
            'start_date': '2026-10-14T20:00:00Z'
        }
        self.payload = {
            'header': {
                'id': '1',
                'competitions': [{
                    'date': '2026-10-14T20:00:00Z',
                    'timeValid': True,
                    'status': {'type': {'state': 'pre', 'completed': False}},
                    'competitors': [
                        {'homeAway': 'home', 'team': {'id': '10'}, 'score': '14'},
                        {'homeAway': 'away', 'team': {'id': '20'}, 'score': '28'}
                    ]
                }]
            },
            'pickcenter': [{
                'provider': {'name': 'DraftKings'},
                'homeTeamOdds': {'moneyLine': 250},
                'awayTeamOdds': {'moneyLine': -300}
            }]
        }

    def snapshot(self, side='Home', confidence=.75):
        return make_snapshot(
            self.game,
            {'Predicted Side': side,
             'Confidence': confidence,
             'Predicted Winner': side},
            self.payload, '2026-10-13T12:00:00Z', {'model_version': 'V1.5'}
        )

    def settle_game(self, snap, home_score='14', away_score='28'):
        competition = self.payload['header']['competitions'][0]
        competition['status']['type'].update(
            state='post', completed=True, name='STATUS_FINAL')
        competition['competitors'][0]['score'] = home_score
        competition['competitors'][1]['score'] = away_score
        return settle(snap, self.payload, '2026-10-15T00:00:00Z')

    def test_corrects_v15_error_and_preserves_original_side_value_test(self):
        s = self.snapshot()
        self.assertLess(s['blend_probability'], .5)
        result = self.settle_game(s)
        self.assertEqual(result['outcome'], 'loss')
        log = {'snapshots': {'1': s}, 'results': {'1': result}}
        metrics, games = winner_comparison(log, 2026)
        frame = metrics.set_index('Method')
        self.assertEqual(frame.loc['Frozen V1.5', 'Correct winners'], 0)
        self.assertEqual(frame.loc[CHALLENGER_NAME, 'Correct winners'], 1)
        self.assertEqual(frame.loc[CHALLENGER_NAME, 'Winner switches vs V1.5'], 1)
        self.assertEqual(frame.loc[CHALLENGER_NAME, 'Errors fixed'], 1)
        self.assertEqual(frame.loc[CHALLENGER_NAME, 'New errors'], 0)
        self.assertEqual(games.iloc[0]['Test C Winner'], 'Away')
        self.assertAlmostEqual(
            games.iloc[0]['Test C Confidence'], 1-s['blend_probability'])
        self.assertAlmostEqual(
            frame.loc[CHALLENGER_NAME, 'Brier score (lower is better)'],
            s['blend_probability'] ** 2)
        existing = comparison(log, 2026).set_index('Method')
        self.assertEqual(existing.loc['Frozen V1.5', 'Wins'], 0)

    def test_avoids_false_credit_when_it_breaks_correct_prediction(self):
        s = self.snapshot()
        result = self.settle_game(s, '28', '14')
        self.assertEqual(result['outcome'], 'win')
        metrics, _ = winner_comparison(
            {'snapshots': {'1': s}, 'results': {'1': result}}, 2026)
        c = metrics.set_index('Method').loc[CHALLENGER_NAME]
        self.assertEqual(c['Correct winners'], 0)
        self.assertEqual(c['New errors'], 1)
        self.assertEqual(c['Errors fixed'], 0)

    def test_away_side_switch_and_pending_exclusion(self):
        s = self.snapshot('Away', .74)
        self.assertGreater(s['blend_probability'], .5)
        result = self.settle_game(s, '28', '14')
        metrics, games = winner_comparison(
            {'snapshots': {'1': s}, 'results': {'1': result}}, 2026)
        self.assertEqual(games.iloc[0]['V1.5 Winner'], 'Away')
        self.assertEqual(games.iloc[0]['Test C Winner'], 'Away')
        self.assertEqual(metrics.iloc[1]['Correct winners'], 0)
        empty, empty_games = winner_comparison(
            {'snapshots': {'1': s}, 'results': {}}, 2026)
        self.assertEqual(empty['Settled games'].sum(), 0)
        self.assertTrue(empty_games.empty)
        wrong_week, _ = winner_comparison(
            {'snapshots': {'1': s}, 'results': {'1': result}}, 2026, week=6)
        self.assertEqual(wrong_week['Settled games'].sum(), 0)

    def test_no_mutations_or_backfilled_predictions(self):
        s = self.snapshot()
        log = {'snapshots': {'1': s}, 'results': {'1': {'outcome': 'win'}}}
        original = copy.deepcopy(log)
        winner_comparison(log, 2026)
        self.assertEqual(log, original)


if __name__ == '__main__':
    unittest.main()
