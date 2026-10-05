from pathlib import Path
import pandas as pd,numpy as np,json,hashlib
P=Path(__file__).parent;root=P.parent
spec={'seasons':[2024,2025,2026],'2026_through_week':4,'max_pregame_score_margin':8,'quarters':[1,2,3],'exclude_q2_final_seconds':120,'minimum_prior_close_plays':30,'rush_majority_threshold':0.5,'notes':'All thresholds fixed before inspecting outcome tables. Earlier-week completed FBS games only. Sacks and text-identified scrambles count as dropbacks; kneels, spikes, no-plays, negated plays excluded. Unidentified scrambles may remain in rushing.'}
(P/'specification.json').write_text(json.dumps(spec,indent=2))
d=pd.read_csv(root/'tendency_test/team_details.csv');rows=[];audit=[];gamecounts=[]
cols=['game_id','id','start.pos_team.id','start.pos_score_diff','period','clock.minutes','clock.seconds','rush','pass','sack','kneel_down','penalty_no_play','penalty_negated_play','text']
def flag(s):return s.astype(str).str.lower().isin(['true','1','1.0','t'])
for year,target in d.groupby('season'):
 s=pd.read_csv(root/f'turnover_test/inputs/schedule{year}.csv');s=s[s.season_type.eq('regular')&s.home_division.eq('fbs')&s.away_division.eq('fbs')].copy();s['start']=pd.to_datetime(s.start_date,utc=True);s['done']=flag(s.completed)
 p=pd.read_parquet(P/f'inputs/pbp{year}.parquet',columns=cols);p=p[p.game_id.isin(s.game_id)].copy()
 for col in ['game_id','start.pos_team.id','start.pos_score_diff','period','clock.minutes','clock.seconds']:p[col]=pd.to_numeric(p[col],errors='coerce')
 dup=p.duplicated(['game_id','id'],keep=False);badgames=set(p.loc[dup,'game_id']);p=p[~p.game_id.isin(badgames)]
 text=p.text.fillna('').str.lower();scramble=text.str.contains(r'\bscrambl');sack=flag(p.sack)|text.str.contains(r'\bsacked\b');drop=flag(p['pass'])|sack|scramble;run=flag(p.rush)&~drop
 exclude=flag(p.kneel_down)|text.str.contains(r'kneel|\bspik(?:e|es|ed|ing)\b')|flag(p.penalty_no_play)|flag(p.penalty_negated_play)
 valid=(run|drop)&~exclude&p['start.pos_team.id'].notna();p['run']=run.astype(int);p['drop']=drop.astype(int)
 close=valid&p.period.isin([1,2,3])&p['start.pos_score_diff'].abs().le(8)&~(p.period.eq(2)&(p['clock.minutes']*60+p['clock.seconds']).le(120))&p['clock.minutes'].notna()&p['clock.seconds'].notna()
 full=p[valid].groupby(['game_id','start.pos_team.id'])[['run','drop']].sum();counts=p[close].groupby(['game_id','start.pos_team.id'])[['run','drop']].sum()
 for (gid,tid),r in full.iterrows():
  c=counts.loc[(gid,tid)] if (gid,tid) in counts.index else pd.Series({'run':0,'drop':0})
  gamecounts.append(dict(season=int(year),game_id=int(gid),team_id=int(tid),all_run=int(r.run),all_drop=int(r['drop']),close_run=int(c.run),close_drop=int(c['drop'])))
 audit.append(dict(season=int(year),pbp_games=int(p.game_id.nunique()),duplicated_games=len(badgames),classified_plays=int(valid.sum()),close_plays=int(close.sum()),sacks_in_close=int((close&sack).sum()),identified_scrambles_in_close=int((close&scramble).sum()),excluded_kneels_spikes=int((flag(p.kneel_down)|text.str.contains(r'kneel|\bspik(?:e|es|ed|ing)\b')).sum())))
 for _,r in target.iterrows():
  g=s[s.game_id.eq(r.game_id)].iloc[0];tid=g.home_id if r.side=='home' else g.away_id;past=s[s.done&s.week.lt(r.week)&s.start.lt(g.start)&(s.home_id.eq(tid)|s.away_id.eq(tid))];assert len(past)==r.prior_games
  keys=[(int(gid),int(tid)) for gid in past.game_id];v=r.to_dict();missing=[k for k in keys if k not in full.index];v.update(close_run=0,close_drop=0,close_share=None,close_style='Missing',reason='')
  if missing:v['reason']='Missing prior-game play-by-play'
  else:
   totals=counts.reindex(pd.MultiIndex.from_tuples(keys),fill_value=0).sum();n=int(totals.sum());v.update(close_run=int(totals.run),close_drop=int(totals['drop']))
   if n<30:v['reason']='Fewer than 30 prior close-score plays'
   else:
    share=totals.run/n;v.update(close_share=share,close_style='Run majority' if share>.5 else 'Pass majority' if share<.5 else 'Balanced')
    rush=r.rush_estimate>r.opponent_rush_estimate+1e-10;pas=r.completion_estimate>r.opponent_completion_estimate+1e-10
    v['close_weighted_score']=r.six_score-int(rush)-int(pas)+2*share*int(rush)+2*(1-share)*int(pas)
  rows.append(v)
 print(year,'done',flush=True)
f=pd.DataFrame(rows);f.to_csv(P/'team_details.csv',index=False);pd.DataFrame(gamecounts).to_csv(P/'prior_game_counts.csv',index=False);(P/'audit.json').write_text(json.dumps(audit,indent=2))
valid=f[f.close_share.notna()];print('COVERAGE',len(valid),'of',len(f),f.reason.value_counts().to_dict())
for seasoncols,name in [([], 'pooled'),(['season'],'by_season')]:
 t=valid.groupby(seasoncols+['group','six_score','close_style']).win.agg(games='size',wins='sum');t['losses']=t.games-t.wins;t['rate']=t.wins/t.games;t.to_csv(P/f'{name}.csv')
print(pd.read_csv(P/'pooled.csv').to_string(index=False))
comp=[]
for (year,gid),z in f.groupby(['season','game_id']):
 if z.close_share.isna().any():continue
 h=z[z.side.eq('home')].iloc[0];a=z[z.side.eq('away')].iloc[0];v=dict(season=year,game_id=gid,group=h.group)
 for name,col in [('baseline','six_score'),('overall','weighted_score'),('close','close_weighted_score')]:
  diff=h[col]-a[col];winner=None if abs(diff)<1e-10 else h if diff>0 else a;v[name+'_pick']=None if winner is None else winner.team;v[name+'_win']=None if winner is None else int(winner.win)
 comp.append(v)
g=pd.DataFrame(comp);g.to_csv(P/'comparison.csv',index=False);paired=g.dropna(subset=['baseline_pick','overall_pick','close_pick']);print('PAIRED',paired.groupby(['season','group'])[['baseline_win','overall_win','close_win']].agg(['count','sum']).to_string());print('AUDIT',audit)
