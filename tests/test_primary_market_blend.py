import copy
import math
import unittest
import pandas as pd
from primary_market_blend import (
    MODEL_WEIGHT, MARKET_WEIGHT, VERSION, FALLBACK,
    market_home_probability, apply_primary_blend
)


class TestCProductionTests(unittest.TestCase):
    def setUp(self):
        self.frame = pd.DataFrame([{
            'Game ID': 123,
            'Week': 7,
            'Home Team': 'Home',
            'Away Team': 'Away',
            'Home Win %': .80,
            'Away Win %': .20,
            'Predicted Winner': 'Home',
            'Predicted Side': 'Home',
            'Confidence': .80,
            'Confidence Label': 'High',
            'Venue Risk': 'Normal',
            'Model Version': 'V1.5',
            'Pick Explanation': 'Original football-side explanation.',
            'Status': 'Awaiting final',
            'Actual Winner': '—',
            'Pick Result': 'Pending',
            'Home ML': '+140',
            'Away ML': '-160',
            'ML Source': 'DraftKings',
            'Bet Line': '+140',
            'Market Implied %': 100/240,
            'Model Edge': .80-100/240,
            'Expected Value': .80*1.4-.20,
            'Value Selected': True,
            'Value Tier': 'Tier 1 · Complete Game',
            'Value Pick': 'Home',
            'Value Side': 'Home',
            'Value Market': 'Spread'
        }])
        self.games = pd.DataFrame([{
            'game_id': 123,
            'home_team':'Home',
            'away_team':'Away',
            'start_date':'2026-10-17T19:00:00Z'
        }])
        self.now='2026-10-16T12:00:00Z'

    def blended(self, **kwargs):
        return apply_primary_blend(self.frame, self.games, now_utc=self.now, **kwargs).iloc[0]

    def test_live_primary_flips_to_the_market_favorite(self):
        copy_of_original=self.frame.copy(deep=True)
        row=self.blended()
        market=market_home_probability('+140','-160')
        expected=MODEL_WEIGHT*.80+MARKET_WEIGHT*market
        self.assertAlmostEqual(row['Home Win %'],expected)
        self.assertLess(expected,.5)
        self.assertEqual(row['Predicted Winner'],'Away')
        self.assertEqual(row['Predicted Side'],'Away')
        self.assertAlmostEqual(row['Confidence'],1-expected)
        self.assertEqual(row['Model Version'],VERSION)
        self.assertTrue(row['Market Blend Used'])
        self.assertEqual(row['V1.5 Predicted Winner'],'Home')
        self.assertEqual(row['Value Pick'],'Home')
        self.assertEqual(row['Value Side'],'Home')
        self.assertEqual(row['Value Market'],'Spread')
        self.assertEqual(row['Bet Line'],'-160')
        self.assertAlmostEqual(row['Model Edge'],.20-160/260)
        self.assertAlmostEqual(row['Expected Value'],.20*(100/160)-.80)
        self.assertIn('original V1.5',str(row['Pick Explanation']))
        pd.testing.assert_frame_equal(self.frame,copy_of_original)

    def test_stale_or_missing_quotes_do_not_change_prediction(self):
        self.assertEqual(self.blended(stale=True)['Predicted Winner'],'Home')
        self.assertEqual(self.blended(stale_event_ids=['123'])['Predicted Winner'],'Home')
        bad=self.frame.copy()
        bad.loc[0,'Away ML']='Unavailable'
        row=apply_primary_blend(bad,self.games,now_utc=self.now).iloc[0]
        self.assertEqual(row['Prediction Source'],FALLBACK)
        self.assertFalse(row['Market Blend Used'])

    def test_market_rejects_nonstandard_or_crossed_prices(self):
        for h,a in [('-600','-600'),('Unavailable','-110'),('+70','-100'),
                    (None,'+200'),(float('nan'),'+120')]:
            self.assertIsNone(market_home_probability(h,a))
        self.assertAlmostEqual(market_home_probability('+100','-110'),.5/(.5+110/210))

    def test_historical_completed_games_stay_v15(self):
        historical=self.games.copy()
        historical.loc[0,'start_date']='2026-10-10T19:00:00Z'
        self.frame.loc[0,'Status']='Final'
        self.frame.loc[0,'Actual Winner']='Away'
        out=apply_primary_blend(self.frame,historical,now_utc=self.now).iloc[0]
        self.assertEqual(out['Predicted Winner'],'Home')
        self.assertEqual(out['Pick Result'],'Pending')
        self.assertFalse(out['Market Blend Used'])

    def test_started_games_use_only_frozen_pregame_prices(self):
        self.frame.loc[0,'Status']='Final'
        self.frame.loc[0,'Actual Winner']='Away'
        self.frame.loc[0,'Pick Result']='Incorrect'
        self.now='2026-10-18T12:00:00Z'
        no_capture=self.blended()
        self.assertEqual(no_capture['Predicted Winner'],'Home')
        frozen={'123':{
            'home':'Home','away':'Away','picked_side':'home',
            'model_probability':.80,'home_ml':140,'away_ml':-160,
            'provider':'DraftKings','captured_at':'2026-10-16T12:00:00Z',
            'kickoff':'2026-10-17T19:00:00Z'
        }}
        row=self.blended(frozen_snapshots=frozen)
        self.assertEqual(row['Predicted Winner'],'Away')
        self.assertEqual(row['Pick Result'],'Correct')
        self.assertEqual(row['Value Pick'],'Home')
        self.assertIn('frozen pregame',row['Prediction Source'])
        bad=copy.deepcopy(frozen)
        bad['123']['captured_at']='2026-10-17T20:00:00Z'
        self.assertEqual(self.blended(frozen_snapshots=bad)['Predicted Winner'],'Home')

    def test_market_can_change_probability_without_winner_change(self):
        self.frame.loc[0,'Home ML']=-600
        self.frame.loc[0,'Away ML']=450
        row=self.blended()
        self.assertEqual(row['Predicted Winner'],'Home')
        self.assertEqual(row['V1.5 Predicted Winner'],'Home')
        self.assertEqual(row['Confidence Label'],'High')
        self.assertNotEqual(row['Confidence'],.80)


if __name__=='__main__':
    unittest.main()
