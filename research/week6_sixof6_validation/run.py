from pathlib import Path
from urllib.request import urlopen
import json
import sys
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from matchup_advantages import build_advantages, assess, conference_group

OUT = Path(__file__).resolve().parent / "week6_sixof6.json"

SCHEDULE_URL = "https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_2026.csv"
BOX_URL = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_team_box/team_box_2026.csv"

def load_csv(url):
    with urlopen(url, timeout=60) as r:
        return pd.read_csv(r)

schedule = load_csv(SCHEDULE_URL)
boxes = load_csv(BOX_URL)

for col in ("neutral_site", "completed"):
    schedule[col] = schedule[col].astype(str).str.lower().isin(["true","t","1","1.0","yes","y"])

checks = build_advantages(schedule, boxes, 6)
week6 = schedule[(schedule["season"] == 2026) & (schedule["season_type"] == "regular") & (schedule["week"] == 6)].copy()

rows = []
for _, g in week6.iterrows():
    gid = str(int(g.game_id))
    rec = checks.get(gid, {"status": "missing", "reason": "No record"})
    hg = conference_group(g.home_conference, g.home_team)
    ag = conference_group(g.away_conference, g.away_team)
    row = {
        "game_id": int(g.game_id),
        "kickoff": g.start_date,
        "home": g.home_team,
        "away": g.away_team,
        "home_conference": g.home_conference,
        "away_conference": g.away_conference,
        "group": hg if hg == ag else None,
        "neutral": bool(g.neutral_site),
        "status": rec.get("status"),
        "reason": rec.get("reason"),
        "home_advantages": None,
        "away_advantages": None,
        "qualifier_6_of_6": False,
        "five_metric_outcomes_home": None,
    }
    if rec.get("status") == "ok":
        ha = assess(rec, "home")
        aa = assess(rec, "away")
        hcount = ha["count"] + (0 if bool(g.neutral_site) else 1)
        acount = aa["count"]
        row["home_advantages"] = int(hcount)
        row["away_advantages"] = int(acount)
        row["five_metric_outcomes_home"] = ha["outcomes"]
        row["qualifier_6_of_6"] = (not bool(g.neutral_site) and hcount == 6 and acount == 0)
    rows.append(row)

payload = {
    "season": 2026,
    "week": 6,
    "method": "Exact prior test methodology: five equal-weight statistical advantages from earlier-week current-season FBS history plus home venue; ties count for neither side; P4/P4 and G6/G6 only; Notre Dame P4.",
    "qualifiers": [r for r in rows if r["qualifier_6_of_6"]],
    "all_games": rows,
}
OUT.write_text(json.dumps(payload, indent=2))
print(json.dumps(payload["qualifiers"], indent=2))
