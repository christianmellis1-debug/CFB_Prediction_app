"""Parse ESPN scores independently of predictions and sportsbook prices."""
import math

def parse_live_scores(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get('events'), list):
        raise ValueError('Invalid live scoreboard response')
    games = {}
    for event in payload['events']:
        for competition in event.get('competitions', []):
            sides = {c.get('homeAway'): c for c in competition.get('competitors', [])}
            if not all(side in sides for side in ('home', 'away')):
                continue
            status = competition.get('status') or event.get('status', {})
            kind = status.get('type', {})
            scores = {}
            for side in ('home', 'away'):
                try:
                    number = float(sides[side].get('score'))
                    scores[side] = int(number) if math.isfinite(number) and number >= 0 and number.is_integer() else None
                except (ValueError, TypeError):
                    scores[side] = None
            games[str(event.get('id'))] = {
                'home_id': str(sides['home'].get('team', {}).get('id', '')),
                'away_id': str(sides['away'].get('team', {}).get('id', '')),
                'home_score': scores['home'], 'away_score': scores['away'],
                'state': str(kind.get('state', 'pre')),
                'completed': kind.get('completed') is True,
                'detail': str(kind.get('detail') or kind.get('shortDetail') or kind.get('description') or 'Status unavailable'),
            }
    return games

def overlay_live_scores(games, scores):
    """Update an outcome-only copy, never the schedule used for model features."""
    result = games.copy()
    result['Live State'] = ''
    result['Live Detail'] = ''
    result['Live Score'] = '—'
    for i, game in result.iterrows():
        try:
            quote = scores.get(str(int(game['game_id'])))
            if not quote or quote['home_id'] != str(int(game['home_id'])) or quote['away_id'] != str(int(game['away_id'])):
                continue
        except (ValueError, TypeError, KeyError):
            continue
        done = str(game.get('completed', False)).lower() in ('true','t','1','1.0','yes')
        if done and not quote['completed']:
            continue
        result.loc[i, 'Live State'] = quote['state']
        result.loc[i, 'Live Detail'] = quote['detail']
        if quote['state'] not in ('in', 'post') and not quote['completed']:
            continue
        if quote['home_score'] is None or quote['away_score'] is None:
            continue
        result.loc[i, 'Live Score'] = f"{game['away_team']} {quote['away_score']} – {game['home_team']} {quote['home_score']}"
        # Only an explicitly completed event may settle a pick or bet.
        if quote['completed']:
            result.loc[i, 'home_points'] = quote['home_score']
            result.loc[i, 'away_points'] = quote['away_score']
            result.loc[i, 'completed'] = True
    return result
