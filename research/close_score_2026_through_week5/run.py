from pathlib import Path
from urllib.request import urlopen
from concurrent.futures import ThreadPoolExecutor
import sys,json,hashlib
import pandas as pd
P=Path(__file__).parent;sys.path.insert(0,str(P.parent/'six_comparison'))
from matchup_advantages import build_advantages,assess
urls={'schedule.csv':'https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_2026.csv','boxes.csv':'https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_team_box/team_box_2026.csv'}
def fetch(kv):
 k,url=kv
 with urlopen(url,timeout=45) as r:(P/k).write_bytes(r.read())
with ThreadPoolExecutor(2) as e:list(e.map(fetch,urls.items()))
s=pd.read_csv(P/'schedule.csv');s=s[s.season.eq(2026)&s.season_type.eq('regular')&s.home_division.eq('fbs')&s.away_division.eq('fbs')].copy()
for c in ['completed','neutral_site']:s[c]=s[c].astype(str).str.lower().isin(['true','t','1','1.0','yes'])
s['start']=pd.to_datetime(s.start_date,utc=True)
b=pd.read_csv(P/'boxes.csv');c=pd.read_csv(P.parent/'neutral_tendency/prior_game_counts.csv');c=c[c.season.eq(2026)].set_index(['game_id','team_id']);rows=[];audit=[]
for w in range(1,6):
 checks=build_advantages(s,b,w)
 for _,g in s[s.week.eq(w)].iterrows():
  rec=checks[str(int(g.game_id))];audit.append(dict(week=w,game_id=int(g.game_id),status=rec['status'],completed=bool(g.completed)))
  if rec['status']!='ok' or not g.completed:continue
  for side in ['home','away']:
   tid=g[side+'_id'];past=s[s.completed&s.week.lt(w)&s.start.lt(g.start)&(s.home_id.eq(tid)|s.away_id.eq(tid))];keys=[(int(gid),int(tid)) for gid in past.game_id]
   assert len(past)==rec[side+'_games']
   v=dict(week=w,game_id=int(g.game_id),group=rec['group'],team=g[side+'_team'],side=side,advantages=assess(rec,side)['count']+int(side=='home' and not g.neutral_site),win=int((g.home_points>g.away_points)==(side=='home')),style='Missing',reason='',close_run=0,close_drop=0)
   if any(k not in c.index for k in keys):v['reason']='Missing prior-game play-by-play'
   else:
    totals=c.loc[keys,['close_run','close_drop']].sum();v.update(close_run=int(totals.close_run),close_drop=int(totals.close_drop));n=totals.sum()
    if n<30:v['reason']='Fewer than 30 prior close-score plays'
    else:v['style']='Run majority' if totals.close_run>totals.close_drop else 'Pass majority' if totals.close_drop>totals.close_run else 'Balanced'
   rows.append(v)
f=pd.DataFrame(rows);f.to_csv(P/'team_results.csv',index=False);pd.DataFrame(audit).to_csv(P/'coverage.csv',index=False);v=f[f['style'].ne('Missing')];t=v.groupby(['group','advantages','style']).win.agg(games='size',wins='sum');t['losses']=t.games-t.wins;t['rate']=t.wins/t.games;t.to_csv(P/'breakdown.csv');print(t.to_string());print('COVERAGE',len(f),len(v),f.reason.value_counts().to_dict());print('WEEK5',pd.DataFrame(audit).query('week==5').groupby(['status','completed']).size().to_dict());print('WEEKCOUNTS',v.groupby('week').size().to_dict())
(P/'sources.json').write_text(json.dumps(dict(urls=urls,hashes={k:hashlib.sha256((P/k).read_bytes()).hexdigest() for k in urls},pbp_counts_sha256=hashlib.sha256((P.parent/'neutral_tendency/prior_game_counts.csv').read_bytes()).hexdigest()),indent=2))
