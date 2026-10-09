"""Run the actual tab bodies in Streamlit with deterministic, network-free inputs."""
import ast
from pathlib import Path
import unittest
from streamlit.testing.v1 import AppTest

APP = Path(__file__).parents[1] / 'app.py'


def harness(eager=False):
    tree = ast.parse(APP.read_text())
    helpers = {'confidence_performance', 'value_pick_performance', 'rank_parlays',
               'format_moneyline', 'payout_outcomes'}
    functions = []
    tabs = []
    keep = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in helpers:
            node.decorator_list = []
            functions.append(ast.unparse(node))
        if isinstance(node, ast.For) and isinstance(node.target, ast.Name) and node.target.id == '_tab_control':
            keep.append(ast.unparse(node))
        if isinstance(node, ast.If) and isinstance(node.test, ast.Attribute) and node.test.attr == 'open' and isinstance(node.test.value, ast.Name) and node.test.value.id in ('performance_tab', 'parlay_tab'):
            tabs.append(ast.unparse(node.body[0] if eager else node))
    assert len(tabs) == 2
    prefix = '''
import streamlit as st
import pandas as pd
import numpy as np
import math
from decimal import Decimal, ROUND_HALF_UP
from itertools import combinations
from heapq import nlargest
from html import escape
season, selected_week, MODEL_VERSION = 2026, 3, 'V1.5'
pred = pd.DataFrame([{'Game ID':i,'Week':3,'Home Team':f'H{i}','Away Team':f'A{i}',
 'Predicted Winner':f'H{i}', 'Confidence':.75, 'Status':'Final', 'Pick Result':'Correct',
 'Actual Winner':f'H{i}','Final Score':'21-10','Value Selected':True,'Value Stage':3,
 'Value Tier':'Tier 3','Value Result':'Correct','Value Pick':f'H{i}',
 'Value Market':'Moneyline','Value Line':'-150','ML Source':'DraftKings',
 'Bet Line':'-150','Expected Value':.25} for i in range(4)])
games = schedule = pd.DataFrame({'week':[3], 'completed':[True]})
live_snapshot = {'games':{}}
quality_by_match = {(f'H{i}',f'A{i}'):(True,False,False) for i in range(4)}
def tour_at(target): pass
def overlay_live_scores(frame, scores): return frame

def show_shadow_tracking(st, season, week):
    st.session_state['performance_runs'] = st.session_state.get('performance_runs',0)+1
    st.checkbox('Show entire selected season', value=True, key='shadow_all_weeks')
def christians_parlay(*args, **kwargs): return None
def future_priced_picks(*args):
    result = pred.copy()
    if st.session_state.get('no_books', False):
        result['ML Source'] = 'Other book'
    return result
'''
    counter = '''
_rank = rank_parlays
def rank_parlays(*args, **kwargs):
    st.session_state['parlay_runs'] = st.session_state.get('parlay_runs',0)+1
    return _rank(*args, **kwargs)
'''
    return '\n'.join([prefix, *functions, counter, *keep,
        'cards_tab, performance_tab, parlay_tab = st.tabs(["Game cards", "Model results", "Parlay finder"], key="main_app_tabs", on_change="rerun")', *tabs])


class LazyTabTests(unittest.TestCase):
    def switch(self, app, tab):
        # AppTest does not yet serialize the browser's selected-tab widget state.
        app.session_state['main_app_tabs'] = tab
        app.run()
        self.assertFalse(app.exception)

    def test_hidden_work_skipped_and_settings_survive(self):
        app = AppTest.from_string(harness()).run()
        self.assertFalse(app.exception)
        self.assertNotIn('performance_runs', app.session_state)
        self.assertNotIn('parlay_runs', app.session_state)
        self.switch(app, 'Model results')
        app.radio(key='model_results_period').set_value('Season to date')
        self.switch(app, 'Model results')
        app.checkbox(key='shadow_all_weeks').uncheck()
        self.switch(app, 'Model results')
        before = app.session_state['performance_runs']
        self.switch(app, 'Parlay finder')
        self.assertEqual(app.session_state['performance_runs'], before)
        app.number_input(key='parlay_stake').set_value(25)
        self.switch(app, 'Parlay finder')
        app.selectbox(key='parlay_legs').select(2)
        self.switch(app, 'Parlay finder')
        app.selectbox(key='parlay_goal').select('Highest payout')
        self.switch(app, 'Parlay finder')
        app.slider(key='parlay_min_conf').set_value(70)
        self.switch(app, 'Parlay finder')
        app.selectbox(key='parlay_data_rule').select('Published pregame summaries for both teams')
        self.switch(app, 'Parlay finder')
        app.selectbox(key='parlay_book').select('DraftKings')
        self.switch(app, 'Parlay finder')
        count = app.session_state['parlay_runs']
        self.switch(app, 'Game cards')
        self.assertEqual(app.session_state['parlay_runs'], count)
        self.switch(app, 'Model results')
        self.assertEqual(app.radio(key='model_results_period').value, 'Season to date')
        self.assertFalse(app.checkbox(key='shadow_all_weeks').value)
        self.switch(app, 'Parlay finder')
        self.assertEqual(app.number_input(key='parlay_stake').value, 25)
        self.assertEqual(app.selectbox(key='parlay_legs').value, 2)
        self.assertEqual(app.selectbox(key='parlay_goal').value, 'Highest payout')
        self.assertEqual(app.slider(key='parlay_min_conf').value, 70)
        self.assertEqual(app.selectbox(key='parlay_book').value, 'DraftKings')
        self.assertEqual(app.selectbox(key='parlay_data_rule').value, 'Published pregame summaries for both teams')
        self.switch(app, 'Game cards')
        app.session_state['no_books'] = True
        self.switch(app, 'Parlay finder')
        self.assertEqual(app.selectbox(key='parlay_book').value, 'Any single sportsbook')

    def test_displayed_results_match_eager_execution(self):
        for label, index in [('Model results', 1), ('Parlay finder', 2)]:
            lazy = AppTest.from_string(harness()).run()
            eager = AppTest.from_string(harness(eager=True)).run()
            self.switch(lazy, label)
            self.assertFalse(eager.exception)
            a, b = lazy.tabs[index], eager.tabs[index]
            self.assertEqual([(m.label,m.value) for m in a.metric], [(m.label,m.value) for m in b.metric])
            self.assertEqual(len(a.dataframe), len(b.dataframe))
            for x,y in zip(a.dataframe,b.dataframe):
                import pandas as pd
                pd.testing.assert_frame_equal(x.value,y.value,check_exact=True)
            self.assertEqual([d.label for d in a.download_button], [d.label for d in b.download_button])
