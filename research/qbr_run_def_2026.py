#!/usr/bin/env python3
"""2026 FBS only pregame QBR + pregame run-defense backtest, read only."""
import collections, datetime as dt, io, json, math
import requests
import pandas as pd

SESSION=requests.Session()
def jsonget(url):
    r=SESSION.get(url,timeout=50);r.raise_for_status();return r.json()
def frameget(url):
    r=SESSION.get(url,timeout=90);r.raise_for_status();return pd.read_csv(io.BytesIO(r.content),low_memory=False)
def numeric(s):
    return pd.to_numeric(s,errors="coerce")
def obj_id(value):
    try: return str(int(value))
    except (ValueError, TypeError): return str(value)
def group(conf,name):
    if "notre dame" in str(name).casefold():return "P4"
    if conf in {"ACC","Big Ten","Big 12","SEC"}:return "P4"
    if conf in {"American Athletic","Conference USA","Mid-American","Mountain West","Sun Belt","Pac-12"}:return "G6"
    return None

URL_SCHEDULE="https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_2026.csv"
URL_BOX="https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_team_box/team_box_2026.csv"
schedule=frameget(URL_SCHEDULE)
box=frameget(URL_BOX)
print("SCHEDULE_SCHEMA",repr(schedule.columns.tolist()),len(schedule),flush=True)
print("BOX_SCHEMA",repr(box.columns.tolist()),len(box),flush=True)
print("SCHEDULE_EXAMPLE",repr(schedule.iloc[0].to_dict()),flush=True)
print("BOX_EXAMPLE",repr(box.iloc[0].to_dict()),flush=True)

required={"game_id","week","home_id","away_id","home_team","away_team","home_conference","away_conference","start_date","home_division","away_division","completed","season_type"}
assert required.issubset(schedule),str(required-set(schedule))
for c in ["game_id","week","home_id","away_id"]:
    schedule[c]=numeric(schedule[c])
for side in ["home","away"]:
    div=side+"_division"
    sacr=schedule[side+"_team"].astype(str).str.casefold().str.contains("sacramento state|sac state",regex=True)
    schedule.loc[sacr,div]="fbs"
    schedule.loc[sacr,side+"_conference"]="Mid-American"
schedule=schedule[schedule["home_division"].astype(str).str.lower().eq("fbs") & schedule["away_division"].astype(str).str.lower().eq("fbs")]
schedule=schedule[schedule.season_type.astype(str).str.casefold().eq("regular")].copy()
schedule["date"]=pd.to_datetime(schedule.start_date,utc=True,errors="coerce")
schedule=schedule.dropna(subset=["game_id","week","home_id","away_id","date"])
schedule=schedule.drop_duplicates(subset=["game_id"],keep=False)
schedule["game_id"]=schedule.game_id.map(obj_id)
schedule["home_id"]=schedule.home_id.map(obj_id)
schedule["away_id"]=schedule.away_id.map(obj_id)
for c in ["game_id","team_id","rushingYards","rushingAttempts"]:
    box[c]=numeric(box[c])
box=box.dropna(subset=["game_id","team_id","rushingYards","rushingAttempts"])
box=box[box.rushingAttempts.gt(0) & box.rushingAttempts.mod(1).eq(0)]
box=box[~box.duplicated(["game_id","team_id"],keep=False)].copy()
box["game_id"]=box.game_id.map(obj_id)
box["team_id"]=box.team_id.map(obj_id)
lookup=box.set_index(["game_id","team_id"])[["rushingYards","rushingAttempts"]].to_dict("index")
byid=schedule.set_index("game_id")
print("FBS_SCHEDULE_ROWS",len(schedule),"BOX_ROWS",len(box),"RELEVANT_GAME_BOXES",sum(g in set(schedule.game_id) for g in box.game_id)/2,flush=True)

