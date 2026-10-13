"""External Test C replication: pre-specified >=70% V1.5 and <55% market.

Source: frozen model reconstruction from Test B, plus archived cfbfastR
raw ESPN game betting JSON (historical opening ESPN BET lines).
WARNING: reconstructed historical V1.5 is retrospective and not a
true locked pregame prediction. The 2026 warning threshold was selected
from its outcomes. 2024/25 testing is a temporal replication check only.
Does not modify the production model or value tiers.
"""
import concurrent.futures, json, time, math, collections
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
import numpy as np
import pandas as pd
from scipy.stats import fisher_exact

ROOT=Path(__file__).resolve().parents[1]
TEST_B_CSV='https://raw.githubusercontent.com/christianmellis1-debug/CFB_Prediction_app/44e7a7cb474e9c19a1af1bfa4774309e6b46b3e6/research/test_b_venue_games.csv'
RAW='https://raw.githubusercontent.com/sportsdataverse/cfbfastR-cfb-raw/main/cfb/betting/json/{}.json'
OUT=ROOT/'research/test_c_historical_validation_results.json'
DETAIL=ROOT/'research/test_c_historical_validation_games.csv'
MISSING=ROOT/'research/test_c_historical_odds_coverage.csv'
CANDIDATES=('primary_open','fallback_open','primary_close')
THRESHOLD_MODEL=.70
THRESHOLD_MARKET=.55

def american_num(o):
    if o is None:return None
    try:
        x=float(str(o).replace(',','').strip())
        if not math.isfinite(x) or abs(x)<100 or x==0:return None
        return x
    except (ValueError,TypeError):return None

def implied(o):
    return 100/(100+o) if o>0 else -o/(100-o)

def quote(odds,endpoint):
    if endpoint in ('open','close'):
        x=odds.get(endpoint)
        if not isinstance(x,dict):return None
        money=x.get('moneyLine')
        if isinstance(money,dict):
            return american_num(money.get('american') or money.get('alternateDisplayValue'))
        return None
    return american_num(odds.get('moneyLine'))

def extract(payload):
    items=payload.get('odds_full',{}).get('items') or []
    if not isinstance(items,list):return dict(error='no_items')
    entries={}
    for item in items:
        label=(item.get('provider') or {}).get('name','').lower().strip()
        if label=='espn bet':key='primary'
        elif label=='espn bet - live odds':key='fallback'
        else:continue
        if key in entries:continue
        ht=item.get('homeTeamOdds') or {}
        at=item.get('awayTeamOdds') or {}
        entry={}
        for period in ('open','close'):
            ho=quote(ht,period);aw=quote(at,period)
            if ho is not None and aw is not None:
                hp=implied(ho);ap=implied(aw);vig=hp+ap-1
                if 0<=vig<=.16:
                    entry[period]=(hp/(hp+ap),ho,aw,vig)
        entries[key]=entry
    data={}
    for period in ('open','close'):
        val=entries.get('primary',{}).get(period)
        if val is not None:data['primary_'+period]=val
    val=entries.get('fallback',{}).get('open')
    if val is not None:data['fallback_open']=val
    return dict(prices=data,provider_count=len(items))

def download(gid):
    err=None
    for attempt in range(3):
        try:
            req=Request(RAW.format(gid),headers={'User-Agent':'SaturdayForecast-TestCResearch/1.0','Accept':'application/json'})
            with urlopen(req,timeout=18) as resp:blob=resp.read()
            data=json.loads(blob)
            return gid,extract(data)
        except HTTPError as e:
            if e.code in (404,410):return gid,dict(error='not_found')
            err='http_'+str(e.code)
        except (URLError,TimeoutError,ValueError,OSError) as e:err=type(e).__name__
        if attempt<2:time.sleep(.3*(attempt+1))
    return gid,dict(error=err or 'other_error')

