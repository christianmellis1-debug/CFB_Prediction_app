"""Frozen V1.5 input processing from app commit 11f9728. No UI execution."""
import math
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.request import urlopen
from io import BytesIO
import pandas as pd
import numpy as np
from shadow_model_v1_5 import COMPONENT_SPEC, predict_week

def download_schedule(season):
    url = f'https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_{season}.csv'
    with urlopen(url, timeout=30) as response:
        frame = pd.read_csv(BytesIO(response.read()), low_memory=False)
        frame.attrs['fetched_at'] = datetime.now(ZoneInfo('America/Chicago')).strftime('%b %d, %I:%M %p %Z')
        return frame

def download_summary(year):
    url = f'https://github.com/sportsdataverse/sportsdataverse-data/releases/download/cfb_team_summaries_weekly/cfb_team_summaries_weekly_{year}.csv'
    with urlopen(url, timeout=60) as response:
        frame = pd.read_csv(BytesIO(response.read()), low_memory=False)
        frame.attrs['fetched_at'] = datetime.now(ZoneInfo('America/Chicago')).strftime('%b %d, %I:%M %p %Z')
        return frame

def read_summary(upload, year):
    if upload is not None:
        frame = pd.read_csv(upload, low_memory=False)
    else:
        frame = download_summary(year).copy()
    required = {'season', 'team_id', 'through_week'} | {spec[0] for spec in COMPONENT_SPEC.values()}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f'{year} summaries are missing: ' + ', '.join(sorted(missing)))
    frame = frame[pd.to_numeric(frame['season'], errors='coerce') == year].copy()
    for col in required - {'season'}:
        frame[col] = pd.to_numeric(frame[col], errors='coerce')
    if frame.empty:
        raise ValueError(f'No team-summary data for {year} has been published yet.')
    if frame[['team_id', 'through_week']].isna().any().any():
        raise ValueError(f'{year} summaries contain invalid team IDs or weeks.')
    if frame.duplicated(['team_id', 'through_week']).any():
        raise ValueError(f'{year} summaries contain duplicate team/week rows.')
    return frame

def augment_missing_summaries(current, prior, schedule, target_week):
    """Create transparent provisional rows when the weekly feed omits a team.

    The schedule has reliable completed-game scores even when the advanced
    summary release is late. Clone the team's latest prior-season profile and
    apply a modest scoring/points-allowed adjustment from completed games.
    """
    result = current.copy()
    derived = {}
    eligible_ids = set(result.loc[pd.to_numeric(result['through_week'], errors='coerce') < int(target_week), 'team_id'].astype(int))
    games = schedule.copy()
    if 'completed' in games:
        done = games['completed'].astype(str).str.lower().isin(['true', 't', '1', '1.0', 'yes', 'y'])
        games = games[done]
    games = games[pd.to_numeric(games['week'], errors='coerce') < int(target_week)]
    games = games[pd.notna(games['home_points']) & pd.notna(games['away_points'])]
    if games.empty:
        return (result, derived)
    for tid in set(games['home_id'].astype(int)) | set(games['away_id'].astype(int)):
        if tid in eligible_ids:
            continue
        prior_rows = prior[prior['team_id'].astype(int) == tid]
        team_games = games[(games['home_id'].astype(int) == tid) | (games['away_id'].astype(int) == tid)]
        if prior_rows.empty or team_games.empty:
            continue
        base = prior_rows.sort_values('through_week').iloc[-1].copy()
        points_for, points_against = ([], [])
        for _, game in team_games.iterrows():
            if int(game['home_id']) == tid:
                points_for.append(float(game['home_points']))
                points_against.append(float(game['away_points']))
            else:
                points_for.append(float(game['away_points']))
                points_against.append(float(game['home_points']))
        base['season'] = int(pd.to_numeric(schedule['season'], errors='coerce').dropna().iloc[0])
        base['through_week'] = int(pd.to_numeric(team_games['week'], errors='coerce').max())
        if 'adj_off_epa' in base:
            base['adj_off_epa'] = float(base['adj_off_epa']) + (sum(points_for) / len(points_for) - 28.0) / 14.0
        if 'adj_def_epa' in base:
            base['adj_def_epa'] = float(base['adj_def_epa']) + (sum(points_against) / len(points_against) - 28.0) / 14.0
        result = pd.concat([result, pd.DataFrame([base])], ignore_index=True)
        derived[tid] = {'games': len(team_games), 'through_week': int(base['through_week'])}
    return (result, derived)

def predict_all_games(current, prior, schedule, week):
    model_schedule = schedule.copy()
    target = pd.to_numeric(model_schedule['week'], errors='coerce') == int(week)
    if 'completed' in model_schedule:
        model_schedule.loc[target, 'completed'] = False
    predictions = predict_week(current, prior, model_schedule, week)
    if not predictions.empty and 'Game ID' not in predictions:
        predictions['Game ID'] = None
    return predictions

def format_moneyline(value):
    if value is None or isinstance(value, bool):
        return 'Unavailable'
    raw = str(value).strip().replace('−', '-')
    if raw.upper() in {'EVEN', 'EV', 'EVS'}:
        return '+100'
    try:
        price = float(raw)
        if not math.isfinite(price) or abs(price) < 100 or (not price.is_integer()):
            return 'Unavailable'
        return f'{int(price):+d}'
    except (ValueError, TypeError):
        return 'Unavailable'

def parse_draftkings(payload):
    """Return every sportsbook's current moneyline for each event.

    DraftKings is preferred in the UI. Other providers are retained as a
    clearly labeled fallback when DraftKings is unavailable or suspended.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get('events'), list):
        raise ValueError('Invalid odds response')
    quotes = {}
    for event in payload['events']:
        event_quotes = {}
        for competition in event.get('competitions', []):
            sides = {c.get('homeAway'): str(c.get('team', {}).get('id', '')) for c in competition.get('competitors', [])}
            completed = bool(competition.get('status', {}).get('type', {}).get('completed', False))
            for odds in competition.get('odds', []):
                provider_name = str(odds.get('provider', {}).get('name', '')).strip()
                if not provider_name:
                    continue
                prices = {}
                for side in ('home', 'away'):
                    market = odds.get('moneyline', {}).get(side, {})
                    value = (market.get('close') or {}).get('odds') if 'close' in market else odds.get(side + 'TeamOdds', {}).get('moneyLine')
                    prices[side] = format_moneyline(value)
                    opening = (market.get('open') or {}).get('odds')
                    if opening is None:
                        legacy = (odds.get(side + 'TeamOdds', {}).get('open') or {}).get('moneyLine', {})
                        opening = legacy.get('american', legacy.get('alternateDisplayValue')) if isinstance(legacy, dict) else legacy
                    prices[side + '_open'] = format_moneyline(opening)
                if prices['home'] == 'Unavailable' and prices['away'] == 'Unavailable':
                    continue
                event_quotes[provider_name] = {'home_id': sides.get('home', ''), 'away_id': sides.get('away', ''), 'home': prices['home'], 'away': prices['away'], 'completed': completed, 'home_open': prices['home_open'], 'away_open': prices['away_open']}
        if event_quotes:
            quotes[str(event.get('id'))] = event_quotes
    return quotes
