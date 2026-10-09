"""Focused smoke tests for the presentation-only Value Shortlist cards."""
import unittest

from value_shortlist_ui import _american_odds, render_value_shortlist_cards


def sample(**updates):
    record = {
        "Value Rank": 1,
        "Value Stage": 1,
        "Value Tier": "Tier 1 · Complete Game",
        "Away Team": "Visitors",
        "Home Team": "Home Team",
        "Value Pick": "Home Team",
        "Value Market": "Spread",
        "Value Line": "-6.5",
        "Value Price": "-110",
        "Value Source": "DraftKings",
        "Value Result": "Correct",
        "Status": "Final",
        "Final Score": "Visitors 14 – Home Team 28",
    }
    record.update(updates)
    return record


class TestValueQuickView(unittest.TestCase):
    def test_correct_spread_bet_shows_ats_not_moneyline(self):
        html = render_value_shortlist_cards([sample()])
        self.assertIn("Home Team -6.5 ATS", html)
        self.assertIn("Point spread", html)
        self.assertIn("-110", html)
        self.assertIn("Won", html)
        self.assertIn("Final: Visitors 14", html)
        self.assertIn("leads in rushing, passing, run defense", html)
        self.assertNotIn("ML -6.5", html)

    def test_moneyline_and_upcoming_and_missing_prices(self):
        html = render_value_shortlist_cards([sample(
            **{"Value Stage": 5, "Value Market": "Moneyline",
               "Value Pick": "Visitors", "Value Line": "Unavailable",
               "Value Price": "Unavailable", "Value Source": "Published weekly metrics",
               "Status": "Awaiting final", "Value Result": "Pending"})])
        self.assertIn("Visitors ML Unavailable", html)
        self.assertIn("No sportsbook price available", html)
        self.assertIn("Upcoming", html)
        self.assertIn("red-zone offense and defense", html)

    def test_push_and_live_and_ungraded_are_distinct(self):
        for result, label in (("Push", "Push"), ("Not graded", "Not graded")):
            self.assertIn(label, render_value_shortlist_cards([sample(**{"Value Result": result})]))
        self.assertIn("Live", render_value_shortlist_cards([sample(**{
            "Status": "In progress", "Value Result": "Pending"})]))
        self.assertIn("Grade pending", render_value_shortlist_cards([sample(**{
            "Status": "Final · score pending", "Value Result": "Pending"})]))

    def test_tier_specific_explanations(self):
        cases = {
            2: "stronger run defense and a better turnover margin",
            3: "turnover-margin edge of at least one per game",
            4: "odds range, not a required statistical edge",
            5: "explosive-play measures",
        }
        for stage, text in cases.items():
            with self.subTest(stage=stage):
                self.assertIn(text, render_value_shortlist_cards([sample(**{
                    "Value Stage": stage, "Value Market": "Moneyline", "Value Line": "-600"})]))

    def test_escapes_provider_and_team_strings(self):
        html = render_value_shortlist_cards([sample(**{
            "Away Team": '<img src=x onerror=alert(1)>',
            "Value Pick": '<script>alert(1)</script>',
            "Value Source": 'Book & <evil>',
        })])
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img src=x", html)
        self.assertNotIn("<evil>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("Book &amp; &lt;evil&gt;", html)

    def test_validates_moneyline_price_without_making_up_odds(self):
        self.assertEqual(_american_odds(-110), "-110")
        self.assertEqual(_american_odds("+125"), "+125")
        self.assertEqual(_american_odds("EVEN"), "+100")
        self.assertEqual(_american_odds("Unavailable"), "Unavailable")
        self.assertEqual(_american_odds("0"), "Unavailable")

    def test_empty_shortlist(self):
        self.assertEqual(render_value_shortlist_cards([]), "")


if __name__ == "__main__":
    unittest.main()
