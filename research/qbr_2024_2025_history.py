#!/usr/bin/env python3
"""Read-only historical validation, locked 2026 P4 low-QBR-gap + rushing-defense rule.
No production settings or model picks are changed.
"""
import collections, io, json, math, time
import requests
import pandas as pd

sess=requests.Session()
def getjson(url):
    r=sess.get(url,timeout=45);r.raise_for_status();return r.json()
def getcsv(url):
    r=sess.get(url,timeout=90);r.raise_for_status()
    return pd.read_csv(io.BytesIO(r.content),low_memory=False)
def num(x):return pd.to_numeric(x,errors="coerce")
def sid(v):return str(int(v))
P4={"ACC","Big Ten","Big 12","SEC"}
G6={"American Athletic","Conference USA","Mid-American","Mountain West","Sun Belt","Pac-12"}
def grp(conf,team):
    if "notre dame" in str(team).casefold():return "P4"
    if conf in P4:return "P4"
    if conf in G6:return "G6"
    return "outside"
def win_stats(rows):
    n=len(rows);w=sum(int(x["won"]) for x in rows)
    return dict(n=n,w=w,l=n-w,pct=round(100*w/n,1) if n else None)
def money_net(odds,winner):
    if odds is None or odds==0:return None
    return (10000/abs(odds) if odds<0 else odds) if winner else -100
def textrow(label,record):
    print(label,json.dumps(record,ensure_ascii=False,default=str),flush=True)

