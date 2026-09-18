"""Conference calibration audit; research only, never modifies production.

Inputs: schedule2024/2025.csv, summary2023/2024/2025.csv at repo root.
Use season-specific conference fields; exclude FCS, independents and the
two-member 2024/2025 Pac-12 from the P4-versus-G5 comparison.
Fit one log-odds offset on 2024, evaluate once on 2025 (temporal holdout).
Historical summaries can be revised; these are reconstructed predictions.
"""
import ast
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.special import expit, logit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model_v1_4_reference import predict_week

P4 = {'ACC', 'Big Ten', 'Big 12', 'SEC'}
G5 = {'American Athletic', 'Conference USA', 'Mid-American', 'Mountain West', 'Sun Belt'}

def normalize(s):
    s = s[(s.home_division == 'fbs') & (s.away_division == 'fbs') & (s.season_type == 'regular')].copy()
    for col in ['completed', 'neutral_site']:
        s[col] = s[col].astype(str).str.lower().isin(['true', 't', '1', '1.0', 'yes', 'y'])
    return s.sort_values('start_date', kind='stable')

def metrics(d, col):
    p = np.clip(d[col].to_numpy(), 1e-8, 1-1e-8)
    y = d.y.to_numpy()
    return {'games': len(d), 'brier': float(np.mean((p-y)**2)),
            'log_loss': float(np.mean(-y*np.log(p)-(1-y)*np.log(1-p))),
            'accuracy': float(np.mean((p>=.5)==y))}

def build(year):
    s = normalize(pd.read_csv(ROOT/f'schedule{year}.csv'))
    assert s.game_id.is_unique
    cur = pd.read_csv(ROOT/f'summary{year}.csv', low_memory=False)
    prior = pd.read_csv(ROOT/f'summary{year-1}.csv', low_memory=False)
    # Use the same missing-team augmentation as the production app.
    source = ROOT/'app.py'
    tree = ast.parse(source.read_text())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name=='augment_missing_summaries')
    ns = {'pd':pd}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(source), 'exec'), ns)
    predictions = []
    for week in sorted(s.week.unique()):
        current, _ = ns['augment_missing_summaries'](cur, prior, s, week)
        predictions.append(predict_week(current, prior, s, int(week), include_completed=True))
    d = pd.concat(predictions).merge(s, left_on='Game ID', right_on='game_id', validate='one_to_one')
    d = d[d.completed & d.home_points.notna() & d.away_points.notna() & d.home_points.ne(d.away_points)].copy()
    d['y'] = (d.home_points>d.away_points).astype(int)
    d['sign'] = np.select([d.home_conference.isin(P4)&d.away_conference.isin(G5),d.away_conference.isin(P4)&d.home_conference.isin(G5)],[1,-1],default=0)
    d['baseline'] = d['Home Win %']
    return d

def main():
    frames = {y:build(y) for y in [2024,2025]}
    train = frames[2024].query('sign != 0')
    def objective(offset):
        p = expit(logit(train.baseline)+offset*train.sign)
        return float(np.mean(-train.y*np.log(p)-(1-train.y)*np.log1p(-p)))
    offset = float(minimize_scalar(objective, bounds=(-3,3), method='bounded').x)
    result = {'method':'Fit a single conference log-odds offset on 2024; hold out 2025. No production change.', 'offset':offset,'seasons':{}}
    for year,d in frames.items():
        d['candidate'] = expit(logit(d.baseline)+offset*d.sign)
        cross = d[d.sign.ne(0)].copy()
        cross['p4_won'] = np.where(cross.sign.eq(1), cross.y, 1-cross.y)
        cross['p4_probability'] = np.where(cross.sign.eq(1),cross.baseline,1-cross.baseline)
        info = {'p4_wins':int(cross.p4_won.sum()),'games':len(cross),'actual_p4_win_rate':float(cross.p4_won.mean()),'baseline_mean_p4_probability':float(cross.p4_probability.mean()),
                'cross_baseline':metrics(cross,'baseline'),'cross_candidate':metrics(cross,'candidate'),
                'all_baseline':metrics(d,'baseline'),'all_candidate':metrics(d,'candidate')}
        info['by_venue'] = {}
        for name,subset in [('P4 home',cross[cross.sign.eq(1)&~cross.neutral_site]),('P4 away',cross[cross.sign.eq(-1)&~cross.neutral_site]),('neutral',cross[cross.neutral_site])]:
            info['by_venue'][name] = {'games':len(subset),'p4_wins':int(subset.p4_won.sum())}
        result['seasons'][year] = info
        d.to_csv(ROOT/f'backtests/conference_predictions_{year}.csv',index=False)
    (ROOT/'backtests/conference_results.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    main()
