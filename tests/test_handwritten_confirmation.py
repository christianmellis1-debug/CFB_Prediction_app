"""Paired confirmation and disagreement tests on synthetic known outcomes."""
import unittest
import pandas as pd
from research.handwritten_offense_defense_2026_10_12.confirmation_vs_v15 import analyze


class HandwrittenConfirmTests(unittest.TestCase):
    def test_disagree_flip_new_wins_and_losses(self):
        df=pd.DataFrame([
            # both signal opposes V1.5 and wins
            {"home_win":1,"baseline_probability":.40,
             "proposed_offense_edge":.3,"proposed_defense_edge":.5,
             "original_offense_edge":.2,"original_defense_edge":-.4},
            # both signal opposes V1.5 and loses
            {"home_win":0,"baseline_probability":.40,
             "proposed_offense_edge":.3,"proposed_defense_edge":.5,
             "original_offense_edge":-.2,"original_defense_edge":-.4},
            # both confirm V1.5 and win
            {"home_win":1,"baseline_probability":.90,
             "proposed_offense_edge":.8,"proposed_defense_edge":.3,
             "original_offense_edge":.2,"original_defense_edge":.4},
            # split unit advantages means no flip
            {"home_win":0,"baseline_probability":.40,
             "proposed_offense_edge":.3,"proposed_defense_edge":-.5,
             "original_offense_edge":.3,"original_defense_edge":-.4},
        ])
        result=analyze(df)
        self.assertEqual(result["cohort_games"],4)
        self.assertEqual(result["both_available"]["games"],3)
        self.assertEqual(result["both_v15_agree"]["games"],1)
        self.assertEqual(result["both_v15_disagree"]["v15"]["games"],2)
        self.assertEqual(result["new_wins_over_baseline"],1)
        self.assertEqual(result["new_losses_over_baseline"],1)
        self.assertEqual(result["net_winners_changed"],0)
        self.assertEqual(result["rule_flip_all"]["wins"],result["baseline_all"]["wins"])
        self.assertEqual(result["v15_abstain_if_both_disagrees"]["bettable_games"],2)
        self.assertEqual(result["split_available"]["baseline"]["games"],1)
        self.assertEqual(result["by_baseline_confidence"]["80pct_plus"]["both_conflicts_v15"]["v15"]["games"],0)

    def test_equal_edge_not_both(self):
        df=pd.DataFrame([
            {"home_win":1,"baseline_probability":.51,
             "proposed_offense_edge":0.0,"proposed_defense_edge":.4,
             "original_offense_edge":.5,"original_defense_edge":.3}
        ])
        result=analyze(df)
        self.assertEqual(result["both_available"]["games"],0)
        self.assertEqual(result["no_both_advantage_games"],1)
        self.assertEqual(result["ties_or_missing_edge_games"],1)

    def test_rejects_invalid_probability(self):
        df=pd.DataFrame([
            {"home_win":0,"baseline_probability":float("nan"),
             "proposed_offense_edge":.5,"proposed_defense_edge":.4}
        ])
        with self.assertRaises(ValueError):
            analyze(df)


if __name__=="__main__":
    unittest.main()
