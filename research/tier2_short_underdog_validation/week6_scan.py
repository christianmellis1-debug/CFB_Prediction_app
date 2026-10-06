from pathlib import Path
from urllib.request import urlopen, Request
import json, math
import pandas as pd
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from matchup_advantages import build_waterfall_profiles, conference_group

SCHED_URL='https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_2026.csv'
BOX_URL='https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_team_box/team_box_2026.csv'
OUT=Path(__file__).resolve().parent/'week6_scan.json'

schedule=pd.read_csv(SCHED_URL,low_memory=False)
boxes=pd.read_csv(BOX_URL,low_memory=False)
profiles=build_waterfall_profiles(schedule,boxes,6)
week=schedule[(schedule.season==2026)&(schedule.season_type.eq('regular'))&(schedule.week==6)].copy()

def get_json(url):
    req=Request(url,headers={'User-Agent':'Mozilla/5.0'})
    with urlopen(req,timeout=25) as r:return json.load(r)

def ml(v):
    if v is None:return None
    try:return int(float(str(v).replace('+','').replace('−','-')))
    except:return None

def quote(event_id):
    p=get_json('https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary?event='+str(event_id))
    options=[]
    for o in p.get('pickcenter',[]):
        name=str((o.get('provider') or {}).get('name','')).strip()
        h=(o.get('moneyline') or {}).get('home',{}); a=(o.get('moneyline') or {}).get('away',{})
        hm=ml((h.get('close') or {}).get('odds')); am=ml((a.get('close') or {}).get('odds'))
        if hm is None:hm=ml((o.get('homeTeamOdds') or {}).get('moneyLine'))
        if am is None:am=ml((o.get('awayTeamOdds') or {}).get('moneyLine'))
        if hm is not None and am is not None:options.append((name,hm,am))
    if not options:return None
    dk=next((x for x in options if x[0].lower().replace(' ','')=='draftkings'),None)
    return dk or options[0]

rows=[]
for _,g in week.iterrows():
    hg=conference_group(g.home_conference,g.home_team); ag=conference_group(g.away_conference,g.away_team)
    if hg!='P4' or ag!='P4':continue
    gid=int(g.game_id)
    q=quote(gid)
    rec=profiles.get(str(gid),{})
    if not q or rec.get('status')!='ok':
        rows.append({'game_id':gid,'away':g.away_team,'home':g.home_team,'status':'missing','quote':q,'profile_status':rec.get('status')});continue
    provider,hm,am=q
    if hm<0<am: fav_side='home'; fav_ml=hm; dog_side='away'; dog_ml=am
    elif am<0<hm: fav_side='away'; fav_ml=am; dog_side='home'; dog_ml=hm
    else:
        rows.append({'game_id':gid,'away':g.away_team,'home':g.home_team,'status':'nonstandard_price','home_ml':hm,'away_ml':am});continue
    dog=rec[dog_side]; fav=rec[fav_side]
    edge=float(dog['margin'])-float(fav['margin'])
    dog_team=g[dog_side+'_team']; fav_team=g[fav_side+'_team']
    qualifies=(-150<=fav_ml<=-110 and edge>=1.0)
    rows.append({'game_id':gid,'away':g.away_team,'home':g.home_team,'provider':provider,'home_ml':hm,'away_ml':am,
                 'favorite':fav_team,'favorite_ml':fav_ml,'underdog':dog_team,'underdog_ml':dog_ml,
                 'dog_turnover_margin':dog['margin'],'fav_turnover_margin':fav['margin'],'turnover_edge':edge,
                 'in_price_window':(-150<=fav_ml<=-110),'qualifies':qualifies,'status':'ok'})

payload={'season':2026,'week':6,'rule':'P4/P4; favorite ML -110 to -150; underdog turnover margin/game at least +1.0 better; pre-Week-6 FBS-only history','qualifiers':[r for r in rows if r.get('qualifies')],'all_p4_games':rows}
OUT.write_text(json.dumps(payload,indent=2))
print(json.dumps(payload,indent=2))