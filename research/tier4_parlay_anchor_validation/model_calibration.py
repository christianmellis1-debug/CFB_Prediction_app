from pathlib import Path
import sys, json
from urllib.request import Request, urlopen
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from model_v1_5 import predict_week
from matchup_advantages import normalize_fbs_schedule

def csv(url):
    with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0 calibration-diagnostic'}),timeout=90) as r:
        return pd.read_csv(r,low_memory=False)

rows=[]
for season in (2024,2025):
    sched=csv(f'https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_{season}.csv')
    cur=csv(f'https://github.com/sportsdataverse/sportsdataverse-data/releases/download/cfb_team_summaries_weekly/cfb_team_summaries_weekly_{season}.csv')
    prior=csv(f'https://github.com/sportsdataverse/sportsdataverse-data/releases/download/cfb_team_summaries_weekly/cfb_team_summaries_weekly_{season-1}.csv')
    s=normalize_fbs_schedule(sched)
    s=s[s.season_type.astype(str).str.lower().eq('regular')]
    for week in sorted(pd.to_numeric(s.week,errors='coerce').dropna().astype(int).unique()):
        pred=predict_week(cur,prior,sched,week,include_completed=True)
        target=s[pd.to_numeric(s.week,errors='coerce').eq(week)]
        outcomes={int(g.game_id):g for _,g in target.iterrows() if pd.notna(g.get('home_points')) and pd.notna(g.get('away_points'))}
        for _,p in pred.iterrows():
            try:gid=int(p['Game ID'])
            except:continue
            g=outcomes.get(gid)
            if g is None:continue
            winner=g.home_team if float(g.home_points)>float(g.away_points) else g.away_team
            rows.append({'season':season,'week':week,'game_id':gid,'confidence':float(p.Confidence),
                         'correct':p['Predicted Winner']==winner})

df=pd.DataFrame(rows)
bins=[(.50,.60),(.60,.70),(.70,.75),(.75,.80),(.80,.85),(.85,.90),(.90,1.000001)]
out={}
for lo,hi in bins:
    g=df[(df.confidence>=lo)&(df.confidence<hi)]
    out[f'{int(lo*100)}-{int(min(hi,1)*100)}']={
        'n':len(g),'accuracy':float(g.correct.mean()) if len(g) else None,
        'mean_confidence':float(g.confidence.mean()) if len(g) else None,
        'by_season':{
            str(y):{
                'n':len(gy),
                'accuracy':float(gy.correct.mean()) if len(gy) else None,
                'mean_confidence':float(gy.confidence.mean()) if len(gy) else None
            } for y,gy in ((y,g[g.season.eq(y)]) for y in (2024,2025))
        }
    }
Path(__file__).with_name('model_confidence_bins.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
