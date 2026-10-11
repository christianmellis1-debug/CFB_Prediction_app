"""Regression tests for prospective Value Shortlist captures and grades."""
import unittest
from value_archive import (event_quotes, market_fields, make_archive, pregame_window, grade, roi, settle)

WHEN = "2026-10-10T13:00:00+00:00"
GAME = {"game_id": 401856712, "season": 2026, "week": 6,
        "home_team": "Alabama", "away_team": "Georgia", "home_id": 333,
        "away_id": 61, "start_date": "2026-10-10T20:00:00+00:00"}
PICK = {"Game ID": 401856712, "Value Selected": True,
        "Value Tier": "Tier 2: Storm Front", "Value Stage": 2,
        "Value Pick": "Alabama", "Value Side": "Home", "Value Line": "-3.5",
        "Value Price": "-110", "Value Market": "Spread",
        "Value Source": "DraftKings", "Value Reason": "test-only",
        "Predicted Winner": "Alabama", "Predicted Side": "Home",
        "Confidence": 0.61, "Model Version": "V1.5"}


def fixture(state="pre", completed=False, score_home="24", score_away="20"):
    return {"header": {"id": "401856712", "timeValid": True, "competitions": [{
        "date": "2026-10-10T20:00:00Z",
        "timeValid": True, "dateValid": True,
        "status": {"type": {"state": state, "completed": completed,
                             "name": "STATUS_FINAL" if completed else "STATUS_SCHEDULED"}},
        "competitors": [
            {"homeAway": "home", "team": {"id": "333"}, "score": score_home},
            {"homeAway": "away", "team": {"id": "61"}, "score": score_away}]}]}}


class TestArchive(unittest.TestCase):
    def test_only_verified_pregame(self):
        self.assertIsNotNone(pregame_window(fixture(), GAME, WHEN, hours=18))
        self.assertIsNone(pregame_window(fixture("in"), GAME, WHEN, hours=18))
        self.assertIsNone(pregame_window(fixture(), GAME, "2026-10-10T21:00:00Z", hours=18))
        self.assertIsNone(pregame_window(fixture(), GAME, "2026-10-09T00:00:00Z", hours=18))
        bad = fixture()
        bad["header"]["competitions"][0]["competitors"][0]["team"]["id"] = "9"
        self.assertIsNone(pregame_window(bad, GAME, WHEN, hours=18))

    def test_side_spread_and_original_odds_locked(self):
        archive = make_archive(GAME, PICK, fixture(), WHEN, {"commit": "pre"})
        self.assertEqual(archive["Value Line"], "-3.5")
        self.assertEqual(grade(archive, 24, 20), "Win")
        self.assertEqual(grade(archive, 23, 20), "Loss")
        self.assertEqual(grade(archive, 24, 20.5), "Push")
        result = settle(archive, fixture("post", True), "2026-10-11T01:00:00Z")
        self.assertEqual(result["result"], "Win")
        self.assertEqual(roi(archive, "Win", 10), 9.09)
        self.assertEqual(roi(archive, "Loss", 10), -10)
        self.assertEqual(archive["Value Line"], "-3.5")

    def test_unpriced_not_in_roi(self):
        values = dict(PICK, **{"Value Price": "Unavailable"})
        archive = make_archive(GAME, values, fixture(), WHEN, {})
        self.assertIsNone(roi(archive, "Win"))

    def test_draftkings_identity_and_spread(self):
        p = fixture()
        p["pickcenter"] = [{"provider": {"name": "DraftKings"},
            "moneyline": {"home": {"close": {"odds": "-140"}},
                          "away": {"close": {"odds": "+120"}}},
            "pointSpread": {"home": {"close": {"line": -3.5, "odds": "-112"}},
                            "away": {"close": {"line": 3.5, "odds": "-108"}}}}]
        fields = market_fields(event_quotes(p), GAME)
        self.assertEqual(fields["DK Home ML"], "-140")
        self.assertEqual(fields["Home Spread"], "-3.5")
        self.assertEqual(fields["Home Spread Odds"], "-112")
        bad = dict(GAME, home_id=900)
        self.assertEqual(market_fields(event_quotes(p), bad)["DK Home ML"], "Unavailable")

    def test_no_postgame_captures(self):
        with self.assertRaises(ValueError):
            make_archive(GAME, PICK, fixture("post", True), WHEN, {})


if __name__ == "__main__":
    unittest.main()
