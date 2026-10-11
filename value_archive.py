"""Immutable prospective archives and market-aware settlement for Saturday Forecast.

An archived decision is written once, before the scheduled kickoff. Outcome data
is held separately and can never change the original tier, pick, or quote.
"""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import math


def parse_time(raw):
    d = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("Timezone required")
    return d.astimezone(timezone.utc)


def pregame_window(payload, game, captured_at, hours=24):
    """ESPN must independently confirm the event is genuinely pregame."""
    try:
        header = payload["header"]
        if str(header["id"]) != str(int(game["game_id"])):
            return None
        competitions = header["competitions"]
        if len(competitions) != 1:
            return None
        comp = competitions[0]
        state = comp["status"]["type"]
        if state.get("state") != "pre" or state.get("completed"):
            return None
        if header.get("timeValid", comp.get("timeValid")) is not True or comp.get("dateValid") is False:
            return None
        now = parse_time(captured_at)
        feed_kickoff = parse_time(comp["date"])
        schedule_kickoff = parse_time(game["start_date"])
        earliest = min(feed_kickoff, schedule_kickoff)
        seconds = (earliest - now).total_seconds()
        if not (0 < seconds <= hours * 3600):
            return None
        sides = {c.get("homeAway"): str(c["team"]["id"]) for c in comp["competitors"]}
        if (sides.get("home") != str(int(game["home_id"])) or
                sides.get("away") != str(int(game["away_id"]))):
            return None
        return {"kickoff": feed_kickoff.isoformat(),
                "scheduled_kickoff": schedule_kickoff.isoformat()}
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def usable_quote(raw):
    try:
        val = float(str(raw).strip().replace("−", "-"))
        return int(val) if math.isfinite(val) and abs(val) >= 100 and val.is_integer() else None
    except (TypeError, ValueError):
        return None


def quote_text(raw):
    val = usable_quote(raw)
    return f"{val:+d}" if val is not None else "Unavailable"


def spread_text(raw):
    try:
        if str(raw).strip().upper() in ("PK", "PICK", "PICKEM"):
            return "+0"
        val = float(str(raw).strip().replace("−", "-"))
        return (f"{val:+g}" if math.isfinite(val) and abs(val) <= 100 else "Unavailable")
    except (TypeError, ValueError):
        return "Unavailable"


def event_quotes(payload):
    """Normalize ESPN same-provider two-sided markets, mirroring the live app."""
    comps = payload.get("header", {}).get("competitions") or []
    if len(comps) != 1:
        return {}
    comp = dict(comps[0], odds=payload.get("pickcenter", []) or comps[0].get("odds", []))
    sides = {c.get("homeAway"): str(c.get("team", {}).get("id", "")) for c in comp.get("competitors", [])}
    providers = {}
    for entry in comp.get("odds", []):
        provider = str(entry.get("provider", {}).get("name", "")).strip()
        if not provider:
            continue
        q = {"home_id": sides.get("home"), "away_id": sides.get("away")}
        for side in ("home", "away"):
            ml = entry.get("moneyline", {}).get(side, {})
            v = (ml.get("close") or {}).get("odds")
            if v is None:
                v = entry.get(side + "TeamOdds", {}).get("moneyLine")
            q[side] = quote_text(v)
            spread = entry.get("pointSpread", {}).get(side, {})
            close = spread.get("close") or {}
            line, price = close.get("line"), close.get("odds")
            if line is None and entry.get("spread") is not None:
                try:
                    home_line = float(entry["spread"])
                    line = home_line if side == "home" else -home_line
                except (ValueError, TypeError):
                    pass
            if price is None:
                price = entry.get(side + "TeamOdds", {}).get("spreadOdds")
            q[side + "_spread"] = spread_text(line)
            q[side + "_spread_odds"] = quote_text(price)
        if any(q[x] != "Unavailable" for x in ("home", "away", "home_spread", "away_spread")):
            providers[provider] = q
    return providers


