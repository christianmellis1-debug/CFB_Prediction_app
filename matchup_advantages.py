"""Five-metric research flag; never modifies model probabilities or selections."""
from html import escape
import numpy as np
import pandas as pd
P4={'ACC','Big Ten','Big 12','SEC'}
G6={'American Athletic','Conference USA','Mid-American','Mountain West','Sun Belt','Pac-12'}
LABELS=('Rushing matchup estimate','Completion matchup estimate','Run defense · YPC allowed','Pass defense · completion allowed','Turnover margin · per game')

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
    for c in ('turnovers','fumblesLost','interceptions'):
        b[c]=pd.to_numeric(b.get(c, pd.Series(np.nan,index=b.index)),errors='coerce')
    b['to_valid']=np.isfinite(b[['turnovers','fumblesLost','interceptions']]).all(axis=1) & b[['turnovers','fumblesLost','interceptions']].ge(0).all(axis=1) & b[['turnovers','fumblesLost','interceptions']].mod(1).eq(0).all(axis=1) & b.turnovers.eq(b.fumblesLost+b.interceptions)
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
            totals=np.zeros(10)
            for _,old in games.iterrows():
                opp=old.away_id if old.home_id==tid else old.home_id
                keys=[(old.game_id,tid),(old.game_id,opp)]
                if not all(k in lookup.index for k in keys):
                    reason='Earlier-week FBS box scores are incomplete or invalid.';break
                own,other=[lookup.loc[k] for k in keys]
                if not own.to_valid or not other.to_valid:
                    reason='Earlier-week FBS turnover data are missing or inconsistent.';break
                totals+=np.array([own.rushingYards,own.rushingAttempts,own.comp,own.att,other.rushingYards,other.rushingAttempts,other.comp,other.att,own.turnovers,other.turnovers])
            if reason:break
            if min(totals[[1,3,5,7]])<=0:
                reason='Not enough rushing or passing attempts to calculate all five metrics.';break
            profiles.append(dict(off_run=totals[0]/totals[1],off_pass=totals[2]/totals[3],def_run=totals[4]/totals[5],def_pass=totals[6]/totals[7],games=len(games),margin=(totals[9]-totals[8])/len(games)))
        if reason:
            out[gid]={'status':'missing','reason':reason};continue
        h,a=profiles
        hv=[(h['off_run']+a['def_run'])/2,(h['off_pass']+a['def_pass'])/2,h['def_run'],h['def_pass'],h['margin']]
        av=[(a['off_run']+h['def_run'])/2,(a['off_pass']+h['def_pass'])/2,a['def_run'],a['def_pass'],a['margin']]
        out[gid]={'status':'ok','home':hv,'away':av,'home_games':h['games'],'away_games':a['games'],'group':hg}
    return out

def assess(record, side):
    if record.get('status')!='ok':return None
    own=record[side];other=record['away' if side=='home' else 'home']
    deltas=[(x-y)*(1 if i in (0,1,4) else -1) for i,(x,y) in enumerate(zip(own,other))]
    outcomes=['Advantage' if v>1e-10 else 'Tied' if abs(v)<=1e-10 else 'Disadvantage' for v in deltas]
    count=outcomes.count('Advantage')
    return dict(count=count,flag=count<=2,outcomes=outcomes)

