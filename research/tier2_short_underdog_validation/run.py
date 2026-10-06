from pathlib import Path
from urllib.request import urlopen, Request
import json, math, time
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'research/short_p4_underdogs_2026_10_05'
OUT=Path(__file__).resolve().parent
OUT.mkdir(parents=True, exist_ok=True)
df=pd.read_csv(BASE/'game_details.csv')
sel=df[df['turnover_margin'].ne('Missing')].copy()

schedules={}
for season in sorted(sel.season.unique()):
    u='https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_'+str(int(season))+'.csv'
    schedules[int(season)]=pd.read_csv(u, low_memory=False)

def fetch_json(url):
    req=Request(url, headers={'User-Agent':'Mozilla/5.0'})
    with urlopen(req,timeout=25) as r:
        return json.load(r)

def side_spread(payload, side):
    ps=(payload.get('pointSpread') or {}).get(side,{})
    close=(ps.get('close') or {}).get('line')
    if close is not None:
        try:return float(str(close).replace('+','').replace('−','-'))
        except:pass
    team_odds=payload.get(side+'TeamOdds') or {}
    fav=team_odds.get('favorite'); dog=team_odds.get('underdog')
    raw=payload.get('spread')
    try: mag=abs(float(raw))
    except: mag=None
    if mag is not None:
        if fav is True:return -mag
        if dog is True:return mag
    details=str(payload.get('details') or '').strip()
    if details:
        try:
            fav_line=float(details.split()[-1].replace('−','-'))
            if fav is True:return fav_line if fav_line<0 else -abs(fav_line)
            if dog is True:return abs(fav_line)
        except:pass
    return math.nan

rows=[]; errors=[]
for rec in sel.to_dict('records'):
    season=int(rec['season']); gid=int(rec['game_id'])
    game=schedules[season][pd.to_numeric(schedules[season].game_id,errors='coerce').eq(gid)]
    if len(game)!=1:
        errors.append({'game_id':gid,'error':'schedule match'}); continue
    g=game.iloc[0]
    if rec['underdog']==g.get('home_team'): side='home'
    elif rec['underdog']==g.get('away_team'): side='away'
    else:
        errors.append({'game_id':gid,'error':'team match'}); continue
    try:
        payload=fetch_json(rec['url']); spread=side_spread(payload,side)
        if not math.isfinite(spread):
            summary=fetch_json('https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary?event='+str(gid))
            for candidate in summary.get('pickcenter',[]):
                candidate_spread=side_spread(candidate,side)
                if math.isfinite(candidate_spread):
                    payload=candidate; spread=candidate_spread; break
    except Exception as e:
        payload={}; spread=math.nan; errors.append({'game_id':gid,'error':repr(e)})
    try:
        hp=float(g['home_points']); ap=float(g['away_points']); margin=(hp-ap) if side=='home' else (ap-hp)
    except Exception:
        margin=math.nan
    ats=margin+spread if math.isfinite(spread) and math.isfinite(margin) else math.nan
    ats_result='W' if ats>1e-9 else 'L' if ats<-1e-9 else 'P' if math.isfinite(ats) else 'Missing'
    out=dict(rec)
    out.update({'dog_side':side,'dog_spread':spread,'ats_margin':ats,'ats_result':ats_result,
                'turnover_edge':float(rec['dog_to_margin'])-float(rec['fav_to_margin']),
                'odds_details':payload.get('details'),'odds_spread_raw':payload.get('spread'),
                'provider_name':(payload.get('provider') or {}).get('name',rec.get('source'))})
    rows.append(out)
    time.sleep(.03)

out=pd.DataFrame(rows)
out.to_csv(OUT/'tier2_game_validation.csv',index=False)
pd.DataFrame(errors).to_csv(OUT/'fetch_errors.csv',index=False)

def summary(frame):
    n=len(frame); ml_w=int(frame.win.sum())
    ats=frame[frame.ats_result.isin(['W','L','P'])]
    aw=int((ats.ats_result=='W').sum()); al=int((ats.ats_result=='L').sum()); ap=int((ats.ats_result=='P').sum())
    return {'games':n,'ml_w':ml_w,'ml_l':n-ml_w,'ml_win_rate':ml_w/n if n else None,
            'ml_profit_10':round(float(frame.profit.sum()),2),'ml_roi':float(frame.profit.sum())/(10*n) if n else None,
            'ats_graded':len(ats),'ats_w':aw,'ats_l':al,'ats_p':ap,
            'ats_win_rate_ex_push':aw/(aw+al) if aw+al else None,'missing_spread':int(frame.dog_spread.isna().sum())}

fixed=out[out.turnover_margin.eq('Advantage')].copy()
report={'fixed_rule':summary(fixed),'by_season':{},'turnover_comparison':{},'secondary_checks':{}}
for y,g in fixed.groupby('season'): report['by_season'][str(int(y))]=summary(g)
for condition,g in out.groupby('turnover_margin'): report['turnover_comparison'][condition]=summary(g)
checks={
 'turnover_edge_ge_0_5':fixed.turnover_edge>=0.5,
 'turnover_edge_ge_1_0':fixed.turnover_edge>=1.0,
 'turnover_edge_ge_1_25':fixed.turnover_edge>=1.25,
 'higher_off_ypc':fixed.offensive_ypc.eq('Advantage'),
 'lower_def_ypc':fixed.defensive_ypc.eq('Advantage'),
 'both_ypc':fixed.offensive_ypc.eq('Advantage') & fixed.defensive_ypc.eq('Advantage')}
for label,mask in checks.items():
    f=fixed[mask]
    report['secondary_checks'][label]={'overall':summary(f),'by_season':{str(int(y)):summary(g) for y,g in f.groupby('season')}}
(OUT/'summary.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))