"""Tier 6 Home Field Advantage regression tests."""
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
import home_field_advantage_tier6 as tier
from matchup_advantages import select_waterfall

class Tier6Waterfall(unittest.TestCase):
    @staticmethod
    def fixture(home_ml="-250", away_ml="+205", home_group="ACC", away_group="ACC", week=3, neutral=False):
        g=dict(game_id=123,season=2026,week=week,season_type="regular",
            home_id=10,away_id=20,home_team="Home",away_team="Away",
            home_conference=home_group,away_conference=away_group,
            home_division="fbs",away_division="fbs",neutral_site=neutral,
            completed=False,home_points=None,away_points=None,
            start_date="2026-09-12T14:00:00Z")
        p={"Game ID":123,"DK Home ML":home_ml,"DK Away ML":away_ml,
           "Home Spread":"-4.5","Home Spread Odds":"-110","Spread Source":"Draft Kings"}
        return g,p

    def select(self,checks,**params):
        g,p=self.fixture(**params)
        return select_waterfall(pd.DataFrame([p]),pd.DataFrame([g]),{},
            advantage_checks={},weather_checks={},tier5_checks={},
            tier6_checks={"123":checks})

    def test_name_and_inclusion(self):
        rec={"status":"ok","qualifies":True,"off_edge":.8,"def_edge":.25,"magnitude":.25}
        card=self.select(rec)
        self.assertEqual(len(card),1)
        self.assertEqual(card[0]["Value Stage"],6)
        self.assertEqual(card[0]["Value Tier"],"Tier 6: Home Field Advantage")
        self.assertEqual(card[0]["Value Market"],"Moneyline")
        self.assertEqual(card[0]["Value Pick"],"Home")
        self.assertEqual(card[0]["Value Line"],"-250")
        self.assertEqual(card[0]["Value Band"],"Straight Up")

    def test_boundary_and_missing_prices(self):
        rec={"status":"ok","qualifies":True,"off_edge":.8,"def_edge":.25,"magnitude":.25}
        for price,away,expected in [
            ("-499","+320",True),("-500","+400",False),("-501","+405",False),
            ("-100","+100",True),("-99","+110",False),("-101","+100",True),
            ("Unavailable","+200",False),("-250","Unavailable",False),
            ("+120","-140",False),("-250","-240",False),
        ]:
            with self.subTest(price=price,away=away):
                self.assertEqual(bool(self.select(rec,home_ml=price,away_ml=away)),expected)

    def test_neutral_and_missing_stats(self):
        rec={"status":"ok","qualifies":True,"off_edge":.7,"def_edge":.7,"magnitude":.7}
        self.assertFalse(self.select(rec,neutral=True))
        self.assertFalse(self.select({"status":"missing","qualifies":False}))
        self.assertFalse(self.select({"status":"ok","qualifies":False}))

    def test_not_replacing_earlier_tier(self):
        g,p=self.fixture(home_ml="-600",away_ml="+450",week=4)
        stage5={"status":"ok","qualifies":True,"through_week":3}
        stage6={"status":"ok","qualifies":True,"off_edge":.9,"def_edge":.5,"magnitude":.5}
        card=select_waterfall(pd.DataFrame([p]),pd.DataFrame([g]),{},
            advantage_checks={},weather_checks={},tier5_checks={"123":stage5},
            tier6_checks={"123":stage6})
        self.assertEqual(len(card),1)
        self.assertEqual(card[0]["Value Stage"],4)
        p["DK Home ML"]="-250"
        card=select_waterfall(pd.DataFrame([p]),pd.DataFrame([g]),{},
            advantage_checks={},weather_checks={},tier5_checks={"123":stage5},
            tier6_checks={"123":stage6})
        self.assertEqual(len(card),1)
        self.assertEqual(card[0]["Value Stage"],5)

    def test_conference_groups(self):
        self.assertEqual(tier.group("SEC","Georgia",2026),"P4")
        self.assertEqual(tier.group("Independent","Notre Dame",2026),"P4")
        self.assertEqual(tier.group("Sun Belt","Troy",2026),"G6")
        self.assertEqual(tier.group("Pac-12","Washington State",2026),"G6")
        self.assertIsNone(tier.group("Pac-12","Washington State",2025))

class Tier6Magnitude(unittest.TestCase):
    @staticmethod
    def evaluate(group="SEC",v=1.2,week=3,neutral=False):
        s=pd.DataFrame([dict(game_id=123,season=2026,week=week,
              season_type="regular",home_id=10,away_id=20,
              home_team="Home",away_team="Away",
              home_conference=group,away_conference=group,
              home_division="fbs",away_division="fbs",
              neutral_site=neutral,completed=False,
              home_points=np.nan,away_points=np.nan,
              start_date="2026-09-12T14:00:00Z")])
        features={10:np.array([v]*6),20:np.array([0]*6)}
        mock_checks=[
          patch.object(tier,"prepare_full_boxes",return_value=pd.DataFrame()),
          patch.object(tier,"standardized_team_profiles",return_value=(features,{})),
          patch.object(tier,"published_required",return_value={10,20}),
          patch.object(tier,"component_vectors",return_value=({},{})),
          patch.object(tier,"latest",return_value=(np.zeros(4),np.zeros(4))),
          patch.object(tier.model,"build_prior_profiles",return_value=lambda tid:(0.0,0.0,0.0)),
          patch.object(tier.model,"current_season_weight",return_value=1.0)
        ]
        for p in mock_checks:p.start()
        try:return tier.build_tier6_checks(s,pd.DataFrame(),pd.DataFrame(),pd.DataFrame(),week)
        finally:
            for p in reversed(mock_checks):p.stop()

    def test_p4_exclusion_and_g6_same_range(self):
        p4=self.evaluate("SEC",v=1.2)["123"]   # .50*1.2 == .60
        self.assertAlmostEqual(p4["magnitude"],.6)
        self.assertFalse(p4["qualifies"])
        g6=self.evaluate("Sun Belt",v=1.2)["123"]
        self.assertTrue(g6["qualifies"])
        for val,expected in [(0.0,False),(.99,True),(1.0,False),(1.5,True)]:
            with self.subTest(v=val):
                record=self.evaluate("SEC",v=val)["123"]
                self.assertEqual(record["qualifies"],expected)

    def test_fail_closed_without_published_boxes(self):
        s=pd.DataFrame([dict(game_id=123,season=2026,week=3,season_type="regular",
                            home_id=10,away_id=20,home_team="Home",away_team="Away",
                            home_conference="SEC",away_conference="SEC",
                            home_division="fbs",away_division="fbs",neutral_site=False,
                            completed=False,home_points=None,away_points=None,
                            start_date="2026-09-12T14:00:00Z")])
        checks=tier.build_tier6_checks(s,pd.DataFrame(),pd.DataFrame(),pd.DataFrame(),3)
        self.assertFalse(checks.get("123",{}).get("qualifies",False))

if __name__=="__main__":
    unittest.main()