def advantage_html(record, side, picked_team):
    status=record.get('status')
    if status!='ok':
        label='Not assessed' if status=='outside' else 'Not enough data'
        return '<details class="card-details"><summary>Advantage check · '+label+'</summary><p>'+escape(record.get('reason','Pregame box scores unavailable.'))+'</p></details>'
    scored=assess(record,side);count=scored['count'];team=escape(str(picked_team))
    banner=(f'<div style="margin-top:10px;padding:10px 12px;border-left:4px solid #e9a23b;border-radius:6px;background:#e9a23b18"><strong>⚠ Matchup risk · {count}/5 advantages</strong><br><span>{team} has limited support from these five metrics.</span></div>' if scored['flag'] else '')
    other='away' if side=='home' else 'home';items=[]
    for i,label in enumerate(LABELS):
        fmt=(lambda x:f'{x:+.2f} per game') if i==4 else (lambda x:f'{x:.1%}') if i in (1,3) else (lambda x:f'{x:.2f} YPC')
        direction='higher is better' if i in (0,1,4) else 'lower is better'
        items.append(f'<li><strong>{label}</strong>: {fmt(record[side][i])} vs {fmt(record[other][i])} · {scored["outcomes"][i]} ({direction})</li>')
    return banner+f'<details class="card-details"><summary>Five-metric check · {count}/5 advantages</summary><p>Values compare {team} with its opponent.</p><ul>'+''.join(items)+f'</ul><p>Earlier-week FBS games: pick {record[side+"_games"]}, opponent {record[other+"_games"]}. Rates use total yards/completions divided by total attempts. Turnover margin = (takeaways minus giveaways) / earlier-week FBS games. Ties do not count as advantages.</p><p>This research flag is not a loss probability. Metrics overlap, and no flag does not mean a safe bet. Current model confidence and value labels are unchanged.</p></details>'


# Raw profiles for the waterfall are deliberately separate from blended risk metrics.
def normalize_fbs_schedule(schedule):
    """Season-aware eligibility; missing division metadata fails closed."""
    s = schedule.copy()
    years = pd.to_numeric(s.get('season', pd.Series(index=s.index, dtype=float)), errors='coerce')
    for side in ('home', 'away'):
        col = side + '_division'
        if col not in s:
            s[col] = None
        names = s.get(side + '_team', pd.Series('', index=s.index)).astype(str).str.strip().str.casefold()
        sac = names.isin(['sacramento state', 'sac state', 'sacramento state hornets'])
        s.loc[sac & years.ge(2026), col] = 'fbs'
        s.loc[sac & years.lt(2026), col] = 'fcs'
        s.loc[sac & years.ge(2026), side + '_conference'] = 'Mid-American'
    return s[s.home_division.astype(str).str.lower().eq('fbs') &
             s.away_division.astype(str).str.lower().eq('fbs')].copy()


def build_waterfall_profiles(schedule, boxes, week):
    """Raw current-season FBS-only rates before the target week AND kickoff.

    No prior-season fallback, partial-history averages, or passing-stat dependency.
    off_run/def_run use total yards / total attempts; margin is per FBS game.
    """
    s = normalize_fbs_schedule(schedule)
    required = {'season', 'week', 'game_id', 'home_id', 'away_id', 'start_date', 'completed'}
    if not required.issubset(s):
        return {}
    for col in ('season', 'week', 'game_id', 'home_id', 'away_id'):
        s[col] = pd.to_numeric(s[col], errors='coerce')
    s = s.dropna(subset=['season', 'week', 'game_id', 'home_id', 'away_id'])
    s['start'] = pd.to_datetime(s.start_date, utc=True, errors='coerce')
    completed = s.completed.astype(str).str.lower().isin(['true', 't', '1', '1.0', 'yes', 'y'])
    cols = ['game_id', 'team_id', 'rushingYards', 'rushingAttempts', 'turnovers', 'fumblesLost', 'interceptions']
    if not set(cols).issubset(boxes):
        return {}
    b = boxes[cols].apply(pd.to_numeric, errors='coerce')
    valid = np.isfinite(b).all(axis=1) & ~b.duplicated(['game_id', 'team_id'], keep=False)
    valid &= b.rushingAttempts.gt(0) & b.rushingAttempts.mod(1).eq(0)
    to = b[['turnovers', 'fumblesLost', 'interceptions']]
    valid &= to.ge(0).all(axis=1) & to.mod(1).eq(0).all(axis=1)
    valid &= b.turnovers.eq(b.fumblesLost + b.interceptions)
    lookup = b[valid].set_index(['game_id', 'team_id'])
    out = {}
    for _, g in s[s.week.eq(int(week))].iterrows():
        gid = str(int(g.game_id))
        record = {'status': 'missing', 'reason': 'Incomplete earlier-week FBS history.'}
        out[gid] = record
        if pd.isna(g.start) or s.game_id.eq(g.game_id).sum() != 1:
            continue
        history = s[completed & s.season.eq(g.season) & s.week.lt(g.week) & s.start.lt(g.start)]
        profiles = {}
        for side in ('home', 'away'):
            tid = g[side + '_id']
            games = history[history.home_id.eq(tid) | history.away_id.eq(tid)]
            if games.empty or games.game_id.duplicated().any():
                break
            totals = np.zeros(6)
            for _, old in games.iterrows():
                opp = old.away_id if old.home_id == tid else old.home_id
                keys = [(old.game_id, tid), (old.game_id, opp)]
                if not all(k in lookup.index for k in keys):
                    break
                own, other = [lookup.loc[k] for k in keys]
                totals += [own.rushingYards, own.rushingAttempts, other.rushingYards,
                           other.rushingAttempts, own.turnovers, other.turnovers]
            else:
                profiles[side] = {'off_run': totals[0] / totals[1],
                                  'def_run': totals[2] / totals[3],
                                  'margin': (totals[5] - totals[4]) / len(games),
                                  'games': len(games)}
        if len(profiles) == 2:
            record.update(status='ok', reason='', **profiles)
    return out