def ci_wilson(k,n):
    if n==0:return None
    z=1.96;p=k/n
    d=1+z*z/n
    c=(p+z*z/(2*n))/d
    a=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [round(c-a,4),round(c+a,4)]

def quality(d):
    if d.empty:return None
    m=d.model_correct.astype(int)
    x=(d.predicted_confidence>=THRESHOLD_MODEL)&(d.market_on_pick<THRESHOLD_MARKET)
    flags=d[x];others=d[~x]
    hc=d[d.predicted_confidence>=THRESHOLD_MODEL]
    nonflag_hc=hc[~((hc.predicted_confidence>=THRESHOLD_MODEL)&(hc.market_on_pick<THRESHOLD_MARKET))]
    def measure(frame):
        n=len(frame)
        if n==0:return {'n':0,'wins':0,'losses':0,'accuracy':None,'wilson95':None}
        w=int(frame.model_correct.sum())
        return {'n':n,'wins':w,'losses':n-w,'accuracy':round(w/n,4),'wilson95':ci_wilson(w,n)}
    y={
        'all':measure(d),'flagged':measure(flags),'not_flagged':measure(others),
        'high_confidence_70_plus':measure(hc),'high_confidence_not_flagged':measure(nonflag_hc),
        'warning_rate':round(len(flags)/len(d),4),
        'losers_caught':int(flags.model_correct.eq(0).sum()),
        'fraction_all_model_losses_caught':round(int((~flags.model_correct).sum())/int(d.model_correct.eq(0).sum()),4) if d.model_correct.eq(0).sum() else 0,
        'model_brier':round(float(np.mean((d.model_home-d.y)**2)),6),
        'market_brier':round(float(np.mean((d.market_home-d.y)**2)),6),
        'model_logloss':round(float(np.mean(-d.y*np.log(np.clip(d.model_home,1e-9,1-1e-9))-(1-d.y)*np.log(np.clip(1-d.model_home,1e-9,1-1e-9)))),6),
        'market_logloss':round(float(np.mean(-d.y*np.log(np.clip(d.market_home,1e-9,1-1e-9))-(1-d.y)*np.log(np.clip(1-d.market_home,1e-9,1-1e-9)))),6),
        'book_favorite_wins':int(d.market_correct.sum()),
        'abstain_accuracy':measure(others)['accuracy'],
        'abstain_coverage':round(len(others)/len(d),4),
    }
    if len(flags)>0 and len(nonflag_hc)>0:
        a=int(flags.model_correct.sum());b=len(flags)-a
        c=int(nonflag_hc.model_correct.sum());e=len(nonflag_hc)-c
        y['flag_vs_other_high_conf_fisher_two_sided_p']=round(float(fisher_exact([[a,b],[c,e]]).pvalue),6)
    return y

