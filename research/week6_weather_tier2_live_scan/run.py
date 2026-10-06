from pathlib import Path
from urllib.request import urlopen
from io import BytesIO
import json
import pandas as pd

from backend.main import attach_market_context
from matchup_advantages import build_waterfall_profiles, weather_tier_candidate_ids
from weather_context import build_weather_context

SEASON=2026
WEEK=6
OUT=Path('research/week6_weather_tier2_live_scan')
OUT.mkdir(parents=True,exist_ok=True)

def read_csv(url):
    with urlopen(url,timeout=60) as r:
        return pd.read_csv(BytesIO(r.read()),low_memory=False)

schedule=read_csv(f'https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_{SEASON}.csv')
boxes=read_csv(f'https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_team_box/team_box_{SEASON}.csv')
games=schedule[(pd.to_numeric(schedule['season'],errors='coerce')==SEASON)&(pd.to_numeric(schedule['week'],errors='coerce')==WEEK)].copy()
games=games[games['season_type'].astype(str).str.lower().eq('regular')]

pred=pd.DataFrame({
 'Game ID':pd.to_numeric(games['game_id'],errors='coerce').astype('Int64'),
 'Home Team':games['home_team'].values,
 'Away Team':games['away_team'].values,
 'Predicted Side':['Home']*len(games),
 'Confidence':[0.5]*len(games),
})
pred=attach_market_context(pred,games)
profiles=build_waterfall_profiles(schedule,boxes,WEEK)
candidate_ids=weather_tier_candidate_ids(pred,schedule,profiles)
weather=build_weather_context(schedule,WEEK,candidate_ids)

rows=[]
for gid in candidate_ids:
    p=pred[pd.to_numeric(pred['Game ID'],errors='coerce').eq(gid)]
    g=games[pd.to_numeric(games['game_id'],errors='coerce').eq(gid)]
    if p.empty or g.empty: continue
    p=p.iloc[0]; g=g.iloc[0]; rec=profiles.get(str(gid),{}); wx=weather.get(str(gid),{})
    rows.append({
      'game_id':gid,'away':g['away_team'],'home':g['home_team'],
      'home_spread':p.get('Home Spread'),'spread_odds':p.get('Home Spread Odds'),'spread_source':p.get('Spread Source'),
      'home_def_ypc_allowed':rec.get('home',{}).get('def_run'),'away_def_ypc_allowed':rec.get('away',{}).get('def_run'),
      'home_turnover_margin':rec.get('home',{}).get('margin'),'away_turnover_margin':rec.get('away',{}).get('margin'),
      'weather_status':wx.get('status'),'inclement':wx.get('inclement'),'weather_type':wx.get('weather_type'),
      'precip_mm':wx.get('precip_mm'),'snowfall':wx.get('snowfall'),'max_wind_mph':wx.get('max_wind_mph'),'max_gust_mph':wx.get('max_gust_mph'),
      'qualifies':bool(wx.get('status')=='ok' and wx.get('inclement') is True)
    })

out=pd.DataFrame(rows)
out.to_csv(OUT/'week6_tier2_live_scan.csv',index=False)
payload={
 'season':SEASON,'week':WEEK,'non_weather_candidates':len(candidate_ids),
 'qualifiers':out[out['qualifies'].eq(True)].to_dict('records') if not out.empty else [],
 'candidates':out.to_dict('records') if not out.empty else []
}
(OUT/'week6_tier2_live_scan.json').write_text(json.dumps(payload,indent=2))
print(json.dumps(payload,indent=2))