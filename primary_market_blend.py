"""Saturday Forecast primary winner forecast: frozen Test C market-informed blend.

Independent six-tier waterfall should be calculated BEFORE apply_primary_blend().
Historic matchups before the 2026-10-13 promotion never receive retrospectively
substituted picks. Completed/current games require authentic pre-kickoff captures.
"""
from datetime import datetime, timezone
import math
import pandas as pd
import numpy as np
from model_v1_5 import confidence_label, road_risk_label

MODEL_WEIGHT = 0.16927926947215113
MARKET_WEIGHT = 1.0 - MODEL_WEIGHT
START_UTC = datetime(2026, 10, 13, 18, 0, tzinfo=timezone.utc)
VERSION = "Test C · Market Blend"
FALLBACK = "V1.5 fallback"


def _utc(value):
    try:
        value = pd.to_datetime(value, errors="coerce", utc=True)
        return value.to_pydatetime() if pd.notna(value) else None
    except (ValueError, TypeError, OverflowError):
        return None


def _implied(odd):
    if odd is None or isinstance(odd, bool):
        return None
    try:
        p = float(str(odd).strip().replace("−", "-").replace("+", ""))
        if not math.isfinite(p) or abs(p) < 100 or not p.is_integer():
            return None
        return 100.0/(100.0+p) if p>0 else -p/(100.0-p)
    except (ValueError, TypeError, OverflowError):
        return None


def market_home_probability(home_price, away_price):
    """Require both valid same-book American prices and reasonable bookmaker vig."""
    hp, ap = _implied(home_price), _implied(away_price)
    if hp is None or ap is None:
        return None
    total = hp+ap
    if not 1.0 <= total <= 1.16:
        return None
    return hp/total


def _set_betting_fields(df, index, winner_side, original_home, row, book_home=None, book_away=None):
    """Betting signals remain based on *independent V1.5*, never the blend."""
    line = book_home if winner_side == "Home" else book_away
    try:
        price = float(line)
    except (TypeError, ValueError, OverflowError):
        price = float("nan")
    if not math.isfinite(price) or abs(price) < 100:
        df.at[index, "Bet Line"] = "Unavailable"
        df.at[index, "Market Implied %"] = np.nan
        df.at[index, "Model Edge"] = np.nan
        df.at[index, "Expected Value"] = np.nan
        return
    df.at[index, "Bet Line"] = f"{int(price):+d}"
    implied = _implied(price)
    independent_p = original_home if winner_side == "Home" else 1-original_home
    df.at[index, "Market Implied %"] = implied
    df.at[index, "Model Edge"] = independent_p - implied
    payoff = price/100 if price>0 else 100/abs(price)
    df.at[index, "Expected Value"] = independent_p*payoff-(1-independent_p)


