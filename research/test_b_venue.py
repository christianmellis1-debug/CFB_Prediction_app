"""Research-only Test B. Never edits model_v1_5 or the production app."""
import json, hashlib, math
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
import numpy as np,pandas as pd
from scipy.special import expit, logit
import model_v1_5 as model
from matchup_advantages import normalize_fbs_schedule
ROOT=Path(__file__).resolve().parents[1]
W=[0.,.05,.1,.15,.2,.3,.4]
TYPES=['raw','shrink5','elo','elo_hfa2','elo_hfa4','blend','flat2','flat4']
ALPHA=model.CALIBRATION_SLOPE*1.10
def num(x):
    try:
        x=float(x)
        return x if math.isfinite(x) else None
    except (TypeError,ValueError): return None
def inputs():
    sums={};schedules={};sha={}
    for y in [2023,2024,2025]:
        x=pd.read_csv('https://github.com/sportsdataverse/sportsdataverse-data/releases/download/cfb_team_summaries_weekly/cfb_team_summaries_weekly_'+str(y)+'.csv',low_memory=False)
        x=x[pd.to_numeric(x.season,errors='coerce').eq(y)]
        sums[y]=x
        sha['summary'+str(y)]=hashlib.sha256(pd.util.hash_pandas_object(x[['team_id','through_week','adj_off_epa','adj_def_epa']],index=False).values.tobytes()).hexdigest()
    for y in [2024,2025,2026]:
        raw=pd.read_csv('https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_'+str(y)+'.csv',low_memory=False)
        schedules[y]=normalize_fbs_schedule(raw)
        sha['schedule'+str(y)]=hashlib.sha256(pd.util.hash_pandas_object(raw[['game_id','week','home_id','away_id','home_points','away_points']],index=False).values.tobytes()).hexdigest()
    return sums,schedules,sha
def history(s,week):
    x=s[pd.to_numeric(s.week,errors='coerce').lt(week)]
    x=x[x.completed.astype(str).str.lower().isin(['true','t','1','yes','y']) &
        x.home_points.notna() & x.away_points.notna() &
        x.season_type.astype(str).str.lower().eq('regular')]
    h=defaultdict(list);a=defaultdict(list)
    for _,g in x.iterrows():
        if bool(g.neutral_site):continue
        p,q=num(g.home_points),num(g.away_points)
        if p is None or q is None:continue
        d=p-q
        eh,ea=num(g.home_pregame_elo),num(g.away_pregame_elo)
        residual=d-(eh-ea)/25.-2.5 if eh is not None and ea is not None else None
        h[int(g.home_id)].append((d,residual))
        a[int(g.away_id)].append((-d,-residual if residual is not None else None))
    return h,a
def shrink(x,index,prior):
    vals=[r[index] for r in x if r[index] is not None]
    return float(np.mean(vals))*len(vals)/(len(vals)+prior) if vals else 0.
def signals(g,h,a):
    if bool(g.neutral_site):return {k:0. for k in TYPES}
    hi=h[int(g.home_id)];aw=a[int(g.away_id)]
    raw=(shrink(hi,0,3)-shrink(aw,0,3))/14.
    adjusted=(shrink(hi,1,3)-shrink(aw,1,3))/14.
    return dict(raw=raw,shrink5=(shrink(hi,0,5)-shrink(aw,0,5))/14.,
                elo=adjusted,elo_hfa2=adjusted+2.5/14.,elo_hfa4=adjusted+4./14.,
                blend=.5*(raw+adjusted),flat2=2.5/14.,flat4=4./14.)
def score(rows,k,w):
    if not rows:return None
    y=np.array([r['y'] for r in rows]);p0=np.array([r['p'] for r in rows])
    raw=np.array([r['raw'] for r in rows]); sig=np.array([r[k] for r in rows])
    p=expit(logit(p0)+ALPHA*(w*sig-.2*raw))
    good=(p>=.5)==y; baseline=(p0>=.5)==y
    flip=(p>=.5)!=(p0>=.5)
    ll=-y*np.log(np.clip(p,1e-12,1))-(1-y)*np.log(np.clip(1-p,1e-12,1))
    hc=np.maximum(p,1-p)>=.8
    return {'n':len(rows),'wins':int(good.sum()),'losses':int((~good).sum()),'accuracy':round(float(good.mean()),5),
            'brier':round(float(np.mean((p-y)**2)),6),'logloss':round(float(ll.mean()),6),
            'flipped':int(flip.sum()),'fixed':int((flip&good).sum()),'broken':int((flip&~good).sum()),
            'high_n':int(hc.sum()),'high_wins':int((hc&good).sum())}
