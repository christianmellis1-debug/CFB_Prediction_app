"""Regression tests for market-aware Value Shortlist ROI accounting."""
import unittest

import pandas as pd

from value_roi import american_price, value_roi_detail, roi_summary


def pick(week=3, price="-110", line="-6.5", market="Spread",
         result="Correct", status="Final", tier="Tier 1: Complete Game",
         stage=1, selected=True, sportsbook="DraftKings"):
    return dict(
        Week=week, **{"Value Selected": selected, "Value Stage": stage,
        "Value Tier": tier, "Value Price": price, "Value Line": line,
        "Value Market": market, "Value Result": result,
        "Status": status, "Value Source": sportsbook, "Value Pick": "Home",
        "Away Team": "Away", "Home Team": "Home"}
    )


class ValueROITests(unittest.TestCase):
    def test_american_price_validation(self):
        self.assertEqual(american_price(-110), -110)
        self.assertEqual(american_price("+150"), 150)
        self.assertEqual(american_price("EVEN"), 100)
        for bad in ("Unavailable", "-6.5", "90", "nan", None, float("inf")):
            self.assertIsNone(american_price(bad))

    def test_flat_stakes_by_week_with_push_and_missing_price(self):
        games = pd.DataFrame([
            pick(week=3, result="Correct", price="-110", line="-6.5"),
            pick(week=3, result="Incorrect", price="+150", line="+150", market="Moneyline"),
            pick(week=4, result="Correct", price="+150", line="+150", market="Moneyline", stage=3),
            pick(week=4, result="Push", price="-110", line="-3.0"),
            pick(week=5, result="Correct", price="-600", line="-600", market="Moneyline", stage=4),
            pick(week=5, result="Correct", price="Unavailable", line="Unavailable", market="Moneyline", stage=5),
            pick(week=5, result="Pending", price="-110", line="-6.5", status="In progress"),
            pick(week=2, result="Correct", price="-110", line="-6.5"),
            pick(week=3, result="Correct", price="-110", line="-6.5", selected=False),
        ])
        detail = value_roi_detail(games, stake=100, weeks=[3, 4, 5])
        self.assertEqual(len(detail), 7)
        byweek = roi_summary(detail, "Week").set_index("Week")
        self.assertEqual(list(byweek.index), [3, 4, 5])
        self.assertEqual(byweek.loc[3, "Wagered"], 200)
        self.assertEqual(byweek.loc[3, "Net Profit"], -9.09)
        self.assertEqual(byweek.loc[4, "Net Profit"], 150)
        self.assertEqual(byweek.loc[4, "Pushes"], 1)
        self.assertEqual(byweek.loc[5, "Net Profit"], 16.67)
        self.assertEqual(byweek.loc[5, "Missing / ungraded"], 2)
        total = roi_summary(detail).iloc[0]
        self.assertEqual(int(total["Settled"]), 5)
        self.assertEqual(total["Wagered"], 500)
        self.assertEqual(total["Net Profit"], 157.58)
        self.assertAlmostEqual(total["ROI"], 157.58 / 500)
        self.assertEqual(detail.loc[detail["Result"].eq("Push"), "Returned"].iloc[0], 100)

    def test_week_scope_and_roi_group_by_tier(self):
        frame = pd.DataFrame([
            pick(week=3, market="Moneyline", price="+200", line="+200", tier="Tier 3", stage=3),
            pick(week=4, market="Moneyline", price="-200", line="-200", tier="Tier 4", stage=4, result="Incorrect"),
            pick(week=5, market="Moneyline", price="+200", line="+200", tier="Tier 3", stage=3),
        ])
        detail = value_roi_detail(frame, stake=25, weeks=[3, 5])
        tier = roi_summary(detail, "Tier").set_index("Tier")
        self.assertEqual(tier.loc["Tier 3", "Wagered"], 50)
        self.assertEqual(tier.loc["Tier 3", "Net Profit"], 100)
        self.assertEqual(tier.loc["Tier 3", "ROI"], 2.0)
        self.assertNotIn("Tier 4", tier.index)

    def test_missing_and_bad_price_are_not_losses(self):
        frame = pd.DataFrame([
            pick(price="Unavailable", line="Unavailable", market="Moneyline", stage=5),
            pick(price="-110", line="-3.5", market="Moneyline", stage=4),
            pick(price="-110", line="-4.5", market="Spread", sportsbook="Published weekly metrics"),
            pick(price="-110", line="-3.5", market="Spread", result="Not graded"),
        ])
        detail = value_roi_detail(frame)
        total = roi_summary(detail).iloc[0]
        self.assertEqual(total["Settled"], 0)
        self.assertEqual(total["Missing / ungraded"], 4)
        self.assertEqual(total["Wagered"], 0)
        self.assertIsNone(total["ROI"])

    def test_decimal_rounding_is_per_winning_bet(self):
        games = pd.DataFrame([
            pick(market="Moneyline", price="-600", line="-600"),
            pick(market="Moneyline", price="-600", line="-600"),
        ])
        detail = value_roi_detail(games, stake="100.00")
        self.assertEqual(detail["Net Profit"].tolist(), [16.67, 16.67])
        self.assertEqual(roi_summary(detail).iloc[0]["Net Profit"], 33.34)

    def test_does_not_graduate_pending_result_to_a_loss(self):
        detail = value_roi_detail(pd.DataFrame([
            pick(result="Correct", status="In progress"),
            pick(result="Incorrect", status="Final · score pending"),
        ]))
        self.assertEqual(set(detail["ROI Status"]), {"Pending final"})
        self.assertEqual(detail["Stake"].sum(), 0)

    def test_invalid_stakes(self):
        for stake in (0, -1, float("inf"), "abc", "0.001", 100001):
            with self.subTest(stake=stake):
                with self.assertRaises(ValueError):
                    value_roi_detail(pd.DataFrame([pick()]), stake=stake)

    def test_empty_and_unselected(self):
        self.assertTrue(value_roi_detail(pd.DataFrame(), 100).empty)
        self.assertTrue(roi_summary(value_roi_detail(pd.DataFrame([pick(selected=False)]))).empty)


if __name__ == "__main__":
    unittest.main()
