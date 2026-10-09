"""Fast, display-only HTML for the official Value Shortlist.

Uses the waterfall's selected market, line, result and reason data; never
selects picks, estimates odds, or changes the grading calculation.
"""
from html import escape
import math


def _clean(value, fallback="Unavailable"):
    if value is None:
        return fallback
    raw = str(value).strip()
    return raw if raw and raw.casefold() not in {"none", "nan", "nat", "<na>", "unavailable"} else fallback


def _american_odds(value):
    raw = _clean(value)
    if raw.upper() in {"EVEN", "EV", "EVS"}:
        return "+100"
    try:
        number = float(raw.replace("−", "-").replace("+", ""))
    except (TypeError, ValueError, OverflowError):
        return "Unavailable"
    if not math.isfinite(number) or abs(number) < 100 or not number.is_integer():
        return "Unavailable"
    return f"{int(number):+d}"


def _positive_int(value):
    try:
        number = float(value)
        return int(number) if math.isfinite(number) and number > 0 and number.is_integer() else None
    except (TypeError, ValueError, OverflowError):
        return None


def _explanation(row, stage, team):
    """Plain-English explanations of the *qualifying rules*, not imagined stats."""
    if stage == 1:
        return f"{team} leads in rushing, passing, run defense, pass defense and turnover margin, with home-field advantage."
    if stage == 2:
        weather = _clean(row.get("Value Band"), "Bad weather")
        return f"{weather}: {team} has stronger run defense and a better turnover margin at home."
    if stage == 3:
        return f"{team} is a short underdog with a turnover-margin edge of at least one per game."
    if stage == 4:
        return f"{team} qualifies as a heavy moneyline favorite. This tier is based on the odds range, not a required statistical edge."
    if stage == 5:
        return f"{team} has better red-zone offense and defense, plus stronger explosive-play measures on both sides."
    return _clean(row.get("Value Reason"), "See the tier guide for the selection rules.")


def _status_badge(row):
    result = _clean(row.get("Value Result"), "Pending")
    status = _clean(row.get("Status"), "Awaiting final")
    if result == "Correct":
        return "Won", "won"
    if result == "Incorrect":
        return "Lost", "lost"
    if result == "Push":
        return "Push", "push"
    if result == "Not graded":
        return "Not graded", "ungraded"
    if status == "In progress":
        return "Live", "live"
    if status.startswith("Final"):
        return "Grade pending", "ungraded"
    return "Upcoming", "upcoming"


def render_value_shortlist_cards(rows):
    """Return one accessible, two-column card grid from official selected rows.

    Expected input: a list of dicts, e.g. value_picks.to_dict("records").
    All user/provider-derived strings are HTML escaped before interpolation.
    """
    if not rows:
        return ""
    html = ['<div class="value-quick-grid" aria-label="Official Value Shortlist quick-view cards">']
    for row in rows:
        stage = _positive_int(row.get("Value Stage"))
        stage = stage if stage in (1, 2, 3, 4, 5) else 0
        rank = _positive_int(row.get("Value Rank"))
        rank_label = str(rank) if rank is not None else "—"
        tier = _clean(row.get("Value Tier"), f"Tier {stage}" if stage else "Value Pick")
        away = _clean(row.get("Away Team"), "Away team")
        home = _clean(row.get("Home Team"), "Home team")
        team = _clean(row.get("Value Pick"), "Unavailable")
        market = _clean(row.get("Value Market"))
        line = _clean(row.get("Value Line"))
        price = _american_odds(row.get("Value Price"))
        source = _clean(row.get("Value Source"), "Source unavailable")
        score = _clean(row.get("Final Score"), "")
        status = _clean(row.get("Status"), "Awaiting final")
        badge, badge_class = _status_badge(row)
        if market == "Spread":
            bet = f"{team} {line} ATS"
            market_name = "Point spread"
        elif market == "Moneyline":
            bet = f"{team} ML {line}"
            market_name = "Moneyline"
        else:
            bet = f"{team} · Market unavailable"
            market_name = "Unavailable"
        if price == "Unavailable":
            source = "No sportsbook price available"
        reason = _explanation(row, stage, team)
        score_html = (
            '<div class="value-quick-score">Final: ' + escape(score) + '</div>'
            if status == "Final" and score else ""
        )
        html.append(
            f'<article class="value-quick-card tier-stage-{stage}" '
            f'aria-label="Value Pick {escape(rank_label, quote=True)}: {escape(team, quote=True)}">'
            '<div class="value-quick-top">'
            f'<span class="value-quick-rank">#{escape(rank_label)}</span>'
            f'<span class="value-quick-tier">{escape(tier)}</span>'
            f'<span class="value-quick-status {badge_class}">{escape(badge)}</span>'
            '</div>'
            f'<div class="value-quick-matchup">{escape(away)} <span>at</span> {escape(home)}</div>'
            '<div class="value-quick-bet-caption">Recommended bet</div>'
            f'<div class="value-quick-bet">{escape(bet)}</div>'
            '<div class="value-quick-markets">'
            f'<span><small>Market</small><strong>{escape(market_name)}</strong></span>'
            f'<span><small>Line</small><strong>{escape(line)}</strong></span>'
            f'<span><small>Odds</small><strong>{escape(price)}</strong></span>'
            '</div>'
            f'<div class="value-quick-source">{escape(source)}</div>'
            f'<p class="value-quick-reason">{escape(reason)}</p>'
            + score_html + '</article>'
        )
    html.append('</div>')
    return "".join(html)
