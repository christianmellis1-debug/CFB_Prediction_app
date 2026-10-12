import unittest
from unittest.mock import patch
import pandas as pd

from matchup_advantages import select_waterfall, WATERFALL_TIERS
from home_field_advantage_tier6 import build_tier6_checks, group


def fixture(week=3, home_ml=-350, away_ml=250, group_name="ACC"):
    game=dict(
        season=2026, week=week, game_id=12345, home_id=10, away_id=20,
        home_team="Home", away_team="Away", home_conference=group_name,
        away_conference=group_name, home_division="fbs", away_division="fbs",
        neutral_site=False, season_type="regular", completed=False,
        start_date="2026-09-19T17:00:00Z", home_points=None, away_points=None)
    pred={"Game ID":12345,"DK Home ML":home_ml,"DK Away ML":away_ml,
          "Home Spread":"-6.5","Away Spread":"+6.5",
          "Home Spread Odds":"-110","Away Spread Odds":"-110"}
    return game,pred


def select(game,pred,checks=None,tier5=None,advantage=None,weather=None):
    status={"status":"ok","qualifies":True,"off_edge":.81,
            "def_edge":.92,"magnitude":.81}
    return select_waterfall(
        pd.DataFrame([pred]),pd.DataFrame([game]),{},
        advantage_checks=advantage or {},
        weather_checks=weather or {},
        tier5_checks=tier5 or {},
        tier6_checks=checks if checks is not None else {"12345":status})


class HomeFieldAdvantageTier6Tests(unittest.TestCase):
    def test_official_display_name(self):
        self.assertEqual(WATERFALL_TIERS[6],"Tier 6: Home Field Advantage")

    def test_price_boundary_and_no_minus10_spread_requirement(self):
        for price,should_qualify in [(-100,True),(-350,True),(-499,True),
                                     (-500,False),(-600,False),(-1000,False),
                                     ("Unavailable",False),("+150",False)]:
            with self.subTest(price=price):
                g,p=fixture(home_ml=price)
                card=select(g,p)
                self.assertEqual(bool(card),should_qualify)
                if card:
                    self.assertEqual(card[0]["Value Tier"],"Tier 6: Home Field Advantage")
                    self.assertEqual(card[0]["Value Market"],"Moneyline")
                    self.assertEqual(card[0]["Value Pick"],"Home")
                    self.assertEqual(card[0]["Value Price"],str(price) if isinstance(price,str) else f"{price:+d}")
                    self.assertEqual(card[0]["Value Stage"],6)

    def test_missing_data_or_away_favorite_cannot_qualify(self):
        cases=[
          dict(checks={"12345":{"status":"missing","qualifies":False}}),
          dict(checks={"12345":{"status":"ok","qualifies":False,"magnitude":.6}}),
        ]
        for override in cases:
            g,p=fixture()
            self.assertEqual(select(g,p,**override),[])
        for home_ml,away_ml in [(-350,-450),(-350,None),(+200,-300),
                                (-350,0),(-350,"Unavailable")]:
            with self.subTest(home_ml=home_ml,away_ml=away_ml):
                g,p=fixture(home_ml=home_ml,away_ml=away_ml)
                self.assertEqual(select(g,p),[])
        g,p=fixture()
        g["neutral_site"]=True
        self.assertEqual(select(g,p),[])
        g["neutral_site"]=None
        self.assertEqual(select(g,p),[])

    def test_existing_tiers_take_precedence(self):
        g,p=fixture()
        tier5={"12345":{"status":"ok","qualifies":True,"through_week":2}}
        self.assertEqual(select(g,p,tier5=tier5)[0]["Value Stage"],5)
        checks={"12345":{"status":"ok","home":[6,.7,3,.55,1],
                          "away":[4,.6,5,.65,0],"group":"P4"}}
        self.assertEqual(select(g,p,advantage=checks)[0]["Value Stage"],1)

    def test_existing_price_tier_stays_unchanged(self):
        g,p=fixture(week=4,home_ml=-600,away_ml=450)
        self.assertEqual(select(g,p)[0]["Value Stage"],4)

    def test_pac12_classification_is_season_aware(self):
        self.assertEqual(group("Pac-12","Washington State",2023),"P4")
        self.assertIsNone(group("Pac-12","Washington State",2024))
        self.assertEqual(group("Pac-12","Washington State",2026),"G6")
        self.assertEqual(group("Independent","Notre Dame",2026),"P4")
        self.assertIsNone(group("Independent","Army",2026))

    def test_fail_closed_without_complete_pregame_inputs(self):
        g,p=fixture()
        empty=pd.DataFrame()
        self.assertEqual(build_tier6_checks(pd.DataFrame([g]),empty,empty,empty,3),
                         {"12345":{"status":"missing","qualifies":False,
                                   "group":"P4",
                                   "reason":"Earlier-week advanced/box-score data missing."}})

    def test_no_model_probability_or_winner_change(self):
        g,p=fixture()
        p.update({"Predicted Winner":"Away","Home Win %":.27})
        c=select(g,p)
        self.assertEqual(c[0]["Value Pick"],"Home")
        self.assertEqual(p["Predicted Winner"],"Away")
        self.assertEqual(p["Home Win %"],.27)


if __name__=="__main__":
    unittest.main()
