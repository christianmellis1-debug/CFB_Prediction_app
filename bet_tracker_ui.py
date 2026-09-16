from pathlib import Path
import pandas as pd
import streamlit.components.v1 as components

_tracker = components.declare_component("personal_bet_tracker", path=str(Path(__file__).parent / "bet_tracker"))


def show_bet_tracker(schedule, predictions, season, week):
    prices = {(r['Home Team'], r['Away Team']): r for _, r in predictions.iterrows()}
    games = []
    for _, r in schedule.iterrows():
        if pd.isna(r.get('game_id')):
            continue
        p = prices.get((r['home_team'], r['away_team']), {})
        games.append({
            'id': str(int(r['game_id'])), 'season': int(season), 'week': int(r['week']),
            'home': str(r['home_team']), 'away': str(r['away_team']),
            'completed': str(r.get('completed', False)).lower() in ('true', 't', '1', '1.0', 'yes'),
            'homeScore': float(r['home_points']) if pd.notna(r['home_points']) else None,
            'awayScore': float(r['away_points']) if pd.notna(r['away_points']) else None,
            'homeLine': str(p.get('Home ML', 'Unavailable')), 'awayLine': str(p.get('Away ML', 'Unavailable')),
            'book': str(p.get('ML Source', '')), 'pick': str(p.get('Predicted Winner', '')),
        })
    _tracker(games=games, season=int(season), week=int(week), key="personal_bet_tracker_v1", default=None)
