from pathlib import Path
import sys,json,math
import pandas as pd
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from matchup_advantages import build_waterfall_profiles, normalize_fbs_schedule
SEASONS=[2024,2025,2026]
def truthy(s):return s.astype(str).str.lower().isin(['true','t','1','1.0','yes','y'])
report={}
for season in SEASONS:
    print('season',season,flush=True)
    s0=pd.read_csv(f'https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_{season}.csv',low_memory=False)
    boxes=pd.read_csv(f'https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_team_box/team_box_{season}.csv',low_memory=False)
    s=normalize_fbs_schedule(s0).copy()
    for col in ('season','week','game_id','home_id','away_id'):s[col]=pd.to_numeric(s[col],errors='coerce')
    s=s.dropna(subset=['week','game_id','home_id','away_id'])
    completed=truthy(s.completed)
    cols=['game_id','team_id','rushingYards','rushingAttempts','turnovers','fumblesLost','interceptions']
    b=boxes[cols].apply(pd.to_numeric,errors='coerce')
    valid=np.isfinite(b).all(axis=1)&~b.duplicated(['game_id','team_id'],keep=False)
    valid&=b.rushingAttempts.gt(0)&b.rushingAttempts.mod(1).eq(0)
    tos=b[['turnovers','fumblesLost','interceptions']]
    valid&=tos.ge(0).all(axis=1)&tos.mod(1).eq(0).all(axis=1)&b.turnovers.eq(b.fumblesLost+b.interceptions)
    lookup=b[valid].set_index(['game_id','team_id'])
    totals={};history_ok={};fast={}
    maxweek=5 if season==2026 else int(s.week.max())
    for week in range(0,maxweek+1):
        for _,g in s[s.week.eq(week)].iterrows():
            rec={'status':'missing'};sp={}
            for side in ('home','away'):
                tid=int(g[side+'_id']);t=totals.get(tid)
                if history_ok.get(tid,True) and t and t[4]>0 and t[1]>0 and t[3]>0:
                    sp[side]={'off_run':t[0]/t[1],'def_run':t[2]/t[3],'margin':(t[6]-t[5])/t[4],'games':t[4]}
            if len(sp)==2:rec.update(status='ok',**sp)
            fast[str(int(g.game_id))]=rec
        for _,g in s[s.week.eq(week)&completed].iterrows():
            hid,aid,gid=int(g.home_id),int(g.away_id),int(g.game_id);keys=[(gid,hid),(gid,aid)]
            if not all(k in lookup.index for k in keys):
                history_ok[hid]=False;history_ok[aid]=False;continue
            h,a=lookup.loc[keys[0]],lookup.loc[keys[1]]
            for tid,own,opp in [(hid,h,a),(aid,a,h)]:
                t=totals.setdefault(tid,[0.,0.,0.,0.,0,0.,0.])
                t[0]+=float(own.rushingYards);t[1]+=float(own.rushingAttempts);t[2]+=float(opp.rushingYards);t[3]+=float(opp.rushingAttempts);t[4]+=1;t[5]+=float(own.turnovers);t[6]+=float(opp.turnovers)
    diffs=[];counts={'exact_ok':0,'fast_ok':0,'status_mismatch':0,'value_mismatch':0,'compared':0}
    for week in range(0,maxweek+1):
        exact=build_waterfall_profiles(s0,boxes,week)
        for gid,e in exact.items():
            f=fast.get(gid,{'status':'missing'});counts['compared']+=1
            counts['exact_ok']+=e.get('status')=='ok';counts['fast_ok']+=f.get('status')=='ok'
            if (e.get('status')=='ok')!=(f.get('status')=='ok'):counts['status_mismatch']+=1;diffs.append({'gid':gid,'week':week,'type':'status','exact':e.get('status'),'fast':f.get('status')});continue
            if e.get('status')=='ok':
                bad=False
                for side in ('home','away'):
                    for k in ('off_run','def_run','margin'):
                        if not math.isclose(float(e[side][k]),float(f[side][k]),rel_tol=1e-12,abs_tol=1e-12):bad=True
                if bad:counts['value_mismatch']+=1;diffs.append({'gid':gid,'week':week,'type':'values','exact':e,'fast':f})
    report[str(season)]={'counts':counts,'examples':diffs[:20]}
    print(json.dumps(report[str(season)],indent=2),flush=True)
Path('research/weather_ypc_validation/profile_method_check.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))