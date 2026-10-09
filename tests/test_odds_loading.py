"""Network-free tests of production odds loading and failure recovery."""
import ast
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO
import json
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse, parse_qs
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit
from live_scores import parse_live_scores

APP = Path(__file__).parents[1] / 'app.py'
NAMES = {'format_moneyline','format_spread','parse_draftkings','parse_archived_summary',
         'download_event_payload','download_archived_event','fetch_scoreboard',
         'download_live_event','download_live_scores','download_event_moneylines',
         'download_market_core','enrich_market_history','download_market_odds',
         'market_odds_for_display','clear_market_odds','watch_results'}


def functions(source):
    nodes = [n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name in NAMES]
    ns = dict(__name__='odds_test', __file__=str(APP), pd=pd, math=math, json=json,
              datetime=datetime, timezone=timezone, ZoneInfo=ZoneInfo, Path=Path,
              deepcopy=deepcopy, urlencode=urlencode, HTTPError=HTTPError,
              ThreadPoolExecutor=ThreadPoolExecutor, parse_live_scores=parse_live_scores,
              st=SimpleNamespace(cache_data=streamlit.cache_data,session_state={},fragment=lambda **kw: lambda f:f))
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(APP),'exec'),ns)
    return ns


def event(gid, opening=False, spread=True, completed=False):
    price = {'provider':{'name':'DraftKings'}, 'moneyline':{}, 'pointSpread':{}}
    for side,ml,sp in [('home',-150,-3),('away',130,3)]:
        price['moneyline'][side] = {'close':{'odds':ml}}
        if opening:
            price['moneyline'][side]['open'] = {'odds':-140 if side=='home' else 120}
        if spread:
            price['pointSpread'][side] = {'close':{'line':sp,'odds':-110}}
    competition = {'competitors':[{'homeAway':side,'team':{'id':str(gid*10+i)},'score':'0'}
                                  for i,side in enumerate(('home','away'))],
                   'status':{'type':{'completed':completed,'state':'post' if completed else 'pre'}},
                   'odds':[price]}
    return {'id':str(gid),'competitions':[competition]}


