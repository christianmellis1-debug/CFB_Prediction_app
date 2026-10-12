"""Safety tests for prospective internal-weight comparisons."""
import copy
import unittest
import numpy as np
import pandas as pd

from prospective_weights import CHALLENGERS, BASE, pregame_predictions, configuration
from prospective_weights_archive import (
    make_snapshot, settle, comparison, empty_archive, detail
)

WHEN = "2026-10-16T12:00:00Z"
GAME = {
    "game_id": 401856712, "season": 2026, "week": 7,
    "home_team": "Home", "away_team": "Away", "home_id": 333,
    "away_id": 61, "start_date": "2026-10-16T22:00:00Z"
}
VALUES = {name: 0.65 + 0.01*i for i, name in enumerate(CHALLENGERS)}


def event(phase="pre", complete=False, home="31", away="24"):
    return {
        "header": {
            "id": "401856712", "timeValid": True,
            "competitions": [{
                "date": "2026-10-16T22:00:00Z", "dateValid": True,
                "status": {"type": {
                    "state": phase, "completed": complete,
                    "name": "STATUS_FINAL" if complete else "STATUS_SCHEDULED"
                }},
                "competitors": [
                    {"homeAway": "home", "team": {"id": "333"}, "score": home},
                    {"homeAway": "away", "team": {"id": "61"}, "score": away},
                ]
            }]
        }
    }


class ProspectiveWeightTest(unittest.TestCase):
    def test_definitions_locked_and_normalized(self):
        self.assertEqual(list(CHALLENGERS), [
            "V1.5 current", "Offensive EPA 60%",
            "Defensive red zone 30%", "Balanced defense 25%"
        ])
        self.assertEqual(BASE, (.4, .3, .15, .15))
        for pair in CHALLENGERS.values():
            for weights in pair:
                self.assertAlmostEqual(sum(weights), 1)
        self.assertEqual(configuration()["Balanced defense 25%"]["defense"]["epa"], .25)

    def test_capture_requires_pregame_and_all_variants(self):
        snap = make_snapshot(GAME, VALUES, event(), WHEN, {"version": "pinned"})
        self.assertEqual(len(snap["models"]), 4)
        self.assertEqual(snap["models"]["V1.5 current"]["predicted_side"], "home")
        self.assertEqual(snap["captured_at"], "2026-10-16T12:00:00+00:00")
        with self.assertRaises(ValueError):
            make_snapshot(GAME, {"V1.5 current": .67}, event(), WHEN, {})
        with self.assertRaises(ValueError):
            make_snapshot(GAME, VALUES, event("in"), WHEN, {})
        with self.assertRaises(ValueError):
            make_snapshot(GAME, VALUES, event(), "2026-10-17T01:00:00Z", {})

    def test_final_is_separate_and_same_cohort(self):
        snap = make_snapshot(GAME, VALUES, event(), WHEN, {})
        frozen = copy.deepcopy(snap)
        self.assertIsNone(settle(snap, event("in"), "2026-10-17T01:00:00Z"))
        result = settle(snap, event("post", True), "2026-10-17T01:00:00Z")
        self.assertEqual(result["winner_side"], "home")
        self.assertEqual(snap, frozen)
        ledger = empty_archive()
        ledger["snapshots"][snap["event_id"]] = snap
        ledger["results"][snap["event_id"]] = result
        scores = comparison(ledger)
        self.assertEqual(list(scores["Graded"]), [1]*4)
        self.assertEqual(list(scores["Wins"]), [1]*4)
        self.assertEqual(len(detail(ledger)), 4)
        self.assertEqual(sum(comparison(ledger, week=6)["Graded"]), 0)

    def test_identity_and_ties_not_graded(self):
        snap = make_snapshot(GAME, VALUES, event(), WHEN, {})
        invalid = event("post", True)
        invalid["header"]["competitions"][0]["competitors"][0]["team"]["id"] = "9"
        self.assertIsNone(settle(snap, invalid, "2026-10-17T01:00:00Z"))
        tied = settle(snap, event("post", True, "21", "21"),
                      "2026-10-17T01:00:00Z")
        ledger = empty_archive()
        ledger["snapshots"][snap["event_id"]] = snap
        ledger["results"][snap["event_id"]] = tied
        self.assertEqual(sum(comparison(ledger)["Graded"]), 0)

    def test_no_current_or_future_week_leakage(self):
        import model_v1_5 as model
        cols = [v[0] for v in model.COMPONENT_SPEC.values()]
        def row(season, team, week, offset):
            values = {col: float(offset + j/10) for j, col in enumerate(cols)}
            return dict(season=season, team_id=team, through_week=week, **values)
        previous = pd.DataFrame([
            row(2025, 333, 14, 1), row(2025, 61, 14, 3)
        ])
        current = pd.DataFrame([
            row(2026, 333, 6, 1), row(2026, 61, 6, 3)
        ])
        future = pd.concat([current, pd.DataFrame([
            row(2026, 333, 7, 100), row(2026, 61, 7, -50),
        ])], ignore_index=True)
        game = pd.DataFrame([dict(GAME, home_division="fbs",
            away_division="fbs", season_type="regular",
            home_conference="ACC", away_conference="SEC")])
        prediction = pd.DataFrame([{"Game ID": GAME["game_id"],
                                    "Home Win %": 0.65}])
        expected = pregame_predictions(current, previous, game, 7,
                                       baseline_frame=prediction)
        observed = pregame_predictions(future, previous, game, 7,
                                       baseline_frame=prediction)
        for key in CHALLENGERS:
            self.assertAlmostEqual(expected["401856712"][key],
                                   observed["401856712"][key], places=12)
        self.assertAlmostEqual(observed["401856712"]["V1.5 current"], .65)


if __name__ == "__main__":
    unittest.main()