def build_tier5_four_factor(schedule, summaries, week):
    """Official Tier 5: strict P4 home team owns all four prior-week factors."""
    out = {}
    week = int(week)
    s = normalize_fbs_schedule(schedule).copy()
    required_game = {'game_id', 'week', 'season_type', 'home_id', 'away_id',
                     'home_team', 'away_team', 'home_conference', 'away_conference',
                     'neutral_site'}
    required_stats = {'team_id', 'through_week', 'red_zone_success_off',
                      'red_zone_success_def', 'explosive_off', 'explosive_def'}
    if not required_game.issubset(s) or not required_stats.issubset(summaries) or week <= 1:
        return out

    for col in ('game_id', 'week', 'home_id', 'away_id'):
        s[col] = pd.to_numeric(s[col], errors='coerce')
    targets = s[s.week.eq(week)].dropna(subset=['game_id', 'home_id', 'away_id'])

    stats = summaries[list(required_stats)].copy()
    for col in required_stats:
        stats[col] = pd.to_numeric(stats[col], errors='coerce')
    stats = stats[stats.through_week.eq(week - 1)].dropna(subset=['team_id'])
    duplicate_ids = set(stats.loc[stats.team_id.duplicated(keep=False), 'team_id'].astype(int))
    stats = stats[~stats.team_id.duplicated(keep=False)].set_index('team_id')

    for _, game in targets.iterrows():
        gid = str(int(game.game_id))
        record = {'status': 'outside', 'qualifies': False}
        out[gid] = record

        neutral_raw = str(game.get('neutral_site', '')).lower()
        if neutral_raw not in ('false', 'f', '0', '0.0', 'no', 'n'):
            record['reason'] = 'Tier 5 requires a non-neutral home game.'
            continue
        if str(game.get('season_type', '')).lower() != 'regular':
            record['reason'] = 'Tier 5 applies to regular-season games only.'
            continue
        # This rule was validated with the four power conferences only.
        if game.get('home_conference') not in P4 or game.get('away_conference') not in P4:
            record['reason'] = 'Tier 5 requires ACC, Big Ten, Big 12, or SEC on both sides.'
            continue

        hid, aid = int(game.home_id), int(game.away_id)
        if hid in duplicate_ids or aid in duplicate_ids or hid not in stats.index or aid not in stats.index:
            record.update(status='missing', reason=f'Exact through-week {week - 1} summary unavailable.')
            continue
        home, away = stats.loc[hid], stats.loc[aid]
        cols = ('red_zone_success_off', 'red_zone_success_def', 'explosive_off', 'explosive_def')
        if not all(np.isfinite(home[col]) and np.isfinite(away[col]) for col in cols):
            record.update(status='missing', reason='One or more Tier 5 metrics are unavailable.')
            continue

        edges = {
            'red_zone_offense': bool(home.red_zone_success_off > away.red_zone_success_off),
            'red_zone_defense': bool(home.red_zone_success_def < away.red_zone_success_def),
            'explosive_offense': bool(home.explosive_off > away.explosive_off),
            'explosive_defense': bool(home.explosive_def < away.explosive_def),
        }
        record.update(
            status='ok',
            qualifies=all(edges.values()),
            reason='Home team is better in all four prior-week Tier 5 metrics.' if all(edges.values())
                   else 'Home team does not own all four Tier 5 edges.',
            through_week=week - 1,
            edges=edges,
            home={col: float(home[col]) for col in cols},
            away={col: float(away[col]) for col in cols},
        )
    return out