def main():
    sums,schedules,sha=inputs()
    archive=json.loads((ROOT/'data/shadow_tracking.json').read_text())
    rows=[]
    for year,s in schedules.items():
        s=s.copy()
        s.week=pd.to_numeric(s.week,errors='coerce')
        s.home_points=pd.to_numeric(s.home_points,errors='coerce')
        s.away_points=pd.to_numeric(s.away_points,errors='coerce')
        completed=s.completed.astype(str).str.lower().isin(['true','t','1','yes','y'])
        done=s[completed & s.home_points.notna() & s.away_points.notna() &
               s.home_points.ne(s.away_points) & s.season_type.astype(str).str.lower().eq('regular')]
        for week in sorted(map(int,done.week.unique())):
            h,a=history(s,week)
            sub=done[done.week.eq(week)]
            if year<2026:
                p=model.predict_week(sums[year],sums[year-1],s,week,include_completed=True)
                probs={str(int(r['Game ID'])):float(r['Home Win %']) for _,r in p.iterrows()}
            for _,g in sub.iterrows():
                gid=str(int(g.game_id))
                if year==2026:
                    locked=archive['snapshots'].get(gid);result=archive['results'].get(gid)
                    if not locked or not result or int(locked.get('week',-1))!=week:continue
                    if not locked.get('captured_at') or not locked.get('kickoff') or locked['captured_at']>=locked['kickoff']:continue
                    if num(result.get('home_score'))!=float(g.home_points) or num(result.get('away_score'))!=float(g.away_points):continue
                    prob=locked['model_probability'] if locked['picked_side']=='home' else 1-locked['model_probability']
                else:prob=probs.get(gid)
                if prob is None or not (0<prob<1):continue
                obj={'year':year,'week':week,'id':gid,'game':str(g.away_team)+' at '+str(g.home_team),
                     'y':int(g.home_points>g.away_points),'p':float(prob),
                     'neutral':bool(g.neutral_site),'prior_home_n':len(h[int(g.home_id)]),
                     'prior_road_n':len(a[int(g.away_id)])}
                obj.update(signals(g,h,a))
                rows.append(obj)
    out={'description':'Test B: pregame opponent-adjusted venue and weight; strict earlier weeks',
         'generated':datetime.now(timezone.utc).isoformat(),
         'premise':'Historical results from pregame Elo residuals, Elo difference /25 points and 2.5 points generic HFA; not fitted to outcomes. Historical baselines reconstructed; 2026 V1.5 originally frozen.',
         'hashes':sha,'weights':W,'families':TYPES,'years':{}}
    for year in [2024,2025,2026]:
        z=[r for r in rows if r['year']==year]
        assert all(all(r[k]==0 for k in TYPES) for r in z if r['neutral'])
        out['years'][str(year)]={'baseline':score(z,'raw',.2),'neutral_n':sum(r['neutral'] for r in z),
           'candidate':{k:{str(w):score(z,k,w) for w in W} for k in TYPES}}
        assert out['years'][str(year)]['candidate']['raw']['0.2']==out['years'][str(year)]['baseline']
    options=out['years']['2024']['candidate']
    _,kind,w=min((v['brier'],k,float(s)) for k,ws in options.items() for s,v in ws.items())
    out['chosen']={'family':kind,'weight':w,'selection':'min 2024 Brier; fixed for all later seasons'}
    out['holdout']={};out['weekly_2026']={};out['flips_2026']=[]
    for year in [2024,2025,2026]:
        r=[x for x in rows if x['year']==year]
        entry={'baseline':score(r,'raw',.2),'chosen':score(r,kind,w),'weeks':{}}
        for name,lo,hi in [('early',1,4),('middle',5,8),('late',9,20)]:
            sub=[x for x in r if lo<=x['week']<=hi]
            if sub:entry['weeks'][name]={'baseline':score(sub,'raw',.2),'chosen':score(sub,kind,w)}
        out['holdout'][str(year)]=entry
    for wk in (5,6):
        group=[r for r in rows if r['year']==2026 and r['week']==wk]
        out['weekly_2026'][str(wk)]={'baseline':score(group,'raw',.2),'chosen':score(group,kind,w)}
    for r in rows:
        if r['year']!=2026:continue
        p=float(expit(logit(r['p'])+ALPHA*(w*r[kind]-.2*r['raw'])))
        if (p>=.5)!=(r['p']>=.5):
            out['flips_2026'].append({'week':r['week'],'game':r['game'],'before':round(r['p'],4),
             'after':round(p,4),'correct':(p>=.5)==r['y']})
    pd.DataFrame(rows).to_csv(ROOT/'research/test_b_venue_games.csv',index=False)
    (ROOT/'research/test_b_venue_results.json').write_text(json.dumps(out,indent=2,allow_nan=False)+'\n')
    print('RESULT_B '+json.dumps({'chosen':out['chosen'],'holdout':out['holdout'],'weekly_2026':out['weekly_2026'],'flips_2026':out['flips_2026']}))
if __name__=='__main__':main()
