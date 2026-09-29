from pathlib import Path
import pandas as pd,numpy as np,json
P=Path(__file__).parent;src=P.parent/'turnover_test';d=pd.read_csv(src/'game_details.csv');out=[]
# Fixed exploratory specification: majority usage at 50%, no threshold search.
# Offense votes weighted 2*own rush/pass share. Defense, turnover and venue remain one vote.
for year,teams in d.groupby('season'):
 s=pd.read_csv(src/f'inputs/schedule{year}.csv');b=pd.read_csv(src/f'inputs/team_box_{year}.csv')
 s=s[s.season_type.eq('regular')&s.home_division.eq('fbs')&s.away_division.eq('fbs')].copy();s['start']=pd.to_datetime(s.start_date,utc=True)
 s['done']=s.completed.astype(str).str.lower().isin(['true','1','1.0','t','yes']);s['neutral']=s.neutral_site.astype(str).str.lower().isin(['true','1','1.0','t','yes'])
 b['pass_att']=pd.to_numeric(b.completionAttempts.astype(str).str.extract(r'^\s*\d+\s*[/−-]\s*(\d+)\s*$')[0]);b=b.set_index(['game_id','team_id']);assert b.index.is_unique
 for _,r in teams.iterrows():
  g=s[s.game_id.eq(r.game_id)].iloc[0];tid=g.home_id if r.side=='home' else g.away_id
  past=s[s.done&s.week.lt(r.week)&s.start.lt(g.start)&(s.home_id.eq(tid)|s.away_id.eq(tid))]
  z=b.loc[[(int(gid),int(tid)) for gid in past.game_id]]
  assert len(z)==r.prior_games and z[['rushingAttempts','pass_att']].notna().all().all()
  run=z.rushingAttempts.sum();pas=z.pass_att.sum();share=run/(run+pas)
  v=r.to_dict();v.update(rush_share=share,style='Run majority' if share>0.5 else 'Pass majority' if share<0.5 else 'Balanced',neutral=bool(g.neutral))
  rush=r.rush_estimate>r.opponent_rush_estimate+1e-10;passing=r.completion_estimate>r.opponent_completion_estimate+1e-10
  v['offense_advantages']='Both' if rush and passing else 'Rush only' if rush else 'Pass only' if passing else 'Neither'
  v['six_score']=r.advantages5+int(r.side=='home' and not g.neutral)
  v['weighted_score']=v['six_score']-int(rush)-int(passing)+2*share*int(rush)+2*(1-share)*int(passing)
  out.append(v)
f=pd.DataFrame(out);f.to_csv(P/'team_details.csv',index=False)
t=f.groupby(['season','group','offense_advantages','style']).agg(teams=('win','size'),wins=('win','sum'));t['losses']=t.teams-t.wins;t['win_rate']=t.wins/t.teams;t.to_csv(P/'by_season.csv')
a=f.groupby(['group','offense_advantages','style']).agg(teams=('win','size'),wins=('win','sum'));a['losses']=a.teams-a.wins;a['win_rate']=a.wins/a.teams;a.to_csv(P/'pooled.csv')
rows=[]
for (year,gid),g in f.groupby(['season','game_id']):
 assert len(g)==2
 h=g[g.side.eq('home')].iloc[0];a=g[g.side.eq('away')].iloc[0]
 row=dict(season=int(year),game_id=int(gid),group=h.group)
 for name,col in [('baseline','six_score'),('weighted','weighted_score')]:
  delta=h[col]-a[col];p=None if abs(delta)<1e-10 else h if delta>0 else a
  row[name+'_pick']=None if p is None else p.team;row[name+'_win']=None if p is None else int(p.win)
 rows.append(row)
g=pd.DataFrame(rows);g.to_csv(P/'game_comparison.csv',index=False)
print('POOLED OFFENSE/STYLE');print(pd.read_csv(P/'pooled.csv').to_string(index=False))
print('PAIRED TEST')
paired=g.dropna(subset=['baseline_pick','weighted_pick'])
print(paired.groupby(['season','group']).agg(games=('game_id','size'),baseline=('baseline_win','sum'),weighted=('weighted_win','sum')).to_string())
print('COVERAGE');print(g.groupby(['season','group']).agg(games=('game_id','size'),baseline=('baseline_pick','count'),weighted=('weighted_pick','count')).to_string())
print('DISAGREEMENTS');q=paired[paired.baseline_pick.ne(paired.weighted_pick)];print(q.groupby(['season','group']).agg(games=('game_id','size'),baseline=('baseline_win','sum'),weighted=('weighted_win','sum')).to_string())
