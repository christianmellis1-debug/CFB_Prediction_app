from pathlib import Path
from datetime import datetime,timezone
from urllib.request import urlopen
from concurrent.futures import ThreadPoolExecutor
import json,ast,hashlib
import pandas as pd,numpy as np
import model_v1_5 as model
from matchup_advantages import build_advantages,assess,conference_group
P=Path(__file__).parent
if (P/'comparison.json').exists():
    raise SystemExit('Refusing to overwrite the frozen comparison. Run in a separate directory for a new experiment.')
urls={'schedule2026.csv':'https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_2026.csv','team_box_2026.csv':'https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_team_box/team_box_2026.csv','summary2026.csv':'https://github.com/sportsdataverse/sportsdataverse-data/releases/download/cfb_team_summaries_weekly/cfb_team_summaries_weekly_2026.csv','summary2025.csv':'https://github.com/sportsdataverse/sportsdataverse-data/releases/download/cfb_team_summaries_weekly/cfb_team_summaries_weekly_2025.csv'}
def fetch(item):
 name,url=item
 with urlopen(url,timeout=45) as r:data=r.read()
 (P/'inputs'/name).write_bytes(data)
 return name,len(data)
print(list(ThreadPoolExecutor(4).map(fetch,urls.items())),flush=True)
ns={'pd':pd,'np':np,'predict_week':model.predict_week}
names=['augment_missing_summaries','predict_all_games']
a=ast.parse((P/'app.py').read_text())
for name in names:
 f=next(n for n in a.body if isinstance(n,ast.FunctionDef) and n.name==name);f.decorator_list=[]
 exec(compile(ast.Module(body=[f],type_ignores=[]),'production_functions','exec'),ns)
s=pd.read_csv(P/'inputs/schedule2026.csv');s=s[s.season.eq(2026)&s.season_type.eq('regular')&s.home_division.eq('fbs')&s.away_division.eq('fbs')].copy()
for c in ['neutral_site','completed']:s[c]=s[c].astype(str).str.lower().isin(['true','t','1','1.0','yes'])
s=s.sort_values('start_date',kind='stable');assert s.game_id.is_unique
b=pd.read_csv(P/'inputs/team_box_2026.csv');cur=pd.read_csv(P/'inputs/summary2026.csv');prior=pd.read_csv(P/'inputs/summary2025.csv')
rows=[];capture=datetime.now(timezone.utc).isoformat()
for w in range(1,6):
 aug,derived=ns['augment_missing_summaries'](cur,prior,s,w)
 pred=ns['predict_all_games'](aug,prior,s,w)
 checks=build_advantages(s,b,w)
 for _,g in s[s.week.eq(w)].iterrows():
  if w==5:assert pd.Timestamp(g.start_date)>pd.Timestamp(capture) and not g.completed
  p=pred[pred['Game ID'].astype(int).eq(int(g.game_id))];assert len(p)==1;p=p.iloc[0]
  rec=checks[str(int(g.game_id))]
  row=dict(game_id=int(g.game_id),week=w,kickoff=g.start_date,home=g.home_team,away=g.away_team,neutral=bool(g.neutral_site),group=conference_group(g.home_conference,g.home_team) if conference_group(g.home_conference,g.home_team)==conference_group(g.away_conference,g.away_team) else None,app_pick=p['Predicted Winner'],app_home_probability=float(p['Home Win %']),app_confidence=float(p.Confidence),status=rec['status'],reason=rec.get('reason'),six_pick=None,home_advantages=None,away_advantages=None,home_metrics=None,away_metrics=None,winner=(g.home_team if g.home_points>g.away_points else g.away_team if g.away_points>g.home_points else None) if g.completed else None)
  if rec['status']=='ok':
   h=assess(rec,'home')['count']+(not g.neutral_site);a=assess(rec,'away')['count']
   row.update(home_advantages=int(h),away_advantages=int(a),home_metrics=rec['home'],away_metrics=rec['away'],six_pick=g.home_team if h>a else g.away_team if a>h else None)
   if h==a:row['reason']='Equal advantage count: no pick'
  row['app_correct']=row['app_pick']==row['winner'] if row['winner'] else None
  row['six_correct']=row['six_pick']==row['winner'] if row['winner'] and row['six_pick'] else None
  rows.append(row)
(P/'comparison.json').write_text(json.dumps(dict(captured_at=capture,method='Equal-weight five statistical advantages plus home venue; neutral venue awards neither; metric ties award neither; equal total means no pick. P4/P4 and G6/G6 only; Notre Dame P4. Earlier-week current-season FBS histories.',historical_label='Retrospective reconstruction, not picks frozen before those historical kickoffs.',inputs={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (P/'inputs').glob('*.csv')},rows=rows),indent=2,allow_nan=False))
d=pd.DataFrame(rows);hist=d[d.week.le(4)&d.winner.notna()];same=hist[hist.six_pick.notna()]
print('COVERAGE',len(hist),'same group',len(hist[hist.status.ne('outside')]),'assessed',len(hist[hist.status.eq('ok')]),'paired',len(same))
for key,g in same.groupby(['week','group']):print('PAIR',key,len(g),int(g.app_correct.sum()),int(g.six_correct.sum()))
for key,g in same.groupby('group'):print('TOTAL',key,len(g),int(g.app_correct.sum()),int(g.six_correct.sum()))
for key,g in same.groupby(same.app_pick.eq(same.six_pick)):print('AGREEMENT',key,len(g),int(g.app_correct.sum()),int(g.six_correct.sum()))
for key,g in hist[hist.status.ne('outside')].groupby('week'):print('SCOPE',key,len(g),g.status.value_counts().to_dict(),'no pick',len(g[g.status.eq('ok')&g.six_pick.isna()]))
f=d[d.week.eq(5)];print('WEEK5',len(f),f.status.value_counts().to_dict(),'picks',f.six_pick.notna().sum(),'equal',len(f[f.status.eq('ok')&f.six_pick.isna()]))
print(f[f.six_pick.notna()&f.six_pick.ne(f.app_pick)][['home','away','group','app_pick','six_pick','home_advantages','away_advantages']].to_string(index=False))