teams=jsonget("https://site.api.espn.com/apis/site/v2/sports/football/college-football/teams?limit=500&groups=80")
fbs={str(x["team"]["id"]) for x in teams.get("sports",[{}])[0].get("leagues",[{}])[0].get("teams",[])}
games_by_week={}
qbr_by_game=collections.defaultdict(dict)
for wk in range(1,8):
    result=jsonget(f"https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard?dates=2026&seasontype=2&week={wk}&groups=80&limit=500")
    games=[]
    for ev in result.get("events",[]):
        comp=ev.get("competitions",[{}])[0]
        if not comp.get("status",{}).get("type",{}).get("completed",False):continue
        cs=comp.get("competitors",[])
        if len(cs)!=2:continue
        h=next((z for z in cs if z.get("homeAway")=="home"),None)
        a=next((z for z in cs if z.get("homeAway")=="away"),None)
        if not h or not a:continue
        hid=str(h["team"]["id"]);aid=str(a["team"]["id"])
        if hid not in fbs or aid not in fbs:continue
        games.append(dict(id=str(ev["id"]),date=ev.get("date"),week=wk,home=h["team"]["displayName"],away=a["team"]["displayName"],hid=hid,aid=aid,winner="home" if h.get("winner") else "away" if a.get("winner") else None))
    games_by_week[wk]=sorted(games,key=lambda g:g["date"])
    raw=jsonget(f"https://site.web.api.espn.com/apis/fitt/v3/sports/football/college-football/qbr?qbrType=weeks&season=2026&week={wk}&seasontype=2&isqualified=false&limit=1000")
    labels=raw.get("categories",[{}])[0].get("labels",[])
    for rec in raw.get("athletes",[]):
        athlete=rec.get("athlete",{}); game=rec.get("game",{}).get("id")
        if not game:continue
        values=dict(zip(labels,rec.get("categories",[{}])[0].get("totals",[])))
        val=values.get("TQBR")
        try:
            qbr=float(val)
            if not math.isfinite(qbr):continue
            qbr_by_game[str(game)][str(athlete["teamId"])]=(athlete.get("displayName"),qbr)
        except (ValueError,TypeError,KeyError):continue
    print("INPUT_WEEK",wk,"ESPN_FBS",len(games),"WEEKLY_QBR_ROWS",len(raw.get("athletes",[])),"SCHEDULE_MATCH",sum(g["id"] in byid.index for g in games),flush=True)

def defense(g,side):
    team=g["hid"] if side=="home" else g["aid"]
    gid=g["id"]
    if gid not in byid.index:return None,"not in canonical schedule"
    match=byid.loc[gid]
    history=schedule[(schedule.week.lt(g["week"])) & schedule.date.lt(pd.Timestamp(g["date"])) &
                     (schedule.home_id.eq(team)|schedule.away_id.eq(team))]
    history=history[history.completed.astype(str).str.casefold().isin(["true","t","1","1.0","yes","y"])]
    if history.empty:return None,"no earlier FBS games"
    yds=att=0
    for _,p in history.iterrows():
        opponent=p.away_id if p.home_id==team else p.home_id
        key=(p.game_id,opponent)
        if key not in lookup:return None,f"missing opponent rushing line for {p.game_id}"
        op=lookup[key]
        yds+=op["rushingYards"];att+=op["rushingAttempts"]
    if att<=0:return None,"no attempts"
    return yds/att,""

rows=[];missing=collections.Counter();previous={}
for week in range(1,8):
    for g in games_by_week[week]:
        h=previous.get(g["hid"]);a=previous.get(g["aid"])
        if h and a and h[1]!=a[1] and week>=2:
            higher="home" if h[1]>a[1] else "away"
            won=int(g["winner"]==higher)
            rg=byid.loc[g["id"]] if g["id"] in byid.index else None
            grouping=(group(rg.home_conference,rg.home_team),group(rg.away_conference,rg.away_team)) if rg is not None else (None,None)
            bucket=grouping[0] if grouping[0] is not None and grouping[0]==grouping[1] else "outside"
            home_ypc,hreason=defense(g,"home")
            away_ypc,areason=defense(g,"away")
            if home_ypc is None or away_ypc is None: agree=None;missing[hreason or areason]+=1
            elif home_ypc==away_ypc:agree="tie"
            else:agree=(home_ypc<away_ypc)==(higher=="home")
            rows.append(dict(week=week,game_id=g["id"],matchup=f'{g["away"]} at {g["home"]}',group=bucket,
                higher_qbr_team=g[higher],winner_team=g[g["winner"]] if g["winner"] else None,
                win=won,qbr_higher=h[1] if higher=="home" else a[1],qbr_lower=a[1] if higher=="home" else h[1],
                hqb=h[0],aqb=a[0],hqb_qbr=h[1],aqb_qbr=a[1],
                home_run_def_ypc=home_ypc,away_run_def_ypc=away_ypc,agrees=agree))
        elif week>=2:missing["missing prior QBR or tied"]+=1
        current=qbr_by_game.get(g["id"],{})
        for team in [g["hid"],g["aid"]]:
            if team in current:previous[team]=current[team]

