"""Temporal evaluation: fit 2022–23, choose on 2024, evaluate 2025.
2025 is held out from this parameter fit, but was inspected in the earlier audit.
No production mutation. Reads scheduleYYYY.csv and summaryYYYY.csv at root.
"""
import ast, hashlib, json, sys, types
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.special import expit, logit
from scipy.optimize import minimize_scalar
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from conference_audit import normalize, metrics

BASE=(ROOT/'backtests/model_v1_4_reference.py').read_text()
OLD='''            if fallback and fallback in x.columns:
                v = v.where(v.notna(), pd.to_numeric(x[fallback], errors="coerce"))
            z[key] = _zscore(v * sign)'''
NEW='''            z[key] = _zscore(v * sign)
            if fallback and fallback in x.columns:
                fallback_z = _zscore(pd.to_numeric(x[fallback], errors="coerce") * sign)
                z[key] = z[key].where(v.notna(), fallback_z)'''
RAW='''            if fallback and fallback in x.columns:
                v = pd.to_numeric(x[fallback], errors="coerce")
            z[key] = _zscore(v * sign)'''
P={'ACC','Big Ten','Big 12','SEC'}
G={'American Athletic','Conference USA','Mid-American','Mountain West','Sun Belt'}

def model(mode):
    m=types.ModuleType('research_model')
    assert OLD in BASE
    exec(BASE if mode=='baseline' else BASE.replace(OLD,NEW if mode=='separate_z' else RAW),m.__dict__)
    return m

def build(year,mode):
    cache=ROOT/f'backtests/extended_{mode}_{year}.csv'
    if cache.exists():return pd.read_csv(cache)
    m=model(mode);s=normalize(pd.read_csv(ROOT/f'schedule{year}.csv'))
    cur=pd.read_csv(ROOT/f'summary{year}.csv',low_memory=False)
    prior=pd.read_csv(ROOT/f'summary{year-1}.csv',low_memory=False)
    tree=ast.parse((ROOT/'app.py').read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='augment_missing_summaries')
    ns={'pd':pd};exec(compile(ast.Module(body=[fn],type_ignores=[]),'app.py','exec'),ns)
    out=[]
    for w in sorted(s.week.unique()):
        c,_=ns['augment_missing_summaries'](cur,prior,s,w)
        out.append(m.predict_week(c,prior,s,int(w),include_completed=True))
    d=pd.concat(out).merge(s,left_on='Game ID',right_on='game_id',validate='one_to_one')
    d=d[d.completed & d.home_points.notna() & d.away_points.notna() & d.home_points.ne(d.away_points)].copy()
    power=P|({'Pac-12'} if year<=2023 else set())
    d['sign']=np.select([d.home_conference.isin(power)&d.away_conference.isin(G),d.away_conference.isin(power)&d.home_conference.isin(G)],[1,-1],default=0)
    d['y']=(d.home_points>d.away_points).astype(int);d['p']=d['Home Win %']
    d.to_csv(cache,index=False)
    return d

def score(d):
    return {'all':metrics(d,'p'),'cross':metrics(d[d.sign.ne(0)],'p')}

def acceptable(candidate,baseline):
    # Require improvement in both proper scoring rules, and limit accuracy loss.
    return all(candidate[k]['brier']<baseline[k]['brier'] and candidate[k]['log_loss']<baseline[k]['log_loss'] for k in ['all','cross']) and candidate['all']['accuracy']>=baseline['all']['accuracy']-.01 and candidate['cross']['accuracy']>=baseline['cross']['accuracy']-.03

def main():
    frames={mode:{y:build(y,mode) for y in [2022,2023,2024,2025]} for mode in ['baseline','separate_z','raw_only']}
    result={'design':'2022–23 fitting; 2024 selection; 2025 evaluation. Previously examined 2025 is not a pristine holdout.', 'baseline':{y:score(d) for y,d in frames['baseline'].items()},'candidates':[]}
    for mode in frames:
        train=pd.concat([frames[mode][2022],frames[mode][2023]]);train=train[train.sign.ne(0)]
        def loss(b):
            q=expit(logit(train.p)+b*train.sign)
            return float(np.mean(-train.y*np.log(q)-(1-train.y)*np.log1p(-q)))
        fitted=float(minimize_scalar(loss,bounds=(-3,3),method='bounded').x)
        for shrink in [0,.5,1]:
            if mode=='baseline' and shrink==0:continue
            row={'mode':mode,'shrink':shrink,'offset':fitted*shrink,'scores':{}}
            for year in [2024,2025]:
                d=frames[mode][year].copy();d['p']=expit(logit(d.p)+row['offset']*d.sign);row['scores'][year]=score(d)
            row['passes_2024']=acceptable(row['scores'][2024],result['baseline'][2024]);result['candidates'].append(row)
    eligible=[r for r in result['candidates'] if r['passes_2024']]
    selected=min(eligible,key=lambda r:r['scores'][2024]['all']['brier']) if eligible else None
    result['selected']=selected
    result['passes_2025']=bool(selected and acceptable(selected['scores'][2025],result['baseline'][2025]))
    if selected:
        d=frames[selected['mode']][2025].copy();d['p']=expit(logit(d.p)+selected['offset']*d.sign)
        base=frames['baseline'][2025].set_index('game_id').loc[d.game_id]
        delta=(d.p.to_numpy()-d.y.to_numpy())**2-(base.p.to_numpy()-base.y.to_numpy())**2
        rng=np.random.default_rng(20260918)
        boot=[float(rng.choice(delta,size=len(delta),replace=True).mean()) for _ in range(3000)]
        result['brier_difference_bootstrap_95']=np.quantile(boot,[.025,.975]).tolist()
        result['bootstrap_note']='Game-level resampling ignores team/week dependence; descriptive uncertainty only.'
    result['sources']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for pattern in ['schedule202[2345].csv','summary202[12345].csv'] for p in ROOT.glob(pattern)}
    (ROOT/'backtests/extended_results.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
