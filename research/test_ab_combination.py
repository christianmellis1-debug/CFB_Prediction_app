"""Compare precomputed Test A and B pregame-derived signals on matching games.

This audit intentionally does NOT recompute upstream signals; input CSV files
are pinned to immutable research commits. Upstream test methods and documented
limitations apply. Selected A and B coefficients are fixed, NOT refit here.
The conditional switch was explored after inspecting 2024–2026 outcomes,
so the 2025/2026 comparisons are *not* clean prospective validation of it.

Usage:
    pip install pandas scipy numpy
    python research/test_ab_combination.py
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.special import expit, logit

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://raw.githubusercontent.com/christianmellis1-debug/CFB_Prediction_app/"
TEST_A = BASE + "01f85866c023f8fb248b4bde594922a6411d1115/research/test_a_recent_epa_game_results.csv"
TEST_B = BASE + "44e7a7cb474e9c19a1af1bfa4774309e6b46b3e6/research/test_b_venue_games.csv"
SLOPE = 1.945 * 1.10
A_WEIGHT = 0.20
B_WEIGHT = 0.20
OUTPUT = ROOT / "research/test_ab_combination_results.json"

def stats(frame, column):
    if frame.empty:
        return None
    y = frame.y.to_numpy(dtype=int)
    p = frame[column].to_numpy(dtype=float)
    old = frame.p.to_numpy(dtype=float)
    pred = p >= 0.5
    right = pred == y
    changed = pred != (old >= 0.5)
    loss = -y * np.log(np.clip(p, 1e-12, 1-1e-12)) - (1-y) * np.log(np.clip(1-p, 1e-12, 1-1e-12))
    return dict(n=len(frame), wins=int(right.sum()), losses=int((~right).sum()), accuracy=float(right.mean()),
                brier=float(np.mean((p-y)**2)), log_loss=float(loss.mean()),
                changed=int(changed.sum()), fixed=int((changed & right).sum()), broken=int((changed & ~right).sum()))

def main():
    a = pd.read_csv(TEST_A, low_memory=False)
    b = pd.read_csv(TEST_B, low_memory=False)
    assert not a.duplicated(["season", "id"]).any()
    assert not b.duplicated(["year", "id"]).any()
    # Assert that all saved A rows match a corresponding B row and that both
    # experiments used exactly the same archived or reconstructed baselines.
    aligned = b.merge(a[["season", "id", "week", "outcome", "baseline", "shift_adjusted_offense"]],
                      left_on=["year", "id"], right_on=["season", "id"], how="left",
                      validate="one_to_one", indicator=True)
    paired = aligned[aligned._merge.eq("both")]
    assert len(paired) == len(a), (len(paired), len(a))
    assert np.allclose(paired.p, paired.baseline, atol=1e-7, rtol=0)
    assert np.array_equal(paired.y, paired.outcome)
    assert np.array_equal(paired.week_x, paired.week_y)
    assert aligned.p.between(0,1,inclusive="neither").all()
    a_available = aligned.shift_adjusted_offense.notna()
    delta_a = np.where(a_available, A_WEIGHT * aligned.shift_adjusted_offense.fillna(0), 0)
    delta_b = SLOPE * B_WEIGHT * (aligned.elo_hfa4 - aligned.raw)
    z = logit(aligned.p.to_numpy(dtype=float))
    aligned["A"] = expit(z + delta_a)
    aligned["B"] = expit(z + delta_b)
    aligned["AB"] = expit(z + delta_a + delta_b)
    aligned["conditional"] = expit(z + np.where(a_available, delta_a, delta_b))
    aligned["A_available"] = a_available
    aligned["halfBplusA"] = expit(z + delta_a + delta_b / 2)
    aligned["B_half_if_A_available"] = expit(z + delta_a + np.where(a_available, delta_b / 2, delta_b))

    variants = ["p", "A", "B", "AB", "conditional", "halfBplusA", "B_half_if_A_available"]
    def compare(frame):
        return {name: stats(frame, name) for name in variants}

    result = {
        "design": "Fixed Test A recent offensive EPA and Test B opponent-adjusted venue signals. All outcomes retrospective.",
        "audits": {"rows_A":len(a), "rows_B":len(b), "matched_A_rows":len(paired),
                   "eligible_A_total":int(a_available.sum())},
        "all": compare(aligned),
        "seasons":{},
        "week_2026":{},
        "changed_2026":[]
    }
    for year in (2024,2025,2026):
        frame = aligned[aligned.year.eq(year)]
        result["seasons"][str(year)] = {
            "all":compare(frame),
            "A_eligible_n":int(frame.A_available.sum()),
            "A_eligible":compare(frame[frame.A_available]),
            "A_not_eligible":compare(frame[~frame.A_available]),
        }
    for w in (5,6):
        frame = aligned[aligned.year.eq(2026)&aligned.week_x.eq(w)]
        result["week_2026"][str(w)] = compare(frame)
    for _,row in aligned[aligned.year.eq(2026)].iterrows():
        if (row.conditional>=.5)!=(row.p>=.5):
            result["changed_2026"].append({"week":int(row.week_x),"game":row.game,
                "p_base":round(float(row.p),4),"p_conditional":round(float(row.conditional),4),
                "correct":bool((row.conditional>=.5)==row.y)})
    OUTPUT.write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps({"audit":result["audits"],
                      "selected_comparison":{y: {k: v for k,v in s["all"].items()
                            if k in ("p","A","B","AB","conditional")} for y,s in result["seasons"].items()},
                      "flips_2026":result["changed_2026"]},indent=2))

if __name__=="__main__":
    main()