WATERFALL_TIERS = {
    1: 'Tier 1: Complete Game',
    2: 'Tier 2: Storm Front',
    3: 'Tier 3: Takeaway Trouble',
    4: 'Tier 4: The Foundation',
    5: 'Tier 5: Home Turf Hammer',
}


def _spread_number(value):
    if value is None or isinstance(value, bool):
        return np.nan
    raw = str(value).strip().replace('−', '-').replace('+', '')
    if raw.upper() in ('PK', 'PICK', 'PICKEM', "PICK'EM"):
        return 0.0
    try:
        number = float(raw)
        return number if np.isfinite(number) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _six_of_six_band(line):
    if -13.5 <= line <= -7:
        return 0, 'Prime 6/6'
    if -7 < line <= 0:
        return 1, 'Standard 6/6'
    if line > 0:
        return 2, '6/6 Market Disagreement'
    return 3, '6/6 Heavy Favorite'


def weather_tier_candidate_ids(predictions, schedule, profiles):
    """Games that satisfy Tier 2's non-weather gates and therefore need weather."""
    games = normalize_fbs_schedule(schedule).copy()
    if 'game_id' not in games:
        return []
    games['_id'] = pd.to_numeric(games.game_id, errors='coerce')
    games = games.dropna(subset=['_id'])
    games = games[~games._id.duplicated(keep=False)].set_index('_id')
    ids = []
    seen = set()
    for _, row in predictions.iterrows():
        try:
            gid = int(row['Game ID'])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if gid in seen or gid not in games.index:
            continue
        seen.add(gid)
        game = games.loc[gid]
        neutral_raw = str(game.get('neutral_site', '')).lower()
        if neutral_raw not in ('false', 'f', '0', '0.0', 'no', 'n'):
            continue
        rec = profiles.get(str(gid), {})
        spread = _spread_number(row.get('Home Spread'))
        if (rec.get('status') == 'ok'
                and rec['home']['def_run'] < rec['away']['def_run']
                and rec['home']['margin'] > rec['away']['margin']
                and np.isfinite(spread) and spread > -14):
            ids.append(gid)
    return ids


