"""Regression coverage for the new expandable forecast transparency panel."""
import unittest

from forecast_comparison import forecast_comparison_html, _display_time


class ForecastComparisonTests(unittest.TestCase):
    def setUp(self):
        self.row = {
            "Home Team": "Marshall",
            "Away Team": "South Alabama",
            "V1.5 Home Win %": 0.534555285,
            "Home Win %": 0.4675,
            "Market Blend Used": True,
            "Blend Odds Provider": "DraftKings",
            "Blend Odds Timestamp": "2026-10-20T18:00:00+00:00",
            "Prediction Source": "Test C · current pregame",
        }

    def test_disagreement_shows_both_teams_and_data_source(self):
        result = forecast_comparison_html(self.row)
        self.assertIn("Compare win chances", result)
        self.assertIn("Independent analysis", result)
        self.assertIn("With sportsbook odds", result)
        self.assertIn("Marshall 53.5%", result)
        self.assertIn("South Alabama 53.2%", result)
        self.assertIn("Forecasts disagree on the winner", result)
        self.assertIn("DraftKings", result)
        self.assertIn("Oct 20, 2026", result)
        self.assertIn("CDT", result)

    def test_fallback_does_not_label_independent_as_market_adjusted(self):
        no_price = dict(self.row, **{
            "Market Blend Used": False,
            "Home Win %": .93,
            "Blend Odds Provider": "Unavailable",
            "Blend Odds Timestamp": "Unavailable",
        })
        result = forecast_comparison_html(no_price)
        self.assertIn("Marshall 53.5%", result)
        self.assertNotIn("Marshall 93.0%", result)
        self.assertIn("Not available", result)
        self.assertIn("Sportsbook adjustment not applied", result)
        self.assertNotIn("Forecasts disagree", result)

    def test_frozen_pregame_stamp_distinct_from_live_odds(self):
        old = dict(self.row, **{
            "Prediction Source": "Test C · frozen pregame",
            "Blend Odds Timestamp": "2026-10-18T17:24:52+00:00",
        })
        result = forecast_comparison_html(old)
        self.assertIn("Saved pregame odds", result)
        self.assertIn("Oct 18, 2026", result)
        self.assertNotIn("Odds feed retrieved", result)

    def test_missing_timestamp_and_bad_provider_do_not_make_up_values(self):
        old = dict(self.row, **{
            "Blend Odds Timestamp": "Unavailable",
            "Blend Odds Provider": None,
        })
        result = forecast_comparison_html(old)
        self.assertIn("time unavailable", result)
        self.assertIn("Sportsbook", result)
        self.assertNotIn("Oct 20, 2026", result)

    def test_unsafe_team_names_and_provider_are_escaped(self):
        old = dict(self.row, **{
            "Home Team": "<script>alert(1)</script>",
            "Blend Odds Provider": "<img src=x>",
        })
        result = forecast_comparison_html(old)
        self.assertNotIn("<script>", result)
        self.assertNotIn("<img src=x>", result)
        self.assertIn("&lt;script&gt;", result)
        self.assertIn("&lt;img src=x&gt;", result)

    def test_offset_required_and_timezone_converted(self):
        self.assertIsNone(_display_time("2026-10-20T18:00:00"))
        self.assertIsNone(_display_time("Unavailable"))
        self.assertIsNone(_display_time(None))
        self.assertEqual(
            _display_time("2026-10-20T18:00:00Z"),
            "Oct 20, 2026 · 01:00 PM CDT",
        )

    def test_missing_probability_keeps_unavailable_presentation(self):
        old = dict(self.row, **{
            "Market Blend Used": True,
            "Home Win %": float("nan"),
            "V1.5 Home Win %": float("nan"),
        })
        result = forecast_comparison_html(old)
        self.assertEqual(result.count("Not available"), 2)
        self.assertIn("Sportsbook adjustment not applied", result)


if __name__ == "__main__":
    unittest.main()