def apply_primary_blend(predictions, games, *, now_utc=None, stale=False,
                        stale_event_ids=(), frozen_snapshots=None,
                        odds_retrieved_utc=None):
    """Post-tier display transform: select winners using valid pregame quotes.

    Future games may use fresh quotes. After kickoff, only a previously frozen
    kickoff-verified first observation is accepted; otherwise retain V1.5.
    The input DataFrame must already have attach_odds/add_betting_value and
    independently computed value tiers. This function never mutates its input.
    """
    if predictions.empty:
        return predictions.copy()
    now = _utc(now_utc) if now_utc is not None else datetime.now(timezone.utc)
    if now is None:
        raise ValueError("Invalid now_utc")
    # Use the timestamp from the successful (possibly cached) sportsbook feed,
    # never the time Streamlit reruns to render a page.
    odds_retrieved = _utc(odds_retrieved_utc)
    if odds_retrieved is not None and odds_retrieved > now:
        odds_retrieved = None
    df = predictions.copy(deep=True)
    for old, new in (
        ("Home Win %", "V1.5 Home Win %"),
        ("Away Win %", "V1.5 Away Win %"),
        ("Predicted Winner", "V1.5 Predicted Winner"),
        ("Predicted Side", "V1.5 Predicted Side"),
        ("Confidence", "V1.5 Confidence"),
        ("Model Version", "V1.5 Version"),
        ("Pick Explanation", "V1.5 Explanation"),
    ):
        df[new] = df[old].copy()
    df["Prediction Source"] = FALLBACK
    df["Market Blend Used"] = False
    # Only a genuine applied pregame market blend can produce a forecast split.
    df["Forecasts Disagree"] = False
    df["Blend Odds Provider"] = "Unavailable"
    df["Blend Odds Timestamp"] = "Unavailable"

    games_index = {}
    if "game_id" in games:
        for _, g in games.iterrows():
            try:
                gid = str(int(g["game_id"]))
            except (KeyError, ValueError, TypeError, OverflowError):
                continue
            games_index[gid] = g
    stale_ids = {str(x) for x in stale_event_ids}
    frozen_snapshots = frozen_snapshots or {}

    for index, row in df.iterrows():
        try:
            gid = str(int(row["Game ID"]))
        except (KeyError, ValueError, TypeError, OverflowError):
            continue
        g = games_index.get(gid)
        if g is None:
            continue
        kickoff = _utc(g.get("start_date"))
        if kickoff is None or kickoff < START_UTC:
            # Preserve historical V1.5 records; no post-hoc promotion.
            continue
        base_home = float(row["V1.5 Home Win %"])
        if not math.isfinite(base_home) or not 0 < base_home < 1:
            continue
        market = None
        provider = None
        quote_timestamp = None
        reason = None
        is_future = kickoff > now and row.get("Status") == "Awaiting final"
        if is_future:
            if stale or gid in stale_ids:
                continue
            provider = row.get("ML Source", "Unavailable")
            if not isinstance(provider, str) or provider in ("", "Unavailable"):
                continue
            book_home = row.get("Home ML")
            book_away = row.get("Away ML")
            market = market_home_probability(book_home, book_away)
            quote_timestamp = odds_retrieved.isoformat() if odds_retrieved else None
        else:
            frozen = frozen_snapshots.get(gid)
            if not frozen or str(frozen.get("home")) != str(row["Home Team"]) or str(frozen.get("away")) != str(row["Away Team"]):
                continue
            taken, saved_kick = _utc(frozen.get("captured_at")), _utc(frozen.get("kickoff"))
            if not taken or not saved_kick or taken >= min(saved_kick,kickoff) or saved_kick < START_UTC:
                continue
            try:
                frozen_home = (float(frozen["model_probability"]) if frozen["picked_side"] == "home"
                    else 1-float(frozen["model_probability"]))
            except (KeyError, ValueError, TypeError):
                continue
            if not 0 < frozen_home < 1:
                continue
            book_home, book_away = frozen.get("home_ml"), frozen.get("away_ml")
            market = market_home_probability(book_home, book_away)
            provider = frozen.get("provider")
            quote_timestamp = taken.isoformat()
            base_home = frozen_home
            # When a later model reconstruction differs from the actual saved
            # pregame forecast, show the actual saved prediction as V1.5.
            df.at[index, "V1.5 Home Win %"] = base_home
            df.at[index, "V1.5 Away Win %"] = 1-base_home
            df.at[index, "V1.5 Confidence"] = max(base_home, 1-base_home)
            df.at[index, "V1.5 Predicted Side"] = "Home" if base_home >= .5 else "Away"
            df.at[index, "V1.5 Predicted Winner"] = row["Home Team"] if base_home >= .5 else row["Away Team"]
            df.at[index, "V1.5 Explanation"] = "Original V1.5 pick from the immutable pre-kickoff shadow archive."

        if market is None or provider is None:
            continue
        home = MODEL_WEIGHT * base_home + MARKET_WEIGHT*market
        side = "Home" if home >= .5 else "Away"
        winner = row["Home Team"] if side == "Home" else row["Away Team"]
        confidence = max(home,1-home)
        opponent = row["Away Team"] if side == "Home" else row["Home Team"]
        market_favorite = row["Home Team"] if market >= .5 else row["Away Team"]
        # Keep the technical blend and prior forecast in the data columns, but
        # show supporters a plain-English game outlook instead of the formula.
        if winner != market_favorite:
            explanation = (
                f"We're picking {winner} in a possible upset over {opponent}. "
                "This looks like a close game that could go either way."
            )
        elif confidence >= .80:
            explanation = (
                f"We're picking {winner} over {opponent}. "
                f"{winner} heads into this matchup as the clear favorite."
            )
        elif confidence >= .60:
            explanation = (
                f"We're picking {winner} over {opponent}. "
                f"{winner} has the edge coming into the game, "
                f"but {opponent} could still make it competitive."
            )
        else:
            explanation = (
                f"We're leaning toward {winner} over {opponent}, "
                "but this matchup looks very close."
            )
        df.at[index, "Home Win %"] = home
        df.at[index, "Away Win %"] = 1-home
        df.at[index, "Predicted Winner"] = winner
        df.at[index, "Predicted Side"] = side
        df.at[index, "Confidence"] = confidence
        df.at[index, "Confidence Label"] = confidence_label(confidence)
        df.at[index, "Venue Risk"] = road_risk_label(side, confidence)
        df.at[index, "Model Version"] = VERSION
        df.at[index, "Pick Explanation"] = explanation
        df.at[index, "Prediction Source"] = VERSION + (" · frozen pregame" if not is_future else " · current pregame")
        df.at[index, "Market Blend Used"] = True
        df.at[index, "Forecasts Disagree"] = (base_home >= 0.5) != (home >= 0.5)
        df.at[index, "Blend Odds Provider"] = provider
        df.at[index, "Blend Odds Timestamp"] = quote_timestamp
        _set_betting_fields(df,index,side,base_home,row,book_home=book_home,book_away=book_away)
        if str(row.get("Status")) == "Final":
            actual = row.get("Actual Winner", "—")
            if actual not in ("—", "Tie", ""):
                df.at[index, "Pick Result"] = "Correct" if winner == actual else "Incorrect"
    return df
