import ast
import math
import unittest
from html import escape
from pathlib import Path

import pandas as pd

from weather_context import _summarize_window, _weather_code_label


class WeatherContextTests(unittest.TestCase):
    def test_weather_code_labels(self):
        self.assertEqual(_weather_code_label(0), "Clear")
        self.assertEqual(_weather_code_label(2), "Partly cloudy")
        self.assertEqual(_weather_code_label(63), "Rain")
        self.assertEqual(_weather_code_label(95), "Thunderstorms")

    def test_game_window_summary_flags_inclement_and_temperature(self):
        times = pd.date_range("2026-10-10T18:00:00Z", periods=5, freq="h")
        frame = pd.DataFrame({
            "time": times,
            "temperature_2m": [78, 77, 76, 75, 74],
            "apparent_temperature": [82, 81, 80, 79, 78],
            "precipitation": [0.0, 0.4, 0.7, 0.2, 0.0],
            "snowfall": [0, 0, 0, 0, 0],
            "weather_code": [2, 61, 63, 61, 2],
            "wind_speed_10m": [12, 15, 18, 19, 17],
            "wind_gusts_10m": [20, 24, 31, 28, 25],
        })
        wx = _summarize_window(frame, pd.Timestamp("2026-10-10T18:30:00Z"), "Forecast")
        self.assertTrue(wx["inclement"])
        self.assertEqual(wx["weather_type"], "Wet/snow + wind")
        self.assertEqual(wx["condition"], "Partly cloudy")
        self.assertEqual(wx["temperature_f"], 78)
        self.assertAlmostEqual(wx["precip_mm"], 1.3)
        self.assertEqual(wx["max_gust_mph"], 31)

    def test_ordinary_game_window(self):
        times = pd.date_range("2026-10-10T18:00:00Z", periods=5, freq="h")
        frame = pd.DataFrame({
            "time": times,
            "temperature_2m": [70] * 5,
            "apparent_temperature": [70] * 5,
            "precipitation": [0] * 5,
            "snowfall": [0] * 5,
            "weather_code": [0] * 5,
            "wind_speed_10m": [8] * 5,
            "wind_gusts_10m": [14] * 5,
        })
        wx = _summarize_window(frame, pd.Timestamp("2026-10-10T18:00:00Z"), "Forecast")
        self.assertFalse(wx["inclement"])
        self.assertEqual(wx["weather_type"], "Ordinary")


class WeatherCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse(Path("app.py").read_text())
        # The card uses the app's weather-icon helper; load both functions.
        funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name in ("weather_card_html", "weather_condition_icon")]
        ns = {"escape": escape, "math": math}
        exec(compile(ast.Module(body=funcs, type_ignores=[]), "app.py", "exec"), ns)
        cls.render = staticmethod(ns["weather_card_html"])

    def test_inclement_card_is_explicit(self):
        html = self.render({
            "status": "ok",
            "inclement": True,
            "condition": "Rain",
            "temperature_f": 76,
            "feels_like_f": 80,
            "precip_mm": 5.2,
            "snowfall": 0,
            "max_wind_mph": 18,
            "max_gust_mph": 34,
            "source_type": "Forecast",
            "location": "Baton Rouge, LA",
        })
        self.assertIn("Inclement-weather threshold met", html)
        self.assertIn("Rain", html)
        self.assertIn("76°F", html)
        self.assertIn("Gusts 34 mph", html)

    def test_indoor_card_is_clear(self):
        html = self.render({"status": "indoor", "venue_name": "Indoor Stadium"})
        self.assertIn("Indoor venue", html)
        self.assertIn("Indoor Stadium", html)


if __name__ == "__main__":
    unittest.main()
