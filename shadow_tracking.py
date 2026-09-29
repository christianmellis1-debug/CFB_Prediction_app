"""Prospective frozen-model experiment. Never changes the app's live picks."""
import json
import math
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

EXPERIMENT = 'v15-market-blend-2026-09-28'
MODEL_WEIGHT = 0.16927926947215113
ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data' / 'shadow_tracking.json'

def utc(value):
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Timezone is required')
    return parsed.astimezone(timezone.utc)

def implied(line):
    line = float(line)
    if not math.isfinite(line) or abs(line) < 100:
        raise ValueError('Invalid American moneyline')
    return 100 / (line + 100) if line > 0 else -line / (-line + 100)

def signal(probability, line):
    edge = probability - implied(line)
    profit = float(line)/100 if float(line)>0 else 100/abs(float(line))
    ev = probability * profit - (1-probability)
    if probability >= .70 and edge >= .03 and ev > 0:
        return 'Strong value'
    if probability >= .60 and edge >= .02 and ev > 0:
        return 'Value'
    return 'Pass'

def profit(line, outcome):
    if outcome == 'push':
        return 0.0
    if outcome == 'loss':
        return -10.0
    value = Decimal(str(line))
    amount = Decimal(10) * (value/100 if value>0 else Decimal(100)/abs(value))
    return float(amount.quantize(Decimal('.01'), rounding=ROUND_HALF_UP))

def make_snapshot(game, pick, payload, captured_at, provenance):
    """Reject live/final/TBD, wrong-team, missing-price and late responses."""
    from shadow_inputs import parse_draftkings
    now = utc(captured_at)
    gid = str(int(game['game_id']))
    header = payload.get('header', {})
    if str(header.get('id')) != gid:
        raise ValueError('Event ID mismatch')
    comps = header.get('competitions', [])
    if len(comps) != 1:
        raise ValueError('Ambiguous competition')
    comp = comps[0]
    state = comp.get('status', {}).get('type', {})
    if state.get('state') != 'pre' or state.get('completed'):
        raise ValueError('Not pregame')
    if header.get('timeValid', comp.get('timeValid')) is not True or comp.get('dateValid') is False:
        raise ValueError('Kickoff time not confirmed')
    kickoff = utc(comp['date'])
    scheduled = utc(game['start_date'])
    if not now < min(kickoff, scheduled) or kickoff-now > timedelta(days=7):
        raise ValueError('Outside pregame capture window')
    comp = dict(comp, odds=payload.get('pickcenter', []) or comp.get('odds', []))
    quotes = parse_draftkings({'events':[{'id':gid,'competitions':[comp]}]}).get(gid,{})
    candidates=[]
    for book, quote in quotes.items():
        if quote['home_id'] != str(int(game['home_id'])) or quote['away_id'] != str(int(game['away_id'])):
            continue
        try:
            hp, ap = implied(quote['home']), implied(quote['away'])
        except (ValueError, TypeError):
            continue
        candidates.append((book, quote, hp, ap))
    candidates.sort(key=lambda x:(x[0].lower().replace(' ','')!='draftkings',x[0]))
    if not candidates:
        raise ValueError('No same-book two-sided moneyline')
    book, quote, hp, ap = candidates[0]
    side = str(pick['Predicted Side']).lower()
    if side not in ('home','away'):
        raise ValueError('Invalid predicted side')
    p = float(pick['Confidence'])
    if not math.isfinite(p) or not 0<=p<=1:
        raise ValueError('Invalid model probability')
    market = (hp if side=='home' else ap)/(hp+ap)
    blend = MODEL_WEIGHT*p + (1-MODEL_WEIGHT)*market
    line = float(quote[side])
    return dict(experiment=EXPERIMENT, game_id=gid, season=int(game['season']),
        week=int(game['week']), home_id=str(int(game['home_id'])),away_id=str(int(game['away_id'])),
        home=str(game['home_team']),away=str(game['away_team']),picked_side=side,
        picked_team=str(pick['Predicted Winner']),captured_at=now.isoformat(),kickoff=kickoff.isoformat(),
        provider=book,home_ml=float(quote['home']),away_ml=float(quote['away']),pick_ml=line,
        model_probability=p,market_probability=market,blend_probability=blend,
        model_signal=signal(p,line),blend_signal=signal(blend,line),model_weight=MODEL_WEIGHT,
        provenance=provenance)