data=pd.DataFrame(rows)
print("MATCHED",len(data),"ORIGINAL_BASELINE_WINS",int(data.win.sum()),"LOSSES",len(data)-int(data.win.sum()),flush=True)
print("MISSING",repr(missing),flush=True)
def report(frame,label):
    n=len(frame);wins=int(frame.win.sum()) if n else 0
    print("RESULT",label,"W",wins,"L",n-wins,"N",n,"PCT",round(100*wins/n,1) if n else None,flush=True)
report(data,"ALL_QBR_WITH_ANY_DEFENSE")
for bucket in ["P4","G6","outside"]:
    sub=data[data.group==bucket]
    report(sub,bucket+"_QBR_ALL")
    for flag in [True,False,"tie",None]:
        filt=sub[sub.agrees.map(lambda x:x is flag or x==flag if x is not None else flag is None)]
        report(filt,bucket+"_RUN_AGREES_"+str(flag).upper())
    for wk in range(2,8):
        report(sub[(sub.week==wk)&(sub.agrees==True)],bucket+"_RUN_AGREES_WEEK_"+str(wk))
    for lo,hi in [(0,0.5),(0.5,1),(1,2),(2,999)]:
        f=sub[sub.agrees==True].copy()
        f["gap"]=(f.home_run_def_ypc-f.away_run_def_ypc).abs()
        report(f[(f.gap>=lo)&(f.gap<hi)],bucket+"_RUN_EDGE_"+str(lo)+"_"+str(hi))
    for _,row in sub[sub.agrees==True].iterrows():
        print("QUALIFYING_GAME",json.dumps({"week":int(row.week),"matchup":row.matchup,"group":bucket,
            "qbr_team":row.higher_qbr_team,"winner":row.winner_team,"win":int(row.win),
            "qbr_high":round(row.qbr_higher,1),"qbr_low":round(row.qbr_lower,1),
            "home_ypc":round(row.home_run_def_ypc,3),"away_ypc":round(row.away_run_def_ypc,3)}),flush=True)
for wk in range(2,8):
    report(data[(data.week==wk)&(data.group.isin(["P4","G6"]))&(data.agrees==True)],"ALL_QUALIFYING_WEEK_"+str(wk))
report(data[(data.group.isin(["P4","G6"]))&(data.agrees==True)],"ALL_QUALIFYING_COMBINED")
print("DONE",flush=True)


selected=data[(data.group.isin(["P4","G6"]))&(data.agrees==True)].copy()
selected["def_gap"]=(selected.home_run_def_ypc-selected.away_run_def_ypc).abs()
selected=selected[selected.def_gap>=2]
print("SELECTED",len(selected),flush=True)
market_url="https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_betting/betting_2026.csv"
try:
    market=frameget(market_url)
    print("MARKET_SCHEMA",repr(market.columns.tolist()),"N",len(market),flush=True)
    print("MARKET_SAMPLE",repr(market.iloc[0].to_dict()),flush=True)
except Exception as e: print("MARKET_ERROR",str(e)[:300],flush=True)
for i,row in selected.iterrows():
    if i>2:break
    try:
        ev=jsonget("https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary?event="+row.game_id)
        print("ESPN_ODDS_SCHEMA",row.game_id,"pickcenter",repr(ev.get("pickcenter"))[:2000],
            "header_odds",repr(ev.get("header",{}).get("competitions",[{}])[0].get("odds"))[:1200],flush=True)
    except Exception as e:print("ESPN_ODDS_ERROR",row.game_id,str(e)[:150],flush=True)


archive_path="data/archived_moneylines_2026.json"
try:
    with open(archive_path,encoding="utf8") as f: archived=json.load(f).get("events",{})
