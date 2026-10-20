"""Regression checks for the G6 Confidence Conflict risk overlay.

Do not mix market blended probabilities into the independent risk gate.
"""
import unittest

import pandas as pd

from confidence_conflict import (
    apply_g6_conflict_flags, omit_risky_value_recommendations,
    paired_market_probability, conference_tier,
)


class TestG6ConfidenceConflict(unittest.TestCase):
    NOW = "2026-10-20T12:00:00Z"
    KICK = "2026-10-24T20:00:00Z"

    def game(self, **overrides):
        data = dict(game_id=42, season=2026, start_date=self.KICK,
                    home_team="Delaware", away_team="Missouri State",
                    home_conference="Conference USA",
                    away_conference="Conference USA",
                    home_id=11, away_id=12,
                    home_division="fbs", away_division="fbs")
        data.update(overrides)
        return pd.DataFrame([data])

    def prediction(self, **overrides):
        data = dict(**{"Game ID":42, "Home Team":"Delaware",
                       "Away Team":"Missouri State", "Predicted Side":"Home",
                       "Predicted Winner":"Delaware", "Confidence":.77,
                       "Home ML":"+110", "Away ML":"-130",
                       "ML Source":"DraftKings", "Status":"Awaiting final",
                       "Value Selected":True, "Value Market":"Moneyline",
                       "Value Rank":1, "Game of Week":True,
                       "Bet Signal":"Value"})
        data.update(overrides)
        return pd.DataFrame([data])

    def flagged(self, games=None, picks=None, **kw):
        return apply_g6_conflict_flags(
            self.prediction() if picks is None else picks,
            self.game() if games is None else games,
            now_utc=self.NOW, **kw).iloc[0]

    def test_no_vig_pair_and_overround(self):
        p = paired_market_probability("+110", "-130", "home")
        self.assertAlmostEqual(p, .456, places=2)
        self.assertIsNone(paired_market_probability("+130", None, "home"))
        self.assertIsNone(paired_market_probability("-5000", "-5000", "home"))
        self.assertIsNone(paired_market_probability("+110", "-130", "unknown"))

    def test_valid_g6_warning_uses_original_probability(self):
        result = self.flagged()
        self.assertTrue(result["G6 Confidence Conflict"])
        self.assertAlmostEqual(result["Conflict V1.5 %"], .77)
        self.assertLess(result["Conflict Market %"], .55)
        self.assertEqual(result["Conflict Team"], "Delaware")
        self.assertEqual(result["Predicted Winner"], "Delaware")
        self.assertTrue(result["Value Selected"])

    def test_near_miss_is_not_flagged(self):
        # Week 8 Missouri State at Delaware: frozen book ~56.3%, not below 55.
        p = self.prediction(**{"Home ML":"-142", "Away ML":"+118"})
        self.assertFalse(self.flagged(picks=p)["G6 Confidence Conflict"])

    def test_only_g6_vs_g6(self):
        p4 = self.game(home_conference="Big Ten")
        self.assertFalse(self.flagged(games=p4)["G6 Confidence Conflict"])
        ind = self.game(home_conference="FBS Independents")
        self.assertFalse(self.flagged(games=ind)["G6 Confidence Conflict"])
        fcs = self.game(away_division="fcs")
        self.assertFalse(self.flagged(games=fcs)["G6 Confidence Conflict"])
        self.assertEqual(conference_tier("Pac-12", "Washington State", 2024), None)
        self.assertEqual(conference_tier("Pac-12", "Washington State", 2026), "G6")
        self.assertEqual(conference_tier("FBS Independents", "Notre Dame", 2026), "P4")

    def test_fail_closed_on_stale_or_bad_lines(self):
        self.assertFalse(self.flagged(stale=True)["G6 Confidence Conflict"])
        self.assertFalse(self.flagged(stale_event_ids={"42":"refresh failed"})["G6 Confidence Conflict"])
        p = self.prediction(**{"Away ML":"Unavailable"})
        self.assertFalse(self.flagged(picks=p)["G6 Confidence Conflict"])
        self.assertFalse(self.flagged(games=pd.concat([self.game(), self.game()]))["G6 Confidence Conflict"])

    def test_market_blend_cannot_cause_own_warning(self):
        # Independent model is below the confidence threshold, even if the
        # sportsbook-blended display subsequently shows high confidence.
        p = self.prediction(Confidence=.69)
        self.assertFalse(self.flagged(picks=p)["G6 Confidence Conflict"])

    def test_started_requires_original_frozen_pregame(self):
        started = self.prediction(Status="Final")
        self.assertFalse(self.flagged(picks=started)["G6 Confidence Conflict"])
        frozen = {
            "42": dict(home="Delaware", away="Missouri State", home_id="11",
                       away_id="12", picked_side="home", model_probability=.77,
                       provider="DraftKings", home_ml=110, away_ml=-130,
                       captured_at="2026-10-23T12:00:00Z", kickoff=self.KICK)
        }
        r = apply_g6_conflict_flags(
            started, self.game(), now_utc="2026-10-25T12:00:00Z",
            frozen_snapshots=frozen).iloc[0]
        self.assertTrue(r["G6 Confidence Conflict"])
        bad = {"42":dict(frozen["42"], captured_at="2026-10-25T12:00:00Z")}
        self.assertFalse(apply_g6_conflict_flags(
            started, self.game(), now_utc="2026-10-25T12:00:00Z",
            frozen_snapshots=bad).iloc[0]["G6 Confidence Conflict"])

    def test_suppress_future_value_but_not_historical_or_model(self):
        flagged = apply_g6_conflict_flags(self.prediction(), self.game(), now_utc=self.NOW)
        omitted = omit_risky_value_recommendations(flagged).iloc[0]
        self.assertFalse(omitted["Value Selected"])
        self.assertFalse(omitted["Game of Week"])
        self.assertEqual(omitted["Value Rank"], 0)
        self.assertEqual(omitted["Predicted Winner"], "Delaware")
        self.assertEqual(omitted["Bet Signal"], "Pass · high-risk G6 conflict")

        # This is a whole-matchup risk rule, not merely a moneyline flag.
        spread = self.prediction(**{"Value Market":"Spread"})
        spread = apply_g6_conflict_flags(spread, self.game(), now_utc=self.NOW)
        self.assertFalse(omit_risky_value_recommendations(spread).iloc[0]["Value Selected"])

        archived = flagged.copy()
        archived["Status"] = "Final"
        self.assertTrue(omit_risky_value_recommendations(archived).iloc[0]["Value Selected"])


if __name__ == "__main__":
    unittest.main()