def select_waterfall(predictions, schedule, profiles, advantage_checks=None, weather_checks=None,
                     tier5_checks=None, minimum=12, maximum=18):
    """Weekly sequential card with ATS tiers first.

    The minimum/maximum values describe preferred weekly volume only.
    They never suppress a game that satisfies an official tier rule.

    Tier 1 is exact 6/6 ATS dominance.
    Tier 2 is the frozen weather defensive-edge ATS rule:
    outdoor inclement weather, non-neutral home team, lower pregame defensive
    rushing YPC allowed, better pregame turnover margin/game, and spread > -14.
    Tier 3 is the P4 short-underdog turnover rule:
    P4 vs P4, market favorite -110 through -150, and underdog pregame
    turnover margin/game at least +1.0 better than the favorite.
    Tier 4 is the official heavy-favorite straight-up rule:
    Week 4 or later, regular-season FBS vs FBS, DraftKings favorite priced
    from -505 through -1000 inclusive. Tier 5 is the official straight-up
    four-factor home-dominance rule using the exact prior-week published
    team-summary snapshot.
    """
    if not 1 <= minimum <= maximum:
        raise ValueError('Require 1 <= minimum <= maximum')
    games = normalize_fbs_schedule(schedule).copy()
    if 'game_id' not in games:
        return []
    games['_id'] = pd.to_numeric(games.game_id, errors='coerce')
    games = games.dropna(subset=['_id'])
    games = games[~games._id.duplicated(keep=False)].set_index('_id')
    candidates = {1: [], 2: [], 3: [], 4: [], 5: []}
    advantage_checks = advantage_checks or {}
    weather_checks = weather_checks or {}
    tier5_checks = tier5_checks or {}
    seen = set()

    for _, row in predictions.iterrows():
        try:
            gid = int(row['Game ID'])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if gid in seen or gid not in games.index:
            continue
        seen.add(gid)
        game = games.loc[gid]
        neutral_raw = str(game.get('neutral_site', '')).lower()
        if neutral_raw not in ('true', 't', '1', '1.0', 'yes', 'y', 'false', 'f', '0', '0.0', 'no', 'n'):
            continue
        neutral = neutral_raw in ('true', 't', '1', '1.0', 'yes', 'y')

        # Tier 1: exact six-of-six = all five statistical advantages + home field.
        check = advantage_checks.get(str(gid), {})
        home_check = assess(check, 'home') if check.get('status') == 'ok' else None
        spread = _spread_number(row.get('Home Spread'))
        if not neutral and home_check and home_check['count'] == 5 and np.isfinite(spread):
            band_order, band = _six_of_six_band(spread)
            spread_text = str(row.get('Home Spread', '')).strip() or f'{spread:+g}'
            candidates[1].append({
                'Game ID': gid,
                'Value Tier': WATERFALL_TIERS[1],
                'Value Stage': 1,
                'Value Pick': game['home_team'],
                'Value Side': 'Home',
                'Value Line': spread_text,
                'Value Price': row.get('Home Spread Odds', 'Unavailable'),
                'Value Market': 'Spread',
                'Value Source': row.get('Spread Source', 'Unavailable'),
                'Value Band': band,
                'Value Reason': 'Exact 6/6: home team owns all five statistical matchup advantages plus home field.',
                '_sort': (band_order, str(game.get('start_date', '')), gid),
            })
            continue

        rec = profiles.get(str(gid), {})

        # Tier 2: frozen weather defensive-edge ATS rule.
        # The -14 exclusion is part of the published rule because the validation
        # sample was 12-2-1 ATS when the selected home team's spread was > -14,
        # while -14 or larger favorites were 7-7 ATS.
        weather = weather_checks.get(str(gid), {})
        if (not neutral and rec.get('status') == 'ok'
                and weather.get('status') == 'ok' and weather.get('inclement') is True
                and rec['home']['def_run'] < rec['away']['def_run']
                and rec['home']['margin'] > rec['away']['margin']
                and np.isfinite(spread) and spread > -14):
            spread_text = str(row.get('Home Spread', '')).strip() or f'{spread:+g}'
            weather_type = str(weather.get('weather_type') or 'Inclement weather')
            candidates[2].append({
                'Game ID': gid,
                'Value Tier': WATERFALL_TIERS[2],
                'Value Stage': 2,
                'Value Pick': game['home_team'],
                'Value Side': 'Home',
                'Value Line': spread_text,
                'Value Price': row.get('Home Spread Odds', 'Unavailable'),
                'Value Market': 'Spread',
                'Value Source': row.get('Spread Source', 'Unavailable'),
                'Value Band': weather_type,
                'Value Reason': (
                    f'{weather_type}: home team has lower defensive YPC allowed and '
                    'better turnover margin/game; validated ATS rule excludes spreads of -14 or shorter.'
                ),
                '_sort': (spread, str(game.get('start_date', '')), gid),
            })
            continue

        # Tiers 3-4 use market/profile gates. Tier 5 does not require a price:
        # it is a straight-up signal from the exact prior-week published snapshot.
        tier5 = tier5_checks.get(str(gid), {})
        stage, side, reason = None, None, ''
        lines = {}
        try:
            hline, aline = float(row['DK Home ML']), float(row['DK Away ML'])
            valid_lines = all(np.isfinite(n) and abs(n) >= 100 and n.is_integer() for n in (hline, aline))
        except (KeyError, TypeError, ValueError, OverflowError):
            valid_lines = False

        if valid_lines:
            if hline < 0 < aline:
                fav, dog = 'home', 'away'
            elif aline < 0 < hline:
                fav, dog = 'away', 'home'
            else:
                fav = dog = None
            if fav is not None:
                lines = {'home': hline, 'away': aline}

                # Tier 3 still requires its validated pregame profile gate.
                if rec.get('status') == 'ok':
                    f, d = rec[fav], rec[dog]
                    if all(np.isfinite(p.get(k, np.nan)) for p in (f, d) for k in ('off_run', 'def_run', 'margin')):
                        fav_group = conference_group(game.get(fav + '_conference'), game.get(fav + '_team'))
                        dog_group = conference_group(game.get(dog + '_conference'), game.get(dog + '_team'))
                        turnover_edge = d['margin'] - f['margin']
                        if (-150 <= lines[fav] <= -110
                                and fav_group == 'P4' and dog_group == 'P4'
                                and turnover_edge >= 1.0 - 1e-10):
                            stage, side = 3, dog
                            reason = (
                                f'P4 vs P4 short underdog: favorite priced {int(lines[fav]):+d}; '
                                f'underdog turnover margin/game edge {turnover_edge:+.2f}. '
                                'Recommended bet is the underdog moneyline.'
                            )

                # Official Tier 4: no model/profile requirement. The market-price
                # band and Week 4+ cutoff are the complete straight-up rule.
                game_week = pd.to_numeric(game.get('week'), errors='coerce')
                regular = str(game.get('season_type', '')).lower() == 'regular'
                if (stage is None and regular and np.isfinite(game_week) and game_week >= 4
                        and -1000 <= lines[fav] <= -505):
                    stage, side = 4, fav
                    reason = (
                        f'Official Tier 4 SU rule: Week {int(game_week)} FBS vs FBS favorite '
                        f'priced {int(lines[fav]):+d}, inside the validated -505 through -1000 range.'
                    )

        if stage is None and tier5.get('status') == 'ok' and tier5.get('qualifies') is True:
            stage, side = 5, 'home'
            reason = (
                f'Official Tier 5 SU rule: non-neutral P4 home team is better in prior-week '
                f'red-zone offense, red-zone defense, explosive offense, and explosive defense '
                f'(snapshot through Week {tier5.get("through_week")}).'
            )

        if stage:
            if stage == 5:
                raw_line = row.get('DK Home ML', 'Unavailable')
                try:
                    number = float(raw_line)
                    line_text = f'{int(number):+d}' if np.isfinite(number) and number.is_integer() else str(raw_line)
                except (TypeError, ValueError, OverflowError):
                    line_text = 'Unavailable'
                price = line_text
                source = 'DraftKings' if line_text != 'Unavailable' else 'Published weekly metrics'
            else:
                line_text = f'{int(lines[side]):+d}'
                price = line_text
                source = 'DraftKings'
            candidates[stage].append({
                'Game ID': gid,
                'Value Tier': WATERFALL_TIERS[stage],
                'Value Stage': stage,
                'Value Pick': game[side + '_team'],
                'Value Side': side.title(),
                'Value Line': line_text,
                'Value Price': price,
                'Value Market': 'Moneyline',
                'Value Source': source,
                'Value Band': 'Straight Up' if stage in (4, 5) else '',
                'Value Reason': reason,
                '_sort': (str(game.get('start_date', '')), gid),
            })

    # Surface every official qualifier. The 12-18 range is a planning target,
    # not a selection gate or hard weekly cap.
    card = []
    for stage in (1, 2, 3, 4, 5):
        for item in sorted(candidates[stage], key=lambda candidate: candidate['_sort']):
            item = item.copy()
            item.pop('_sort')
            item['Value Rank'] = len(card) + 1
            card.append(item)
    return card
