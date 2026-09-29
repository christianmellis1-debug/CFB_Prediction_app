import copy
import unittest
from shadow_tracking import make_snapshot,settle,comparison,signal,profit,MODEL_WEIGHT

class TrackingTests(unittest.TestCase):
    def setUp(self):
        self.game=dict(game_id=1,season=2026,week=5,home_id=10,away_id=20,home_team='Home',away_team='Away',start_date='2026-10-01T20:00:00Z')
        self.pick={'Predicted Side':'Home','Confidence':.75,'Predicted Winner':'Home'}
        self.payload={'header':{'id':'1','competitions':[{'date':'2026-10-01T20:00:00Z','timeValid':True,'status':{'type':{'state':'pre','completed':False}},'competitors':[{'homeAway':'home','team':{'id':'10'},'score':'21'},{'homeAway':'away','team':{'id':'20'},'score':'14'}]}]},'pickcenter':[{'provider':{'name':'DraftKings'},'homeTeamOdds':{'moneyLine':-150},'awayTeamOdds':{'moneyLine':130}}]}
    def snapshot(self):
        return make_snapshot(self.game,self.pick,self.payload,'2026-09-29T12:00:00Z',{})
    def test_blend_and_labels(self):
        s=self.snapshot()
        market=.6/(.6+100/230)
        self.assertAlmostEqual(s['blend_probability'],MODEL_WEIGHT*.75+(1-MODEL_WEIGHT)*market)
        self.assertEqual(s['model_signal'],'Strong value')
        self.assertEqual(s['blend_signal'],'Pass')
    def test_reject_live_final_tbd_late_and_wrong_ids(self):
        original=copy.deepcopy(self.payload)
        for state in ['in','post']:
            self.payload['header']['competitions'][0]['status']['type']['state']=state
            with self.assertRaises(ValueError):self.snapshot()
        self.payload=copy.deepcopy(original)
        self.payload['header']['competitions'][0]['timeValid']=False
        with self.assertRaises(ValueError):self.snapshot()
        self.payload=copy.deepcopy(original)
        with self.assertRaises(ValueError):make_snapshot(self.game,self.pick,self.payload,'2026-10-01T20:00:00Z',{})
        self.payload['header']['competitions'][0]['competitors'][0]['team']['id']='99'
        with self.assertRaises(ValueError):self.snapshot()
    def test_missing_opponent_price_rejected(self):
        del self.payload['pickcenter'][0]['awayTeamOdds']
        with self.assertRaises(ValueError):self.snapshot()
    def test_settlement_and_pending(self):
        s=self.snapshot()
        self.assertIsNone(settle(s,self.payload,'now'))
        state=self.payload['header']['competitions'][0]['status']['type']
        state.update(completed=True,state='post',name='STATUS_FINAL')
        r=settle(s,self.payload,'now')
        self.assertEqual(r['outcome'],'win')
        log={'snapshots':{'1':s},'results':{'1':r}}
        rows=comparison(log,2026).set_index('Method')
        self.assertEqual(rows.loc['Frozen V1.5','Profit ($10/bet)'],6.67)
        self.assertEqual(rows.loc['Sportsbook blend','Value bets settled'],0)
        self.assertEqual(comparison({'snapshots':{'1':s},'results':{}},2026)['Graded games'].sum(),0)
    def test_collector_does_not_replace_locked_prediction(self):
        import tempfile
        from pathlib import Path
        from datetime import datetime,timezone
        from unittest.mock import patch
        import pandas as pd
        import capture_shadow as collector
        snapshot=self.snapshot()
        log={'experiment':snapshot['experiment'],'snapshots':{'1':snapshot},'results':{}}
        game=dict(self.game,season_type='regular',home_division='fbs',away_division='fbs',home_points=None,away_points=None,completed=False,neutral_site=False)
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'tracking.json'
            with patch.object(collector,'DATA',target),patch.object(collector,'load',return_value=log),patch.object(collector,'now',return_value=datetime(2026,9,29,tzinfo=timezone.utc)),patch.object(collector,'download_schedule',return_value=pd.DataFrame([game])),patch.object(collector,'fetch',return_value=(self.payload,'2026-09-29T14:00:00Z')),patch.object(collector,'read_summary') as summary:
                collector.main()
                summary.assert_not_called()
            import json
            self.assertEqual(json.loads(target.read_text())['snapshots']['1'],snapshot)

    def test_header_time_valid(self):
        del self.payload['header']['competitions'][0]['timeValid']
        self.payload['header']['timeValid']=True
        self.assertEqual(self.snapshot()['game_id'],'1')

    def test_moneyline_profit(self):
        self.assertEqual(profit(130,'win'),13)
        self.assertEqual(profit(-150,'loss'),-10)
        self.assertEqual(profit(-150,'push'),0)

if __name__=='__main__':unittest.main()