def market_fields(providers, game):
    """Require matched team IDs; never invent missing sides, spreads or prices."""
    valid = {k: v for k, v in providers.items()
             if v.get("home_id") == str(int(game["home_id"]))
             and v.get("away_id") == str(int(game["away_id"]))}
    dk = next((v for k, v in valid.items() if k.lower().replace(" ", "") == "draftkings"), {})
    spreads = next(((name, q) for name, q in valid.items()
                    if q["home_spread"] != "Unavailable" and q["away_spread"] != "Unavailable"), None)
    for name, q in valid.items():
        if name.lower().replace(" ", "") == "draftkings" and q["home_spread"] != "Unavailable" and q["away_spread"] != "Unavailable":
            spreads = name, q
            break
    source, spread = spreads if spreads else ("Unavailable", {})
    return {"DK Home ML": dk.get("home", "Unavailable"),
            "DK Away ML": dk.get("away", "Unavailable"),
            "Home Spread": spread.get("home_spread", "Unavailable"),
            "Away Spread": spread.get("away_spread", "Unavailable"),
            "Home Spread Odds": spread.get("home_spread_odds", "Unavailable"),
            "Away Spread Odds": spread.get("away_spread_odds", "Unavailable"),
            "Spread Source": source}


def make_archive(game, pick, payload, captured_at, provenance):
    """Freeze what the production waterfall recommends without changing it."""
    window = pregame_window(payload, game, captured_at)
    if not window:
        raise ValueError("Game is not in verified pregame capture window")
    if str(int(pick["Game ID"])) != str(int(game["game_id"])):
        raise ValueError("Prediction ID mismatch")
    selected = bool(pick.get("Value Selected", False))
    fields = ("Value Tier", "Value Stage", "Value Pick", "Value Side", "Value Line",
              "Value Price", "Value Market", "Value Source", "Value Reason",
              "Predicted Winner", "Predicted Side", "Confidence", "Model Version")
    values = {key: _scalar(pick.get(key)) for key in fields}
    return {"event_id": str(int(game["game_id"])), "season": int(game["season"]),
            "week": int(game["week"]), "home": str(game["home_team"]),
            "away": str(game["away_team"]), "home_id": str(int(game["home_id"])),
            "away_id": str(int(game["away_id"])), "selected": selected,
            "captured_at": parse_time(captured_at).isoformat(),
            **window, **values, "provenance": provenance}


def _scalar(value):
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def settle(archive, payload, checked_at):
    """Save final independently. Missing results remain pending."""
    try:
        h = payload["header"]
        if str(h["id"]) != archive["event_id"] or len(h["competitions"]) != 1:
            return None
        c = h["competitions"][0]
        t = c["status"]["type"]
        if not t.get("completed") or t.get("name") not in ("STATUS_FINAL", "STATUS_FINAL_OVERTIME"):
            return None
        sides = {side["homeAway"]: side for side in c["competitors"]}
        for side in ("home", "away"):
            if str(sides[side]["team"]["id"]) != archive[side + "_id"]:
                return None
        hp, ap = float(sides["home"]["score"]), float(sides["away"]["score"])
        if not all(math.isfinite(x) and x >= 0 for x in (hp, ap)):
            return None
        label = grade(archive, hp, ap)
        return {"home_score": hp, "away_score": ap, "result": label,
                "checked_at": parse_time(checked_at).isoformat()}
    except (KeyError, TypeError, ValueError):
        return None


def grade(archive, hp, ap):
    if not archive.get("selected"):
        return "Not selected"
    side = str(archive.get("Value Side", "")).lower()
    if side not in ("home", "away"):
        return "Not graded"
    diff = hp - ap if side == "home" else ap - hp
    market = archive.get("Value Market")
    if market == "Spread":
        try:
            line = float(str(archive["Value Line"]).replace("−", "-"))
        except (TypeError, ValueError):
            return "Not graded"
        if not math.isfinite(line):
            return "Not graded"
        diff += line
    elif market != "Moneyline":
        return "Not graded"
    return "Win" if diff > 1e-10 else "Loss" if diff < -1e-10 else "Push"


def roi(archive, result, stake=10):
    """ROI requires actual archived price and a settled selected bet."""
    if not archive.get("selected") or result not in ("Win", "Loss", "Push"):
        return None
    price = usable_quote(archive.get("Value Price"))
    if price is None:
        return None
    if result in ("Push",):
        return 0.0
    if result == "Loss":
        return -float(stake)
    p = Decimal(str(price))
    profit = Decimal(str(stake)) * (p / 100 if p > 0 else 100 / abs(p))
    return float(profit.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
