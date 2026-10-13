"""Research-only evaluation of the frozen Test C blend in 2024 and 2025.

No model tuning or production writes. Match V1.5's current retrospective
reconstruction to single-book historical ESPN BET opening and closing prices.
Evaluate matched games fairly; independently measure price coverage and V1.5
fallback on unpriced games. This is NOT a prospective test: source summaries
were republished/revised after historical kickoffs.
"""
import json
from pathlib import Path
from datetime import datetime,timezone

import numpy as np
import pandas as pd
from scipy.stats import binomtest

ROOT=Path(__file__).resolve().parents[1]
PINNED_HISTORICAL_ODDS=(
    "https://raw.githubusercontent.com/christianmellis1-debug/CFB_Prediction_app/"
    "17a68114f48a4308d1e8312296537d701a65047b/"
    "research/test_c_historical_validation_games.csv"
)
PINNED_MODEL=(
    "https://raw.githubusercontent.com/christianmellis1-debug/CFB_Prediction_app/"
    "44e7a7cb474e9c19a1af1bfa4774309e6b46b3e6/"
    "research/test_b_venue_games.csv"
)
MODEL_WEIGHT=0.16927926947215113
OUT=ROOT/"research/test_c_blend_2024_2025_results.json"
DETAIL=ROOT/"research/test_c_blend_2024_2025_games.csv"
BOOTS=5000

def metrics(df,pcol):
    if df.empty:return None
    y=df.y.to_numpy(dtype=int)
    p=df[pcol].to_numpy(dtype=float)
    assert np.all((0<p)&(p<1))
    right=(p>=.5)==y
    eps=1e-12
    p=np.clip(p,eps,1-eps)
    return dict(n=len(df),wins=int(right.sum()),losses=int((~right).sum()),
       accuracy=round(float(right.mean()),6),
       brier=round(float(np.mean((p-y)**2)),6),
       log_loss=round(float(np.mean(-y*np.log(p)-(1-y)*np.log(1-p))),6))

def comparison(df):
    if df.empty:return None
    base=metrics(df,'model_home')
    market=metrics(df,'market_home')
    blend=metrics(df,'blend_home')
    prior=df.model_home.ge(.5)
    challenger=df.blend_home.ge(.5)
    fix=int((prior.ne(challenger)&challenger.eq(df.y.astype(bool))).sum())
    broken=int((prior.ne(challenger)&challenger.ne(df.y.astype(bool))).sum())
    changed=fix+broken
    bdiff=float(np.mean((df.model_home-df.y)**2-(df.blend_home-df.y)**2))
    ldiff=float(np.mean(
      -df.y*np.log(df.model_home)-(1-df.y)*np.log(1-df.model_home)
      +df.y*np.log(df.blend_home)+(1-df.y)*np.log(1-df.blend_home)
    ))
    return dict(v15=base,market=market,blend=blend,
       additional_winners=blend['wins']-base['wins'],
       accuracy_lift_pp=round(100*(blend['wins']-base['wins'])/len(df),5),
       improved_brier=round(bdiff,6),improved_log_loss=round(ldiff,6),
       switches=changed,fixes=fix,breaks=broken,
       paired_two_sided_p=round(float(binomtest(fix,changed,.5).pvalue),7) if changed else 1.)

def bootstrap(df,seed=20261013,rep=BOOTS):
    """Cluster over weeks within each year; preserve season distribution."""
    rng=np.random.default_rng(seed)
    years=sorted(int(y) for y in df.year.unique())
    groups={}
    for y in years:
        a=df[df.year.eq(y)]
        groups[y]=[a[a.week.eq(w)] for w in sorted(a.week.unique())]
    acc=[];brier=[]
    for _ in range(rep):
        bits=[]
        for y in years:
            weekly=groups[y]
            idx=rng.integers(0,len(weekly),size=len(weekly))
            bits += [weekly[int(k)] for k in idx]
        sample=pd.concat(bits)
        obs=comparison(sample)
        acc.append(obs['accuracy_lift_pp'])
        brier.append(obs['improved_brier'])
    def ci(a):return [round(float(q),6) for q in np.quantile(a,[.025,.975])]
    return {'method':'Week-cluster bootstrap, stratified by season, 5000 fixed-seed replicates',
            'accuracy_lift_pp_95_ci':ci(acc),'brier_improvement_95_ci':ci(brier),
            'note':'Week clustering does not fully capture dependence across repeated teams; descriptive only.'}