for yr in [2024,2025,2026]:
    print("START_YEAR",yr,flush=True)
    s=getcsv(f"https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_{yr}.csv")
    b=getcsv(f"https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_team_box/team_box_{yr}.csv")
    odds=getcsv(f"https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_betting/betting_{yr}.csv")
    for col in ["game_id","week","home_id","away_id"]:
        s[col]=num(s[col])
    for side in ["home","away"]:
        if yr==2026:
            sac=s[side+"_team"].astype(str).str.casefold().str.contains("sacramento state|sac state")
            s.loc[sac,side+"_division"]="fbs"
            s.loc[sac,side+"_conference"]="Mid-American"
    s=s[s.home_division.astype(str).str.lower().eq("fbs")&s.away_division.astype(str).str.lower().eq("fbs")&
        s.season_type.astype(str).str.lower().eq("regular")].copy()
    s["date"]=pd.to_datetime(s.start_date,utc=True,errors="coerce")
    s=s.dropna(subset=["game_id","week","home_id","away_id","date"]).drop_duplicates(["game_id"],keep=False)
    for col in ["game_id","home_id","away_id"]:s[col]=s[col].map(sid)
    s["week"]=s.week.astype(int)
    s["is_done"]=s.completed.astype(str).str.lower().isin(["true","t","1","1.0","yes","y"])
    canon=s.set_index("game_id")
    fbs=set(s.home_id)|set(s.away_id)
    if yr==2026:
        allteams=getjson('https://site.api.espn.com/apis/site/v2/sports/football/college-football/teams?limit=500&groups=80')
        fbs={str(team['team']['id']) for team in allteams.get('sports',[{}])[0].get('leagues',[{}])[0].get('teams',[])}
    maxweek=7 if yr==2026 else 15
    qbr_by_game=collections.defaultdict(dict)
    games_by_week={}
    feed_rows=0
    for wk in range(1,maxweek+1):
        res=getjson(f"https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard?dates={yr}&seasontype=2&week={wk}&groups=80&limit=500")
        games=[]
        for ev in res.get("events",[]):
            c=ev.get("competitions",[{}])[0]
            if not c.get("status",{}).get("type",{}).get("completed",False):continue
            cs=c.get("competitors",[])
            h=next((z for z in cs if z.get("homeAway")=="home"),None)
            a=next((z for z in cs if z.get("homeAway")=="away"),None)
            if not h or not a:continue
            hid=str(h["team"]["id"]);aid=str(a["team"]["id"]);eid=str(ev["id"])
            if hid not in fbs or aid not in fbs:continue
            games.append(dict(id=eid,year=yr,week=wk,date=ev["date"],home=h["team"]["displayName"],away=a["team"]["displayName"],
                              hid=hid,aid=aid,winner="home" if h.get("winner") else "away" if a.get("winner") else None))
        games_by_week[wk]=sorted(games,key=lambda x:x["date"])
        j=getjson(f"https://site.web.api.espn.com/apis/fitt/v3/sports/football/college-football/qbr?qbrType=weeks&season={yr}&week={wk}&seasontype=2&isqualified=false&limit=1000")
        labs=j.get("categories",[{}])[0].get("labels",[])
        feed_rows+=len(j.get("athletes",[]))
        for q in j.get("athletes",[]):
            athlete=q.get("athlete",{});e=q.get("game",{}).get("id")
            if not e:continue
            d=dict(zip(labs,q.get("categories",[{}])[0].get("totals",[])))
            try:
                v=float(d.get("TQBR"));tid=str(athlete["teamId"])
                if math.isfinite(v):qbr_by_game[str(e)][tid]=(athlete.get("displayName"),v)
            except (ValueError,TypeError,KeyError):pass
        textrow("INPUT",dict(year=yr,week=wk,espn_fbs_games=len(games),qbr_rows=len(j.get("athletes",[]))))

    for col in ["game_id","team_id","rushingYards","rushingAttempts"]:b[col]=num(b[col])
    b=b.dropna(subset=["game_id","team_id","rushingYards","rushingAttempts"]).copy()
    b=b[b.rushingAttempts.gt(0)&b.rushingAttempts.mod(1).eq(0)]
    b=b[~b.duplicated(["game_id","team_id"],keep=False)]
    b["game_id"]=b.game_id.map(sid);b["team_id"]=b.team_id.map(sid)
    box=b.set_index(["game_id","team_id"])[["rushingYards","rushingAttempts"]].to_dict("index")
    def def_ypc(game,side):
        target=game["hid"] if side=="home" else game["aid"]
        tgtweek=game["week"]
        before=pd.Timestamp(game["date"])
        history=s[(s.week<tgtweek)&s.date.lt(before)&s.is_done&(s.home_id.eq(target)|s.away_id.eq(target))]
        if history.empty:return None
        yards=attempts=0
        for _,old in history.iterrows():
            opponent=old.away_id if old.home_id==target else old.home_id
            k=(old.game_id,opponent)
            if k not in box:return None
            v=box[k];yards+=v["rushingYards"];attempts+=v["rushingAttempts"]
        return yards/attempts if attempts>0 else None
    allqbr=[];scope=[];agree=[];candidate=[];miss=collections.Counter();previous={}
    for wk in range(1,maxweek+1):
        for g in games_by_week[wk]:
            h=previous.get(g["hid"]);a=previous.get(g["aid"])
            if wk>=2 and h is not None and a is not None and h[1]!=a[1] and g["id"] in canon.index:
                high="home" if h[1]>a[1] else "away"
                w=int(high==g["winner"])
                canon_g=canon.loc[g["id"]]
                hg=grp(canon_g.home_conference,canon_g.home_team);ag=grp(canon_g.away_conference,canon_g.away_team)
                buck=hg if hg==ag and hg in ("P4","G6") else "outside"
                gap=abs(h[1]-a[1])
                rec=dict(year=yr,week=wk,game_id=g["id"],home=g["home"],away=g["away"],hid=g["hid"],aid=g["aid"],group=buck,
                         pick=g[high],pick_side=high,pick_qbr=h[1] if high=="home" else a[1],other_qbr=a[1] if high=="home" else h[1],
                         qbr_gap=round(gap,3),won=w)
                allqbr.append(rec)
                if buck=="P4":
                    scope.append(rec)
                    hy=def_ypc(g,"home");ay=def_ypc(g,"away")
                    if hy is None or ay is None:miss["rushing data"]+=1
                    elif hy==ay:miss["rush defense tied"]+=1
                    else:
                        run="home" if hy<ay else "away"
                        if high==run:
                            rec.update(home_ypc=round(hy,4),away_ypc=round(ay,4),ypc_gap=round(abs(hy-ay),4))
                            agree.append(rec)
                            if gap<10:candidate.append(rec)
            elif wk>=2:miss["QBR not comparable"]+=1
            q=qbr_by_game.get(g["id"],{})
            for t in [g["hid"],g["aid"]]:
                if t in q:previous[t]=q[t]
    textrow("YEAR_COUNTS",{"year":yr,"raw_qbr_games":len(allqbr),"p4_qbr_games":len(scope),
                            "p4_dual_adv":win_stats(agree),"p4_candidate_under10":win_stats(candidate),
                            "p4_dual_adv_gap10plus":win_stats([z for z in agree if z["qbr_gap"]>=10]),
                            "missing":dict(miss)})
    for week in range(2,maxweek+1):
        c=[z for z in candidate if z["week"]==week]
        if c:textrow("WEEK_RESULT",{"year":yr,"week":week,**win_stats(c)})

    odds.game_id=odds.game_id.map(sid)
    odds=odds[odds.game_spread_available.astype(str).str.lower().isin(["true","t","1","1.0","yes","y"])]
    odds=odds[~odds.odds_source.astype(str).str.lower().eq("default")]
    odds=odds.drop_duplicates(["game_id"],keep="last").set_index("game_id")
    broad_baseline=collections.Counter()
    for rec in agree:
        eid=rec["game_id"];line=odds.loc[eid] if eid in odds.index else None
        home_spread=float(line.home_team_spread) if line is not None and pd.notna(line.home_team_spread) else None
        if home_spread is None or home_spread==0:continue
        fav_side="home" if home_spread<0 else "away"
        favorite_win=int((rec["pick_side"]==fav_side)==bool(rec["won"]))
        broad_baseline["games"]+=1;broad_baseline["fav_wins"]+=favorite_win
        broad_baseline["qbr_run_wins"]+=rec["won"]
        game=canon.loc[eid]
        try:
            home_margin=float(game.home_points)-float(game.away_points)
            side_margin=home_margin if rec["pick_side"]=="home" else -home_margin
            side_spread=home_spread if rec["pick_side"]=="home" else -home_spread
            ats_result=side_margin+side_spread
            broad_baseline["qbr_run_ats_w"]+=ats_result>0
            broad_baseline["qbr_run_ats_l"]+=ats_result<0
            broad_baseline["qbr_run_ats_p"]+=ats_result==0
        except (ValueError,TypeError):pass
    textrow("BROAD_MARKET",{"year":yr,**dict(broad_baseline)})
    profits=[];fav_profits=[];favwins=0;favcount=0;fav_candidates=0;dogs=0;wkprof=collections.defaultdict(list)
    ats=collections.Counter();fav_ats=collections.Counter();by_status=collections.defaultdict(list)
    for rec in candidate:
        eid=rec["game_id"];line=odds.loc[eid] if eid in odds.index else None
        home_spread=float(line.home_team_spread) if line is not None and pd.notna(line.home_team_spread) else None
        fav=None if home_spread is None or home_spread==0 else ("home" if home_spread<0 else "away")
        is_fav=fav==rec["pick_side"] if fav else None
        if is_fav: fav_candidates+=1
        elif is_fav==False:dogs+=1
        by_status["favorite" if is_fav else "underdog" if is_fav is False else "unpriced"].append(rec)
        if home_spread is not None and eid in canon.index:
            game=canon.loc[eid]
            try:
                home_margin=float(game.home_points)-float(game.away_points)
                side_margin=home_margin if rec["pick_side"]=="home" else -home_margin
                side_spread=home_spread if rec["pick_side"]=="home" else -home_spread
                final_ats=side_margin+side_spread
                ats["W" if final_ats>0 else "L" if final_ats<0 else "P"]+=1
                if fav:
                    f_ats=(home_margin+home_spread)* (1 if fav=="home" else -1)
                    fav_ats["W" if f_ats>0 else "L" if f_ats<0 else "P"]+=1
            except (TypeError,ValueError):pass
        ml=None;opp_ml=None;provider=None
        try:
            e=getjson("https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary?event="+eid)
            for item in e.get("pickcenter",[]):
                name=item.get("provider",{}).get("name","")
                if name.lower()!="draftkings":continue
                provider=name
                side="homeTeamOdds" if rec["pick_side"]=="home" else "awayTeamOdds"
                other="awayTeamOdds" if rec["pick_side"]=="home" else "homeTeamOdds"
                ml=item.get(side,{}).get("moneyLine")
                opp_ml=item.get(other,{}).get("moneyLine")
                break
        except Exception as error:
            provider="not available: "+str(error)[:80]
        pnl=money_net(ml,rec["won"])
        if pnl is not None:
            profits.append(pnl);wkprof[rec["week"]].append(pnl)
        if fav:
            favwin=int((rec["pick_side"]==fav)==bool(rec["won"]))
            favwins+=favwin;favcount+=1
            favorite_odds=ml if is_fav else opp_ml
            favorite_profit=money_net(favorite_odds,favwin)
            if favorite_profit is not None:fav_profits.append(favorite_profit)
        textrow("GAME",{"year":yr,"week":rec["week"],"game_id":eid,"pick":rec["pick"],"opponent":rec["away"] if rec["pick_side"]=="home" else rec["home"],
                        "home":rec["home"],"away":rec["away"],"result":"W" if rec["won"] else "L",
                        "qbr_gap":rec["qbr_gap"],"def_ypc_gap":rec["ypc_gap"],"home_ypc":rec["home_ypc"],"away_ypc":rec["away_ypc"],
                        "selection_favorite":is_fav,"home_spread":home_spread,"dk_moneyline":ml,"pnl_100":round(pnl,2) if pnl is not None else None,
                        "provider":provider})
    textrow("YEAR_DETAIL",{"year":yr,"as_market_favorite":win_stats(by_status["favorite"]),"as_underdog":win_stats(by_status["underdog"]),"candidate_ats":dict(ats),"favorite_ats_same_games":dict(fav_ats)})
    textrow("YEAR_SUMMARY",{"year":yr,**win_stats(candidate),"favorites":fav_candidates,"underdogs":dogs,
                             "favorite_wins":favwins,"favorite_count":favcount,
                             "moneyline_coverage":len(profits),"net_100":round(sum(profits),2),"roi_pct":round(sum(profits)/len(profits),2) if profits else None,
                             "favorite_benchmark_coverage":len(fav_profits),"favorite_benchmark_net_100":round(sum(fav_profits),2),
                             "favorite_benchmark_roi_pct":round(sum(fav_profits)/len(fav_profits),2) if fav_profits else None})
    for wk,vals in sorted(wkprof.items()):
        textrow("WEEK_ROI",{"year":yr,"week":wk,"priced_bets":len(vals),"pnl_100":round(sum(vals),2)})
print("BACKTEST_COMPLETE",flush=True)