except Exception: archived={}
market["game_id"]=market.game_id.astype(str)
for _,row in selected.sort_values(["week","group","matchup"]).iterrows():
    gid=row.game_id
    line=market[market.game_id.eq(gid)]
    spreads=[]
    for _,v in line.iterrows():
        spreads.append({"home_spread":v.home_team_spread,"source":v.odds_source,"available":v.game_spread_available})
    arch=archived.get(gid,{}).get("quotes",{})
    pick={}
    try:
        ev=jsonget("https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary?event="+gid)
        for p in ev.get("pickcenter",[]) or ev.get("header",{}).get("competitions",[{}])[0].get("odds",[]):
            name=p.get("provider",{}).get("name","unknown") if isinstance(p.get("provider"),dict) else "unknown"
            pick[name]={"homeTeamOdds":p.get("homeTeamOdds"),"awayTeamOdds":p.get("awayTeamOdds"),"spread":p.get("spread"),"details":p.get("details")}
    except Exception as e:pick={"error":str(e)[:100]}
    print("ODDS_GAME",json.dumps({"week":int(row.week),"game_id":gid,"matchup":row.matchup,"team":row.higher_qbr_team,"win":int(row.win),"group":row.group,"def_gap":round(row.def_gap,3),"spreads":spreads,"archived":arch,"pickcenter":pick}),flush=True)


# Check whether promising QBR gaps merely identify market favorites.
market=market.dropna(subset=["game_id","home_team_spread"])
market["home_team_spread"]=numeric(market.home_team_spread)
market=market[market.game_spread_available.astype(str).str.casefold().isin(["true","t","1","1.0","yes"])]
market=market[~market.odds_source.astype(str).str.casefold().eq("default")]
market=market.drop_duplicates(subset=["game_id"],keep="last").set_index("game_id")
data["qbr_gap"]=(data.hqb_qbr-data.aqb_qbr).abs()
data["qbr_home"]=data.apply(lambda x:x.higher_qbr_team==x.matchup.rsplit(" at ",1)[-1],axis=1)
data["home_line"]=data.game_id.map(market.home_team_spread)
data["pick_favorite"]=data.apply(lambda x: bool((x.home_line<0)==x.qbr_home) if pd.notna(x.home_line) and x.home_line!=0 else None,axis=1)
for grp in ["P4","G6","ALL"]:
    base=data if grp=="ALL" else data[data.group==grp]
    if grp=="ALL":base=base[base.group.isin(["P4","G6"])]
    for lo,hi in [(0,10),(10,20),(20,30),(30,40),(40,101)]:
        f=base[(base.qbr_gap>=lo)&(base.qbr_gap<hi)]
        good=f[f.pick_favorite==True];dogs=f[f.pick_favorite==False]
        print("MAGNITUDE_MARKET",json.dumps({"group":grp,"bin":f"{lo}-{hi}","games":len(f),"wins":int(f.win.sum()),"fav_games":len(good),"fav_wins":int(good.win.sum()),"dog_games":len(dogs),"dog_wins":int(dogs.win.sum()),"odds_unavailable":int(f.pick_favorite.isna().sum())}),flush=True)
near=data[(data.group=="P4")&(data.qbr_gap<10)].sort_values(["week","matchup"])
roi_profit=0;roi_count=0
for _,row in near.iterrows():
    market_line=float(row.home_line) if pd.notna(row.home_line) else None
    ml=None;src=None
    try:
        ev=jsonget("https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary?event="+row.game_id)
        for price in ev.get("pickcenter",[]):
            prov=price.get("provider",{}).get("name","")
            if prov.lower() != "draftkings":continue
            side="homeTeamOdds" if row.qbr_home else "awayTeamOdds"
            ml=price.get(side,{}).get("moneyLine")
            src=prov
            break
    except Exception as exc:src=str(exc)[:90]
    if ml is not None and int(ml)!=0:
        num=int(ml);ret=(10000/abs(num) if num<0 else num) if row.win else -100
        roi_profit+=ret;roi_count+=1
    print("P4_SMALL_QBR_GAME",json.dumps({"week":int(row.week),"matchup":row.matchup,"team":row.higher_qbr_team,"qbr_gap":round(row.qbr_gap,1),"win":int(row.win),"home_line":market_line,"was_favorite":row.pick_favorite,"moneyline":ml,"source":src}),flush=True)
print("P4_SMALL_QBR_ROI",json.dumps({"bets":roi_count,"profit_100_per_game":round(roi_profit,2),"roi_pct":round(roi_profit/roi_count,4) if roi_count else None}),flush=True)
