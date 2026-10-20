"""Plain-English, read-only forecast comparison for Saturday Forecast card Details.

Only the validated pregame market blend is labeled sportsbook-adjusted. The
source timestamp belongs to the exact odds snapshot used for that adjustment,
not the page render time; older/unverified games fail closed.
"""
from datetime import datetime
from html import escape
import math
from zoneinfo import ZoneInfo


def _probability(value):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and 0 <= number <= 1 else None


def _display_time(value):
    """Render only genuine offset-aware ISO timestamps, in Central Time."""
    if value is None:
        return None
    try:
        stamp = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            return None
        return stamp.astimezone(ZoneInfo("America/Chicago")).strftime(
            "%b %d, %Y · %I:%M %p %Z"
        )
    except (ValueError, TypeError, OverflowError):
        return None


def _estimate_block(label, home_team, away_team, home_probability):
    if home_probability is None:
        result = '<div style="font-size:.9rem;opacity:.75">Not available</div>'
    else:
        if home_probability >= 0.5:
            winner, chance = home_team, home_probability
            other, other_chance = away_team, 1-home_probability
        else:
            winner, chance = away_team, 1-home_probability
            other, other_chance = home_team, home_probability
        result = (
            f'<div style="font-size:1.04rem;margin:5px 0 3px"><strong>'
            f'{escape(winner)} {chance:.1%}</strong></div>'
            f'<div style="font-size:.84rem;opacity:.8">'
            f'{escape(other)} {other_chance:.1%}</div>'
        )
    return (
        '<div style="flex:1 1 200px;min-width:0;padding:11px 12px;'
        'border:1px solid rgba(130,140,155,.28);border-radius:9px">'
        f'<div style="font-size:.82rem;opacity:.8">{escape(label)}</div>'
        + result + '</div>'
    )


def forecast_comparison_html(row):
    """Compact markup for existing game-card Details (and Risky Picks Details).

    Prediction rows have independent columns preserved by apply_primary_blend.
    A fallback is *not* relabeled as sportsbook-adjusted.
    """
    home = str(row.get("Home Team", "") or "")
    away = str(row.get("Away Team", "") or "")
    independent_home = _probability(row.get("V1.5 Home Win %"))
    applied = bool(row.get("Market Blend Used", False))
    combined_home = _probability(row.get("Home Win %")) if applied else None
    if combined_home is None:
        applied = False

    left = _estimate_block("Independent analysis", home, away, independent_home)
    right = _estimate_block(
        "With sportsbook odds" if applied else "Sportsbook-adjusted forecast",
        home, away, combined_home,
    )

    if applied:
        provider = str(row.get("Blend Odds Provider") or "Unavailable").strip()
        if provider.lower() in ("nan", "none", "unavailable", ""):
            provider = "Sportsbook"
        when = _display_time(row.get("Blend Odds Timestamp"))
        frozen = "frozen pregame" in str(row.get("Prediction Source", "")).lower()
        status = (
            ("Saved pregame odds" if frozen else "Odds feed retrieved")
            + f" · {escape(provider)}"
            + (f" · {escape(when)}" if when else " · time unavailable")
        )
        if independent_home is not None and (independent_home >= .5) != (combined_home >= .5):
            status += " · <strong>Forecasts disagree on the winner</strong>"
    else:
        status = (
            "Sportsbook adjustment not applied to this game. "
            "Only the independent forecast is shown; valid pregame odds "
            "may be missing, stale, unverified or outside the supported period."
        )

    return (
        '<section aria-label="Forecast comparison" style="padding:12px 13px;'
        'border:1px solid rgba(130,140,155,.3);border-radius:10px;'
        'margin:10px 0 14px">'
        '<div style="font-weight:650;margin-bottom:8px">Compare win chances</div>'
        '<div style="display:flex;flex-wrap:wrap;gap:8px">'
        + left + right + '</div>'
        '<p style="font-size:.83rem;opacity:.85;margin:10px 0 5px">'
        + status + '</p>'
        '<p style="font-size:.79rem;opacity:.7;margin:5px 0 0">'
        'Both are estimates, not betting recommendations. '
        'Official Value Picks use separate rules.</p></section>'
    )