def main():
    hist=pd.read_csv(PINNED_HISTORICAL_ODDS,low_memory=False)
    base=pd.read_csv(PINNED_MODEL,low_memory=False)
    base=base[base.year.isin([2024,2025])]
    assert not base.duplicated(['year','id']).any()
    assert len(base)==1514 and set(base.year)=={2024,2025}
    assert not hist.duplicated(['year','id','odds_source']).any()
    assert not hist[['model_home','market_home','y']].isna().any().any()
    df=hist.merge(base[['year','week','id','p','y']],
       on=['year','id'],how='left',validate='many_to_one',indicator=True,suffixes=('','_recon'))
    assert df['_merge'].eq('both').all()
    assert (df.week==df.week_recon).all()
    assert (df.y==df.y_recon).all()
    assert np.allclose(df.model_home,df.p,atol=1e-9,rtol=0)
    df['blend_home']=MODEL_WEIGHT*df.model_home+(1-MODEL_WEIGHT)*df.market_home
    assert df.blend_home.between(0,1,inclusive='neither').all()
    results={
        'title':'Test C frozen 16.93% V1.5 / 83.07% market vs V1.5 for 2024 and 2025',
        'created_utc':datetime.now(timezone.utc).isoformat(),
        'model_weight':MODEL_WEIGHT,
        'source_urls':{'model':PINNED_MODEL,'archived_odds':PINNED_HISTORICAL_ODDS},
        'data_provenance':{
          'model':'Retrospective reconstruction of current V1.5 using currently published 2024/2025 weekly summaries; NOT recorded pregame forecast',
          'market':'ESPN BET historical open odds, same bookmaker for both sides, removed margin; recorded in ESPN archived game JSON; quote timing not independently authenticated',
          'cohort':'1,514 reconstructed games; primary matched cohort requires usable same-book opening lines',
          'decision':'No production update unless improvement in winners is reliably demonstrated and independent from previously-used fitting years',
        },
        'season':{},'combined':{},'windows':{},'robustness':{},'coverage':{},
        'risk_notes':[
          'Sportsbook information dominates the blend, so probability cannot be interpreted as an independent betting edge over the same sportsbook.',
          'Winner improvement is a paired outcome from the same games; statistically inconclusive when p>=0.05 or interval crosses 0.',
          'ESPN BET historical odds are not DraftKings; deployment performance may depend on provider and capture time.',
          '2024 and 2025 model predictions were reconstructed after games, and 2025 was used in earlier model development.',
          'Missing lines are not random; all comparisons of priced matches use the EXACT same game cohort.',
          'Do not alter tiers/waterfall selections, value scoring, live app model, or other production pathways on this basis.'
        ]}
    for source in ['primary_open','primary_close','fallback_open']:
        src=df[df.odds_source.eq(source)]
        results['robustness'][source]={'combined':comparison(src),
            'by_season':{str(y):comparison(src[src.year.eq(y)]) for y in [2024,2025]}}
    primary=df[df.odds_source.eq('primary_open')].copy()
    full=base.rename(columns={'p':'model_home'})
    results['combined']['primary_open']=comparison(primary)
    for year in [2024,2025]:
        allgames=full[full.year.eq(year)]
        priced=primary[primary.year.eq(year)]
        omitted=allgames[~allgames.id.isin(priced.id)]
        assert len(omitted)+len(priced)==len(allgames)
        results['coverage'][str(year)]={
           'reconstructed_games':len(allgames),'priced_primary_open':len(priced),
           'missing_price':len(omitted),'missing_price_v15':metrics(omitted,'model_home'),
           'full_year_v15':metrics(allgames,'model_home')}
        results['season'][str(year)]=comparison(priced)
        # True fallback policy: use frozen blend only where both-sided odds
        # exist, otherwise V1.5. Never invent 0.5 or projected missing lines.
        results['season'][str(year)]['v15_fallback_for_missing_prices']={
          'n':len(allgames),
          'wins':results['season'][str(year)]['blend']['wins']+
                 results['coverage'][str(year)]['missing_price_v15']['wins'],
          'note':'Matched priced games use blend; unpriced games use V1.5 unchanged.'}
        for lo,hi,label in [(1,4,'weeks1-4'),(5,8,'weeks5-8'),(9,16,'weeks9-plus')]:
            batch=priced[priced.week.between(lo,hi)]
            results['windows'].setdefault(label,{})[str(year)]=comparison(batch)
    results['combined']['primary_open']['week_cluster_bootstrap']=bootstrap(primary)
    DETAIL.parent.mkdir(parents=True,exist_ok=True)
    primary[['year','week','id','game','y','model_home','market_home','blend_home',
             'home_moneyline','away_moneyline','vig']].to_csv(DETAIL,index=False)
    OUT.write_text(json.dumps(results,indent=2,allow_nan=False)+'\n')
    out={'season':results['season'],'total':results['combined'],
         'windows':results['windows'],'robustness':{
            k:v['combined'] for k,v in results['robustness'].items()},
         'coverage':results['coverage']}
    print('HISTORICAL_TEST_C_RESULT '+json.dumps(out,sort_keys=True),flush=True)

if __name__=='__main__':
    main()
