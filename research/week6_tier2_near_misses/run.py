from pathlib import Path
import sys, json
from urllib.request import urlopen
from io import BytesIO
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from backend.main import attach_market_context
from matchup_advantages import build_waterfall_profiles, normalize_fbs_schedule
from weather_context import build_weather_context

SEASON=2026; WEEK=6
OUT=ROOT/'research/week6_tier2_near_misses'; OUT.mkdir(parents=True,exist_ok=True)
def csv(url):
    with urlopen(url,timeout=60) as r:return pd.read_csv(BytesIO(r.read()),low_memory=False)
schedule=csv(f'https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_{SEASON}.csv')
boxes=csv(f'https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_team_box/team_box_{SEASON}.csv')
games=normalize_fbs_schedule(schedule)
games=games[(pd.to_numeric(games.week,errors='coerce')==WEEK)&games.season_type.astype(str).str.lower().eq('regular')].copy()
pred=pd.DataFrame({'Game ID':pd.to_numeric(games.game_id,errors='coerce').astype('Int64'),'Home Team':games.home_team.values,'Away Team':games.away_team.values,'Predicted Side':['Home']*len(games),'Confidence':[0.5]*len(games)})
pred=attach_market_context(pred,games)
profiles=build_waterfall_profiles(schedule,boxes,WEEK)

rows=[]
for _,g in games.iterrows():
    gid=str(int(g.game_id)); rec=profiles.get(gid,{})
    if rec.get('status')!='ok':continue
    neutral=str(g.get('neutral_site','')).lower() in ('true','t','1','1.0','yes','y')
    football=(not neutral and rec['home']['def_run']<rec['away']['def_run'] and rec['home']['margin']>rec['away']['margin'])
    if not football:continue
    p=pred[pd.to_numeric(pred['Game ID'],errors='coerce').eq(int(gid))].iloc[0]
    spread=p.get('Home Spread')
    try:s=float(str(spread).replace('+',''))
    except:s=None
    rows.append({'game_id':int(gid),'away':g.away_team,'home':g.home_team,'home_spread':spread,'spread_source':p.get('Spread Source'),
                 'spread_gate':bool(s is not None and s>-14),'home_def_ypc_allowed':rec['home']['def_run'],'away_def_ypc_allowed':rec['away']['def_run'],
                 'home_turnover_margin':rec['home']['margin'],'away_turnover_margin':rec['away']['margin']})

ids=[r['game_id'] for r in rows]
weather=build_weather_context(schedule,WEEK,ids) if ids else {}
for r in rows:
    wx=weather.get(str(r['game_id']),{})
    r.update(weather_status=wx.get('status'),inclement=wx.get('inclement'),weather_type=wx.get('weather_type'),
             condition=wx.get('condition'),precip_mm=wx.get('precip_mm'),max_wind_mph=wx.get('max_wind_mph'),max_gust_mph=wx.get('max_gust_mph'))
    r['qualifies_now']=bool(r['spread_gate'] and wx.get('status')=='ok' and wx.get('inclement') is True)
(OUT/'near_misses.json').write_text(json.dumps(rows,indent=2))
print(json.dumps(rows,indent=2))