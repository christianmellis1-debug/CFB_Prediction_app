"""Run from GitHub Actions; first observation is immutable, outcomes are separate."""
import hashlib
import json
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen
import pandas as pd
from shadow_inputs import download_schedule, read_summary, augment_missing_summaries, predict_all_games
from shadow_tracking import DATA, EXPERIMENT, load, make_snapshot, settle

def now():
    return datetime.now(timezone.utc)

def fetch(gid):
    url='https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary?event='+str(gid)
    with urlopen(url,timeout=30) as response:
        payload=json.load(response)
    return payload,now().isoformat()

def digest(frame):
    return hashlib.sha256(frame.to_csv(index=False).encode()).hexdigest()

def main():
    log=load()
    if log['experiment']!=EXPERIMENT:
        raise ValueError('Experiment mismatch; never overwrite another experiment')
    year=2026
    schedule=download_schedule(year)
    schedule=schedule[schedule['season_type'].astype(str).str.lower().eq('regular')]
    for col in ('home_division','away_division'):
        schedule=schedule[schedule[col].astype(str).str.lower().eq('fbs')]
    for col in ('week','home_id','away_id','home_points','away_points'):
        schedule[col]=pd.to_numeric(schedule[col],errors='coerce')
    schedule=schedule.dropna(subset=['week','home_id','away_id'])
    schedule=schedule[schedule['week']>=1].sort_values('start_date',kind='stable')
    for col in ('completed','neutral_site'):
        schedule[col]=schedule[col].astype(str).str.lower().isin(['true','t','1','1.0','yes','y'])
    kickoff=pd.to_datetime(schedule['start_date'],utc=True,errors='coerce')
    upcoming=schedule[(kickoff>now()) & (kickoff<=now()+timedelta(days=7))].copy()
    upcoming=upcoming[~upcoming['game_id'].astype(int).astype(str).isin(log['snapshots'])]
    stats=Counter(eligible_schedule_games=len(upcoming))
    picks={}; provenance={}
    if not upcoming.empty:
        current,prior=read_summary(None,year),read_summary(None,year-1)
        source_hashes={'frozen_model_sha256':hashlib.sha256((DATA.parent.parent/'shadow_model_v1_5.py').read_bytes()).hexdigest(),'schedule_sha256':digest(schedule),'current_summary_sha256':digest(current),'prior_summary_sha256':digest(prior)}
        for week in sorted(upcoming['week'].unique()):
            augmented,derived=augment_missing_summaries(current,prior,schedule,int(week))
            frame=predict_all_games(augmented,prior,schedule,int(week))
            for _,pick in frame.iterrows():
                gid=str(int(pick['Game ID'])); picks[gid]=pick
                provenance[gid]=dict(source_hashes,model_version='V1.5',code_commit=os.environ.get('GITHUB_SHA','local-initial-capture'),
                    summary_cutoff_exclusive=int(week),fallback_team_ids=sorted(derived))
    games={str(int(g['game_id'])):g for _,g in upcoming.iterrows()}
    pending={gid for gid in log['snapshots'] if gid not in log['results']}
    ids=sorted(set(games)|pending)
    def request(gid):
        try:
            return gid,fetch(gid),None
        except Exception as exc:
            return gid,None,type(exc).__name__
    with ThreadPoolExecutor(max_workers=6) as pool:
        for gid,response,error in pool.map(request,ids):
            if error:
                stats['fetch_errors']+=1
                continue
            payload,captured=response
            if gid in games and gid in picks:
                try:
                    snapshot=make_snapshot(games[gid],picks[gid],payload,captured,provenance[gid])
                    log['snapshots'].setdefault(gid,snapshot)
                    stats['new_snapshots']+=1
                except (ValueError,KeyError,TypeError) as exc:
                    stats['skipped: '+str(exc)]+=1
            elif gid in games:
                stats['missing_model_prediction']+=1
            if gid in log['snapshots']:
                result=settle(log['snapshots'][gid],payload,captured)
                if result:
                    log['results'][gid]=result
                    stats['new_results']+=1
    log['last_run']=now().isoformat();log['run_summary']=dict(stats)
    DATA.parent.mkdir(parents=True,exist_ok=True)
    temp=DATA.with_suffix('.tmp')
    temp.write_text(json.dumps(log,indent=2,sort_keys=True,allow_nan=False)+'\n')
    temp.replace(DATA)
    print(json.dumps(dict(stats),sort_keys=True))

if __name__=='__main__':
    main()