def settle(snapshot, payload, checked_at):
    header=payload.get('header',{})
    if str(header.get('id'))!=snapshot['game_id']:
        return None
    comps=header.get('competitions',[])
    if len(comps)!=1 or not comps[0].get('status',{}).get('type',{}).get('completed'):
        return None
    comp=comps[0]
    if comp.get('status',{}).get('type',{}).get('name') not in ('STATUS_FINAL','STATUS_FINAL_OVERTIME'):
        return None
    sides={c.get('homeAway'):c for c in comp.get('competitors',[])}
    try:
        for side in ('home','away'):
            if str(sides[side]['team']['id'])!=snapshot[side+'_id']:
                return None
        h,a=(float(sides[x]['score']) for x in ('home','away'))
        if not all(math.isfinite(v) and v>=0 for v in (h,a)):
            return None
    except (KeyError,TypeError,ValueError):
        return None
    winner='home' if h>a else 'away' if a>h else 'push'
    outcome='push' if winner=='push' else 'win' if winner==snapshot['picked_side'] else 'loss'
    return dict(outcome=outcome,home_score=h,away_score=a,checked_at=checked_at)

def load():
    if DATA.exists():
        return json.loads(DATA.read_text())
    return dict(experiment=EXPERIMENT, snapshots={},results={},last_run=None)

def comparison(log, season, week=None):
    """Same locked cohort for probability scores; each method's own value subset."""
    import pandas as pd
    snapshots=[s for s in log['snapshots'].values() if s['season']==season and (week is None or s['week']==week)]
    rows=[]
    for name,pcol,scol in [('Frozen V1.5','model_probability','model_signal'),('Sportsbook blend','blend_probability','blend_signal')]:
        graded=[(s,log['results'][s['game_id']]) for s in snapshots if s['game_id'] in log['results']]
        decisive=[(s,r) for s,r in graded if r['outcome']!='push']
        bets=[(s,r) for s,r in graded if s[scol] in ('Value','Strong value')]
        net=sum(profit(s['pick_ml'],r['outcome']) for s,r in bets)
        risk=10*sum(r['outcome']!='push' for s,r in bets)
        rows.append({'Method':name,'Locked games':len(snapshots),'Graded games':len(decisive),
          'Brier score (lower is better)':sum((s[pcol]-int(r['outcome']=='win'))**2 for s,r in decisive)/len(decisive) if decisive else None,
          'Value bets settled':len(bets),'Wins':sum(r['outcome']=='win' for s,r in bets),
          'Losses':sum(r['outcome']=='loss' for s,r in bets),'Profit ($10/bet)':round(net,2),
          'ROI':net/risk if risk else None})
    return pd.DataFrame(rows)

def show_shadow_tracking(st, season, week):
    with st.expander('Forward test · current model vs sportsbook blend'):
        log=load()
        st.caption('Separate research only. Recommendations and value labels above are unchanged. The model and blend are frozen for this experiment; neither retrains from these results.')
        st.write('We lock the first eligible observation within seven days of kickoff, using a confirmed pregame status and both moneylines from one sportsbook. DraftKings is preferred. Games without an eligible snapshot are excluded; earlier weeks are not backfilled.')
        st.caption('Blend: 16.93% model + 83.07% sportsbook probability after removing the two-sided margin. Both methods keep the same predicted winner and use the existing value thresholds. Hypothetical stake: $10 per qualifying pick.')
        st.caption('Capture checks are scheduled every six hours. GitHub may delay runs. Last completed check (UTC): '+str(log.get('last_run') or 'Waiting for first check'))
        if log.get('run_summary'):
            st.json(log['run_summary'],expanded=False)
        all_weeks=st.checkbox('Show entire selected season',value=True,key='shadow_all_weeks')
        rows=comparison(log,int(season),None if all_weeks else int(week))
        st.dataframe(rows,hide_index=True,use_container_width=True)
        st.caption('ROI excludes refunded stakes. Pending games are not losses. Brier score evaluates probability quality across the same settled games; a better score does not establish profitable betting. Quote capture time is not the sportsbook’s update time.')
        if not log['snapshots']:
            st.info('No eligible pregame snapshots saved yet. Results will populate after captures and final scores become available.')
        records=[dict(s, result=log['results'].get(s['game_id'],{})) for s in log['snapshots'].values() if s['season']==int(season) and (all_weeks or s['week']==int(week))]
        st.download_button('Download locked forward-test records',json.dumps(records,indent=2),file_name='cfb_forward_test.json',mime='application/json',key='shadow_download')