def build():
    hist=pd.read_csv(TEST_B_CSV,low_memory=False)
    hist=hist[hist.year.isin([2024,2025])].copy()
    assert len(hist)==1514 and not hist.duplicated(['year','id']).any()
    hist['model_home']=hist.p
    hist['y']=hist.y.astype(int)
    hist['predicted_confidence']=np.maximum(hist.model_home,1-hist.model_home)
    ids=[str(x) for x in hist.id.astype(str)]
    records={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=26) as executor:
        jobs=[executor.submit(download,gid) for gid in ids]
        for idx, job in enumerate(concurrent.futures.as_completed(jobs),1):
            gid,val=job.result();records[str(gid)]=val
            if idx%250==0:print(f'Fetched betting JSON: {idx}/{len(ids)}',flush=True)
    print('All archive fetches finished:',len(records),flush=True)
    detail=[]
    coverage=[]
    for r in hist.itertuples():
        gid=str(r.id)
        x=records[gid]
        record={'year':int(r.year),'week':int(r.week),'id':gid,'game':r.game,
            'error':x.get('error'),'provider_count':x.get('provider_count',0)}
        for key in CANDIDATES:
            q=(x.get('prices') or {}).get(key)
            record[key]=q is not None
            if q is None:continue
            market_home,home_ml,away_ml,vig=q
            conf=float(r.predicted_confidence)
            picked_home=r.model_home>=.5
            m_on_pick=market_home if picked_home else 1-market_home
            model_correct=int((r.model_home>=.5)==bool(r.y))
            market_correct=int((market_home>=.5)==bool(r.y))
            detail.append({'year':int(r.year),'week':int(r.week),'id':gid,'game':r.game,
                'odds_source':key,'model_home':float(r.model_home),'market_home':market_home,
                'home_moneyline':home_ml,'away_moneyline':away_ml,'vig':vig,
                'predicted_confidence':conf,'market_on_pick':m_on_pick,'gap':conf-m_on_pick,
                'y':int(r.y),'model_correct':model_correct,'market_correct':market_correct,
                'warning':conf>=THRESHOLD_MODEL and m_on_pick<THRESHOLD_MARKET})
        coverage.append(record)
    detail=pd.DataFrame(detail)
    cover=pd.DataFrame(coverage)
    cover.to_csv(MISSING,index=False)
    detail.to_csv(DETAIL,index=False)
    result={'experiment':'Test C independent-era retrospective market-disagreement replication',
     'generated':datetime.now(timezone.utc).isoformat(),
     'threshold_frozen':'predicted V1.5 win chance >=70% AND same-side sportsbook no-vig probability <55%',
     'limitations':[
      '2024 and 2025 model probabilities are RECONSTRUCTED using currently published weekly data; they were not frozen before kickoff.',
      '2026 threshold was retrospectively chosen on that year: no fresh 2026 validation in this report.',
      'Historical ESPN BET archived opening and closing lines were extracted from SportsDataverse cfbfastR-cfb-raw ESPN game betting snapshots; quote authenticity and timestamps were not independently confirmed.',
      '2025 is not a pristine model-wide holdout because existing model calibration and parameters were informed by historical seasons.',
      'ESPN BET archived historical lines may differ from the original 2026 DraftKings book; opening is preferred to guard against late/live quote leakage.',
      'Odds missingness may be selective: comparisons apply only to matchups with valid two-sided historical quote pairs.',
      'Warnings would mark a game as needing review, not automatically reverse the picked winner or establish betting ROI.'
     ],
     'overall_requested':len(hist),'archives_fetched':len(records),
     'coverage':{},'samples':{},'examples':{}}
    for year in [2024,2025,'combined']:
        subset=cover if year=='combined' else cover[cover.year==year]
        result['coverage'][str(year)]={'requested':len(subset),
            'not_found':int(subset.error.eq('not_found').sum()),
            'other_errors':subset.error.dropna().value_counts().to_dict(),
            'primary_open':int(subset.primary_open.sum()),
            'primary_close':int(subset.primary_close.sum()),
            'fallback_open':int(subset.fallback_open.sum())}
        result['samples'][str(year)]={}
        for key in CANDIDATES:
            sub=detail[detail.odds_source.eq(key)]
            if year!='combined':sub=sub[sub.year==year]
            result['samples'][str(year)][key]=quality(sub)
        chosen=detail[detail.odds_source.eq('primary_open')]
        if year!='combined':chosen=chosen[chosen.year==year]
        flagged=chosen[chosen.warning]
        result['examples'][str(year)]=[dict(game=g.game,year=int(g.year),week=int(g.week),
             model_confidence=round(float(g.predicted_confidence),4),
             market_same_side=round(float(g.market_on_pick),4),
             model_correct=bool(g.model_correct))
             for g in flagged.sort_values('week').head(75).itertuples()]
    OUT.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print('RESULT_TEST_C_VALIDATION '+json.dumps({'coverage':result['coverage'],'samples':result['samples'],
     'examples':{y:x[:20] for y,x in result['examples'].items()}},sort_keys=True),flush=True)

if __name__=='__main__':
    build()
