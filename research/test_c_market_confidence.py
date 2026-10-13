"""Research-only Test C: historical calibration and archived pregame market disagreement.

The only historical two-sided sportsbook odds in this experiment are from
2026 frozen pre-kickoff snapshots. Do not call 2024–25 model reconstructions
prospective; no historical moneyline prices for those years were available.

Do not update model_v1_5, app.py, or waterfall picks.
"""
import json, math
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import fisher_exact

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research/test_c_results.json"
GAME_CSV = ROOT / "research/test_c_game_results.csv"
WEIGHTS = (0.0, 0.16927926947215113, 0.25, 0.5, 0.75, 1.0)
HIST_URL = ("https://raw.githubusercontent.com/christianmellis1-debug/"
            "CFB_Prediction_app/44e7a7cb474e9c19a1af1bfa4774309e6b46b3e6/"
            "research/test_b_venue_games.csv")

def american_implied(odd):
    o = float(odd)
    if not math.isfinite(o) or abs(o) < 100:
        raise ValueError("Invalid American moneyline")
    return 100 / (o+100) if o > 0 else -o/(100-o)

def prob_scores(y, prob):
    p = np.clip(np.asarray(prob, dtype=float), 1e-12, 1-1e-12)
    yy = np.asarray(y, dtype=int)
    good = (p >= 0.5) == yy
    return {
        "n": len(yy), "wins":int(np.sum(good)), "losses":int(np.sum(~good)),
        "accuracy":float(np.mean(good)), "mean_confidence":float(np.mean(np.maximum(p,1-p))),
        "brier":float(np.mean((p-yy)**2)),
        "log_loss":float(np.mean(-yy*np.log(p)-(1-yy)*np.log(1-p)))
    }

def stats(d, col="model_home"):
    if d.empty:
        return None
    return prob_scores(d.y, d[col])

def bins(d, column="model_home"):
    conf = np.maximum(d[column],1-d[column])
    rows = []
    for lo,hi in [(0.5,.6),(.6,.7),(.7,.8),(.8,.9),(.9,1.00001)]:
        sub = d[(conf >= lo)&(conf < hi)]
        if sub.empty:
            continue
        p = sub[column]
        success = (p.ge(.5) == sub.y.astype(bool))
        rows.append({"range":f"{int(lo*100)}-{int(min(hi,1)*100)}%",
                     "n":len(sub), "correct":int(success.sum()),
                     "actual_rate":float(success.mean()),
                     "predicted_mean":float(np.maximum(p,1-p).mean()),
                     "gap_actual_minus_predicted":float(success.mean()-np.maximum(p,1-p).mean())})
    return rows