class OddsLoadingTests(unittest.TestCase):
    def setUp(self):
        self.ns = functions(APP.read_text())
        for name in NAMES:
            f=self.ns.get(name)
            if hasattr(f,'clear'): f.clear()
        self.calls=Counter()
        self.events=[event(1),event(2,spread=False)]
        self.fail_board=False
        self.fail_events=set()
        def urlopen(url,timeout=None):
            if '/scoreboard?' in url:
                self.calls['board']+=1
                if self.fail_board: raise TimeoutError('scoreboard slow')
                return BytesIO(json.dumps({'events':self.events}).encode())
            gid=parse_qs(urlparse(url).query)['event'][0]
            self.calls[gid]+=1
            if gid in self.fail_events: raise TimeoutError('summary slow')
            e=event(int(gid),opening=True)
            return BytesIO(json.dumps({'header':e,'pickcenter':e['competitions'][0]['odds']}).encode())
        self.ns['urlopen']=urlopen

    def test_shares_scoreboard_and_omitted_game_summary(self):
        self.ns['download_live_scores']('20261010',('1','2','3'))
        core=self.ns['download_market_core']('20261010',('1','2','3'))
        self.assertEqual(self.calls['board'],1)
        self.assertEqual(self.calls['3'],1)
        self.assertEqual(core['quotes']['3']['DraftKings']['home'],'-150')

    def test_opening_only_requests_are_deferred_and_coverage_retained(self):
        core=self.ns['download_market_core']('20261010',('1','2','3'))
        self.assertEqual(self.calls['1'],0)
        self.assertEqual(self.calls['2'],1)
        self.assertEqual(self.calls['3'],1)
        full=self.ns['download_market_odds']('20261010',('1','2','3'))
        self.assertEqual(self.calls['1'],1)
        self.assertEqual(self.calls['2'],1)
        self.assertEqual(set(full['quotes']),{'1','2','3'})
        self.assertEqual(full['quotes']['1']['DraftKings']['home_open'],'-140')
        self.assertEqual(core['quotes']['1']['DraftKings']['home_open'],'Unavailable')
        self.assertEqual(full['quotes']['2']['DraftKings']['home_spread'],'-3')

    def test_whole_feed_failure_retains_timestamp_and_recovers(self):
        get=self.ns['market_odds_for_display']
        good=get('20261010',('1',),include_history=True)
        self.ns['clear_market_odds']();self.fail_board=True
        stale=get('20261010',('1',))
        self.assertTrue(stale['stale'])
        self.assertEqual(stale['quotes'],good['quotes'])
        self.assertEqual(stale['retrieved'],good['retrieved'])
        with self.assertRaises(TimeoutError): get('20261011',('8',))
        self.fail_board=False
        recovered=get('20261010',('1',))
        self.assertFalse(recovered['stale'])

    def test_partial_failure_retains_only_failed_missing_events(self):
        get=self.ns['market_odds_for_display']
        good=get('20261010',('1','3'))
        self.ns['clear_market_odds']();self.ns['download_event_moneylines'].clear()
        self.fail_events.add('3')
        fresh=get('20261010',('1','3'))
        self.assertEqual(fresh['quotes']['3'],good['quotes']['3'])
        self.assertEqual(fresh['stale_events'],{'3':good['retrieved']})
        self.assertFalse(fresh['stale'])

    def test_successful_market_withdrawal_does_not_restore_old_odds(self):
        get=self.ns['market_odds_for_display']
        get('20261010',('1',))
        self.ns['clear_market_odds']();self.ns['download_event_moneylines'].clear()
        self.events=[]
        self.ns['download_event_moneylines']=lambda *a:{}
        fresh=get('20261010',('1',))
        self.assertEqual(fresh['quotes']['1'],{})
        self.assertEqual(fresh['stale_events'],{})

    def test_history_failure_keeps_current_prices_and_does_not_repeat_core_failure(self):
        self.fail_events.update(('1','3'))
        full=self.ns['download_market_odds']('20261010',('1','3'))
        self.assertEqual(full['quotes']['1']['DraftKings']['home'],'-150')
        self.assertIn('1',full['history_errors'])
        self.assertIn('3',full['lookup_errors'])
        self.assertEqual(self.calls['3'],1)

    def test_enrichment_survives_rerun_and_manual_refresh_clears_shared_requests(self):
        get=self.ns['market_odds_for_display']
        get('20261010',('1',))
        full=get('20261010',('1',),include_history=True)
        again=get('20261010',('1',))
        self.assertEqual(again['quotes'],full['quotes'])
        self.ns['clear_market_odds']()
        self.ns['download_market_core']('20261010',('1',))
        self.assertEqual(self.calls['board'],2)

    def test_history_refresh_reruns_once_and_stale_health_recovers(self):
        class Rerun(BaseException): pass
        def rerun(): raise Rerun()
        st = self.ns['st']
        st.rerun = rerun
        st.caption = st.warning = lambda *a: None
        self.ns['download_live_scores'] = lambda *a: {'games':{},'retrieved':'now'}
        get = self.ns['market_odds_for_display']
        watch = self.ns['watch_results']
        core = get('20261010',('1',))
        health = {'stale':False,'stale_events':{}}
        with self.assertRaises(Rerun):
            watch(2026,None,'20261010',core['quotes'],('1',),{},health)
        full = get('20261010',('1',))
        # Completed history no longer causes another full rerun.
        watch(2026,None,'20261010',full['quotes'],('1',),{},health)
        self.ns['clear_market_odds'](); self.fail_board=True
        with self.assertRaises(Rerun):
            watch(2026,None,'20261010',full['quotes'],('1',),{},health)
        self.fail_board=False
        with self.assertRaises(Rerun):
            watch(2026,None,'20261010',full['quotes'],('1',),{}, {'stale':True,'stale_events':{}})
