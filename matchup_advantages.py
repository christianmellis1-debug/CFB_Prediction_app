"""Four-metric research flag; never modifies model probabilities or selections."""
from html import escape
import numpy as np
import pandas as pd
P4={'ACC','Big Ten','Big 12','SEC'}
G6={'American Athletic','Conference USA','Mid-American','Mountain West','Sun Belt','Pac-12'}
LABELS=('Rushing matchup estimate','Completion matchup estimate','Run defense · YPC allowed','Pass defense · completion allowed')

def conference_group(value, team=None):
    # Treat Notre Dame as P4 for research scope, despite its independent conference.
    if str(team).strip().casefold() == 'notre dame':
        return 'P4'
    return 'P4' if value in P4 else 'G6' if value in G6 else None

def build_advantages(schedule, boxes, week):
    """Earlier-week FBS histories only; incomplete histories are not scored."""
    s=schedule.copy()
    for c in ('week','home_id','away_id','game_id'):
        s[c]=pd.to_numeric(s[c],errors='coerce')
    s=s[s.season_type.astype(str).str.lower().eq('regular') & s.home_division.astype(str).str.lower().eq('fbs') & s.away_division.astype(str).str.lower().eq('fbs')]
    s['start']=pd.to_datetime(s.start_date,utc=True,errors='coerce')
    targets=s[s.week.eq(int(week))]
    b=boxes.copy()
    for c in ('game_id','team_id','rushingYards','rushingAttempts'):
        b[c]=pd.to_numeric(b[c],errors='coerce')
    pairs=b.completionAttempts.astype(str).str.extract(r'^\s*(\d+)\s*[/−-]\s*(\d+)\s*$')
    b['comp']=pd.to_numeric(pairs[0],errors='coerce');b['att']=pd.to_numeric(pairs[1],errors='coerce')
    valid=np.isfinite(b[['rushingYards','rushingAttempts','comp','att']]).all(axis=1)&b.rushingAttempts.gt(0)&b.rushingAttempts.mod(1).eq(0)&b.comp.ge(0)&b.att.ge(b.comp)
    # Ambiguous duplicates make the affected prior game unavailable.
    valid &= ~b.duplicated(['game_id','team_id'],keep=False)
    lookup=b[valid].set_index(['game_id','team_id'])
    completed=s.completed.astype(str).str.lower().isin(['true','t','1','1.0','yes','y'])
    past=s[completed&s.week.lt(int(week))&s.home_points.notna()&s.away_points.notna()]
    out={}
    for _,g in targets.iterrows():
        gid=str(int(g.game_id));hg=conference_group(g.home_conference,g.get('home_team'));ag=conference_group(g.away_conference,g.get('away_team'))
        if hg is None or hg!=ag:
            out[gid]={'status':'outside','reason':'Applies to P4 vs. P4 and G6 vs. G6 only. Notre Dame is treated as P4.'};continue
        if pd.isna(g.start):
            out[gid]={'status':'missing','reason':'Kickoff date unavailable.'};continue
        history=past[past.start.lt(g.start)]
        profiles=[];reason=''
        for tid in (g.home_id,g.away_id):
            games=history[history.home_id.eq(tid)|history.away_id.eq(tid)]
            if games.empty:
                reason='At least one team has no earlier-week FBS game this season.';break
            totals=np.zeros(8)
            for _,old in games.iterrows():
                opp=old.away_id if old.home_id==tid else old.home_id
                keys=[(old.game_id,tid),(old.game_id,opp)]
                if not all(k in lookup.index for k in keys):
                    reason='Earlier-week FBS box scores are incomplete or invalid.';break
                own,other=[lookup.loc[k] for k in keys]
                totals+=np.array([own.rushingYards,own.rushingAttempts,own.comp,own.att,other.rushingYards,other.rushingAttempts,other.comp,other.att])
            if reason:break
            if min(totals[[1,3,5,7]])<=0:
                reason='Not enough rushing or passing attempts to calculate all four metrics.';break
            profiles.append(dict(off_run=totals[0]/totals[1],off_pass=totals[2]/totals[3],def_run=totals[4]/totals[5],def_pass=totals[6]/totals[7],games=len(games)))
        if reason:
            out[gid]={'status':'missing','reason':reason};continue
        h,a=profiles
        hv=[(h['off_run']+a['def_run'])/2,(h['off_pass']+a['def_pass'])/2,h['def_run'],h['def_pass']]
        av=[(a['off_run']+h['def_run'])/2,(a['off_pass']+h['def_pass'])/2,a['def_run'],a['def_pass']]
        out[gid]={'status':'ok','home':hv,'away':av,'home_games':h['games'],'away_games':a['games'],'group':hg}
    return out

def assess(record, side):
    if record.get('status')!='ok':return None
    own=record[side];other=record['away' if side=='home' else 'home']
    deltas=[(x-y)*(1 if i<2 else -1) for i,(x,y) in enumerate(zip(own,other))]
    outcomes=['Advantage' if v>1e-10 else 'Tied' if abs(v)<=1e-10 else 'Disadvantage' for v in deltas]
    count=outcomes.count('Advantage')
    return dict(count=count,flag=count<=1,outcomes=outcomes)

def advantage_html(record, side, picked_team):
    status=record.get('status')
    if status!='ok':
        label='Not assessed' if status=='outside' else 'Not enough data'
        return '<details class="card-details"><summary>Advantage check · '+label+'</summary><p>'+escape(record.get('reason','Pregame box scores unavailable.'))+'</p></details>'
    scored=assess(record,side);count=scored['count'];team=escape(str(picked_team))
    banner=(f'<div style="margin-top:10px;padding:10px 12px;border-left:4px solid #e9a23b;border-radius:6px;background:#e9a23b18"><strong>⚠ Matchup risk · {count}/4 advantages</strong><br><span>{team} has limited support from these four metrics.</span></div>' if scored['flag'] else '')
    other='away' if side=='home' else 'home';items=[]
    for i,label in enumerate(LABELS):
        fmt=(lambda x:f'{x:.1%}') if i in (1,3) else (lambda x:f'{x:.2f} YPC')
        direction='higher is better' if i<2 else 'lower is better'
        items.append(f'<li><strong>{label}</strong>: {fmt(record[side][i])} vs {fmt(record[other][i])} · {scored["outcomes"][i]} ({direction})</li>')
    return banner+f'<details class="card-details"><summary>Four-metric check · {count}/4 advantages</summary><p>Values compare {team} with its opponent.</p><ul>'+''.join(items)+f'</ul><p>Earlier-week FBS games: pick {record[side+"_games"]}, opponent {record[other+"_games"]}. Rates use total yards/completions divided by total attempts. Ties do not count as advantages.</p><p>This research flag is not a loss probability. Metrics overlap, and no flag does not mean a safe bet. Current model confidence and value labels are unchanged.</p></details>'
