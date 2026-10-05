import pandas as pd,json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from urllib.request import urlopen
p=Path(__file__).parent;f=pd.read_csv(p.parent/'neutral_2026_week5/team_results.csv');s=pd.read_csv(p.parent/'neutral_2026_week5/schedule.csv');f=f[f.advantages.eq(6)].merge(s[['game_id','away_team','home_points','away_points']],on='game_id')
def fetch(r):
 url=f'https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary?event={r.game_id}'
 try:
  with urlopen(url,timeout=30) as resp:x=json.load(resp)
 except Exception:
  q=p.parent/f'weekly_performance/week4_odds/{r.game_id}.json'
  if not q.exists():raise
  x=json.loads(q.read_text())
 quotes=x.get('pickcenter',[]);dk=[q for q in quotes if q.get('provider',{}).get('id')=='100'];q=(dk or quotes or [{}])[0]
 ml=q.get('moneyline',{}).get('home',{})
 o=dict(week=int(r.week),group=r.group,team=r.team,opponent=r.away_team,result=('W' if r.win else 'L')+f' {int(r.home_points)}–{int(r.away_points)}',open=ml.get('open',{}).get('odds'),close=ml.get('close',{}).get('odds'),source=q.get('provider',{}).get('name'),url=url,game_id=int(r.game_id))
 (p/f'{r.game_id}.json').write_text(json.dumps({'game_id':int(r.game_id),'url':url,'pickcenter':quotes},indent=2));return o
with ThreadPoolExecutor(5) as ex:rows=list(ex.map(fetch,f.itertuples(index=False)))
d=pd.DataFrame(rows).sort_values(['week','group','team']);d.to_csv(p/'moneylines.csv',index=False);print(d.to_string(index=False))