def archived():
    raw = json.loads((ROOT/"data/shadow_tracking.json").read_text())
    rows=[];skips={}
    for gid,s in raw["snapshots"].items():
        final=raw.get("results",{}).get(gid)
        if final is None:
            skips["not_settled"]=skips.get("not_settled",0)+1
            continue
        if not s.get("captured_at") or not s.get("kickoff") or datetime.fromisoformat(s["captured_at"])>=datetime.fromisoformat(s["kickoff"]):
            skips["not_pregame"]=skips.get("not_pregame",0)+1;continue
        if not s.get("provider","").replace(" ","").lower().startswith("draftkings"):
            skips["other_book"]=skips.get("other_book",0)+1;continue
        h,a = float(final["home_score"]),float(final["away_score"])
        if h==a:skips["tie"]=skips.get("tie",0)+1;continue
        if s["picked_side"] not in ("home","away"):raise ValueError("Missing side")
        home_ml,away_ml=float(s["home_ml"]),float(s["away_ml"])
        ph,pa=american_implied(home_ml),american_implied(away_ml)
        home_market=ph/(ph+pa) # no vig, same sportsbook
        confidence=float(s["model_probability"])
        home_model=confidence if s["picked_side"]=="home" else 1-confidence
        picked_market=home_market if s["picked_side"]=="home" else 1-home_market
        if abs(float(s["market_probability"])-picked_market)>1e-7:
            raise AssertionError(f"Market mismatch on {gid}")
        y=int(h>a)
        if final.get("outcome") != ("win" if ((home_model>=.5)==bool(y)) else "loss"):
            raise AssertionError(f"Outcome mismatch on {gid}")
        item = {
            "id":str(gid),"week":int(s["week"]),"home":s["home"],"away":s["away"],
            "captured_at":s["captured_at"], "provider":s["provider"],
            "y":y, "model_home":home_model,"market_home":home_market,
            "model_pick_correct": int((home_model>=.5)==bool(y)),
            "market_pick_correct": int((home_market>=.5)==bool(y)),
            "model_conf":max(home_model,1-home_model),
            "market_on_model":picked_market,"gap":confidence-picked_market,
            "abs_home_gap":abs(home_model-home_market),
            "opposite_picks":int((home_model>=.5)!=(home_market>=.5)),
            "model_weight_archived":float(s.get("model_weight",0.16927926947215113))}
        for weight in WEIGHTS:
            item[f"blend_{weight:.6f}"] = weight*home_model+(1-weight)*home_market
        rows.append(item)
    df=pd.DataFrame(rows)
    assert len(df)==len(set(df.id)) and df.model_home.between(0,1).all()
    assert len(df)==112 and set(df.week)=={5,6}, "Frozen cohort changed; re-audit before interpretation"
    assert df.groupby("week").size().to_dict()=={5:56,6:56}
    return df,skips

def warnings(df):
    # Explicitly diagnostic; thresholds explored on outcomes (not confirmed).
    definitions={
        "Opposing sportsbook favorite":df.opposite_picks.eq(1),
        "Model >=70%, market <55% for predicted team":(df.model_conf>=.70)&(df.market_on_model<.55),
        "Model >=80%, market <70% for predicted team":(df.model_conf>=.80)&(df.market_on_model<.70),
        "Model lead over market >=15 percentage points":df.gap>=.15,
        "Model lead over market >=20 percentage points":df.gap>=.20,
        "Absolute model/market gap >=20 percentage points":df.abs_home_gap>=.20,
    }
    out={}
    for name,mask in definitions.items():
        sub=df[mask]
        out[name]={
            "all":{"n":len(sub),"wins":int(sub.model_pick_correct.sum()),
                   "losses":int(len(sub)-sub.model_pick_correct.sum()),
                   "mean_model_confidence":float(sub.model_conf.mean()) if len(sub) else None},
            "by_week":{str(w):{"n":len(sub[sub.week==w]),"wins":int(sub.loc[sub.week==w,"model_pick_correct"].sum())}
                       for w in (5,6)}}
        if len(sub)<=10:
            out[name]["games"]=[{"game":r.away+" at "+r.home,"week":r.week,
                  "model_confidence":round(r.model_conf,4),
                  "market_probability_for_model_pick":round(r.market_on_model,4),
                  "model_correct":bool(r.model_pick_correct)}
                  for r in sub.itertuples()]
    agree=df[df.opposite_picks.eq(0)]
    disagree=df[df.opposite_picks.eq(1)]
    out["agree_vs_disagree_fisher_p_two_sided"]=float(fisher_exact([
        [int(agree.model_pick_correct.sum()),len(agree)-int(agree.model_pick_correct.sum())],
        [int(disagree.model_pick_correct.sum()),len(disagree)-int(disagree.model_pick_correct.sum())]
    ]).pvalue)
    return out

def blends(df):
    out={}
    for w in WEIGHTS:
        key=f"blend_{w:.6f}"
        pick_changed=(df[key].ge(.5)!=df.model_home.ge(.5))
        good=df[key].ge(.5).eq(df.y.astype(bool))
        out[str(w)]={
            "all":stats(df,key),
            "week5":stats(df[df.week==5],key),
            "week6":stats(df[df.week==6],key),
            "flipped":int(pick_changed.sum()),
            "corrected":int((pick_changed&good).sum()),
            "broken":int((pick_changed&~good).sum()),
            "brier_2026_minus_baseline":float(stats(df,key)["brier"]-stats(df,"model_home")["brier"])
        }
    return out

