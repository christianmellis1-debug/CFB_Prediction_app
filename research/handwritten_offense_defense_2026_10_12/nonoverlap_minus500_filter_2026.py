"""Apply heavy favorite cutoff (-500 or shorter) to 2026 Test A ex-Tier4 picks.
Retrospective Draft Kings closing moneylines. Week 3 was excluded from Tier4
by date rather than price, so fetch those lines independently.
"""
from pathlib import Path
from datetime import datetime, timezone
import csv,json
from research.handwritten_offense_defense_2026_10_12.audit_tier4_overlap_2026 import get,ml

ROOT=Path("research/handwritten_offense_defense_2026_10_12")
INPUT=ROOT/"tier4_overlap_2026_games.csv"
RESULT=ROOT/"nonoverlap_minus500_filter_2026.json"
CSV=ROOT/"nonoverlap_minus500_filter_2026.csv"

def stats(rows):
    w=sum(r["result"]=="W" for r in rows)
    return {"games":len(rows),"wins":w,"losses":len(rows)-w,
            "win_pct":round(w/len(rows),6) if rows else None}

def season_stat(rows):
    return {str(w):stats([r for r in rows if int(r["week"])==w]) for w in (3,4,5,6)}

def main():
    with INPUT.open() as f:
        inp=list(csv.DictReader(f))
    selected=[r for r in inp if r["overlap_close"]!="True"]
    assert stats(selected)["games"]==39 and stats(selected)["wins"]==31
    for r in selected:
        r["week"]=int(r["week"])
        if r["week"]==3:
            r["dk_home_close"]=None
            r["dk_away_close"]=None
            j,error=get(r["game_id"])
            if error:
                r["error"]=error
                continue
            comp=(((j.get("header") or {}).get("competitions")) or [{}])[0]
            home=next((c for c in comp.get("competitors",[]) if c.get("homeAway")=="home"),{})
            away=next((c for c in comp.get("competitors",[]) if c.get("homeAway")=="away"),{})
            hname=((home.get("team") or {}).get("displayName") or "").casefold()
            aname=((away.get("team") or {}).get("displayName") or "").casefold()
            def same(name,full):return full==name.casefold() or full.startswith(name.casefold()+" ")
            if not same(r["home"],hname) or not same(r["away"],aname):
                r["error"]="ESPN school identity mismatch"
                continue
            o=j.get("pickcenter") or comp.get("odds") or j.get("odds") or []
            if isinstance(o,dict):o=[o]
            dk=next((x for x in o if "draft" in str((x.get("provider") or {}).get("name","")).casefold() and
                         "king" in str((x.get("provider") or {}).get("name","")).casefold()),None)
            if dk is None:
                r["error"]="No Draft Kings provider"
                continue
            market=dk.get("moneyline") or {}
            r["dk_home_close"]=ml((((market.get("home") or {}).get("close") or {}).get("odds")))
            r["dk_away_close"]=ml((((market.get("away") or {}).get("close") or {}).get("odds")))
            if r["dk_home_close"] is None or r["dk_away_close"] is None:
                r["error"]="Missing DK close moneyline"
            else:
                r["error"]=""
        else:
            r["dk_home_close"]=ml(r["dk_home_close"])
            r["dk_away_close"]=ml(r["dk_away_close"])
        valid=(r["dk_home_close"] is not None and r["dk_away_close"] is not None and
               r["dk_home_close"]<0<r["dk_away_close"])
        r["valid_DK_favorite"]=valid
        r["exclude_favorite_minus500_or_shorter"]=bool(valid and r["dk_home_close"]<=-500)
        r["include_less_than_minus500"]=bool(valid and -500<r["dk_home_close"]<0)
    included=[r for r in selected if r.get("include_less_than_minus500")]
    excluded=[r for r in selected if r.get("exclude_favorite_minus500_or_shorter")]
    unknown=[r for r in selected if not r.get("include_less_than_minus500") and not r.get("exclude_favorite_minus500_or_shorter")]
    assert len(included)+len(excluded)+len(unknown)==len(selected)
    result={
        "retrieved_at":datetime.now(timezone.utc).isoformat(),
        "source":"ESPN 2026 event summary retrospective Draft Kings closing moneylines, game-id verified",
        "filter":"Start 39 2026 W3-6 custom Test A selections not confirmed Tier4 closing-band. Exclude every valid DK home favorite with closing moneyline <= -500, keep favorites from -100 through -499, leave unavailable unclassified.",
        "original_no_tier4":stats(selected),
        "included_after_cut":stats(included),
        "excluded_short_price":stats(excluded),
        "unverified_price":stats(unknown),
        "included_per_week":season_stat(included),
        "excluded_per_week":season_stat(excluded),
        "unverified_per_week":season_stat(unknown),
        "included_games":[{k:r.get(k) for k in ("week","game_id","home","away","home_group","spread","magnitude","dk_home_close","result")} for r in included],
        "excluded_games":[{k:r.get(k) for k in ("week","game_id","home","away","dk_home_close","result")} for r in excluded],
        "unverified_games":[{k:r.get(k) for k in ("week","game_id","home","away","error")} for r in unknown],
        "limitations":[
           "Odds may be revised; closing prices in the retrospective ESPN API not verified as immutable pregame screenshots.",
           "No ROI, spread coverage, or independence claim.",
           "Because Tier4 only starts W4, W3 price check is solely the user-requested new -500 exclusion.",
           "Missing prices are not presumed to be qualifying under the cap.",
           "No production file changes."
        ]
    }
    RESULT.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    fields=["week","game_id","home","away","home_group","result","magnitude","spread",
            "dk_home_close","dk_away_close","valid_DK_favorite",
            "include_less_than_minus500","exclude_favorite_minus500_or_shorter","error"]
    with CSV.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        w.writeheader()
        w.writerows(selected)
    print(json.dumps(result,indent=2))
if __name__=="__main__":main()