def uncertainty(df):
    # Stratified game-level bootstrap preserves week5/week6 n=56 but assumes
    # games within a week independent; correlated team/game risk remains.
    rng=np.random.default_rng(20261013)
    week5=df[df.week==5];week6=df[df.week==6]
    ds=[]
    for _ in range(3000):
        sample=pd.concat([week5.iloc[rng.integers(0,len(week5),len(week5))],
                          week6.iloc[rng.integers(0,len(week6),len(week6))]])
        m=stats(sample,"model_home");mk=stats(sample,"market_home")
        blend=stats(sample,"blend_0.169279")
        ds.append([m["brier"]-mk["brier"],blend["brier"]-mk["brier"],
                   blend["accuracy"]-m["accuracy"]])
    return {
        "description":"Descriptive stratified game-level bootstrap 3000 replicates, equal sample by 2026 week; does not resolve team/week dependence or outcome-selection bias.",
        "v15_brier_minus_market_brier":np.quantile(np.asarray(ds)[:,0],[.025,.975]).tolist(),
        "blend_brier_minus_market_brier":np.quantile(np.asarray(ds)[:,1],[.025,.975]).tolist(),
        "blend_accuracy_minus_v15":np.quantile(np.asarray(ds)[:,2],[.025,.975]).tolist()
    }

def historical():
    # Reconstructed V1.5 with no matching archived historical market lines.
    d=pd.read_csv(HIST_URL,low_memory=False)
    result={}
    for y in (2024,2025):
        sub=d[d.year.eq(y)].copy()
        assert len(sub) in (752,762)
        sub["model_home"]=sub.p
        sub["y"]=sub.y.astype(int)
        result[str(y)]={"n":len(sub),"reconstructed_model":stats(sub),
                        "confidence_bands":bins(sub)}
    return result

def main():
    df,skips=archived()
    result={
        "experiment":"Test C, market disagreement and confidence calibration",
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "scope":"Only 2026 Weeks 5-6 contain locked pregame model predictions and both sides of matching DraftKings moneylines; 2024-25 have model reconstruction only.",
        "caveats":["Thresholds examined retrospectively; Week 6 split is not a clean unseen holdout.",
                   "Bookmaker probability is no-vig from same-book two-sided American moneylines.",
                   "Available quotes were locked 0-7 days before kickoff, and are not necessarily closing lines.",
                   "Historical 2024-25 confidence samples are retrospective V1.5 reconstructed with later-published summary data.",
                   "Betting profitability and ATS performance are not measured in this experiment."],
        "archive_audit":{"snapshots":len(df)+skips.get("not_settled",0),
                         "settled_valid":len(df),"skips":skips,
                         "weeks":{str(int(k)):int(v) for k,v in df.groupby("week").size().items()}},
        "model_2026":stats(df,"model_home"),
        "market_2026":stats(df,"market_home"),
        "week_2026":{str(w):{"model":stats(df[df.week==w],"model_home"),
                             "market":stats(df[df.week==w],"market_home")} for w in (5,6)},
        "model_bands_2026":bins(df),
        "market_bands_2026":bins(df,"market_home"),
        "disagreement":warnings(df),
        "blends":blends(df),
        "confidence_2024_2025":historical(),
        "uncertainty":uncertainty(df)
    }
    # Must not conflate the old 'blend_probability' stored in the snapshot,
    # which remains on the original predicted side, with a re-pick blend here.
    df.to_csv(GAME_CSV,index=False)
    OUT.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print("RESULT_C "+json.dumps({
        "archive_audit":result["archive_audit"],
        "model":result["model_2026"],"market":result["market_2026"],
        "disagreement":result["disagreement"],"blends":result["blends"],
        "confidence_bands_2026":result["model_bands_2026"],
        "uncertainty":result["uncertainty"]
    },sort_keys=True))

if __name__=="__main__":
    main()
