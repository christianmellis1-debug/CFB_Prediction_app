"""Flat-stake, market-aware accounting for the official Value Shortlist.

Presentation/analysis only. Does not select picks, change model probabilities,
infer missing odds, or substitute core-model results for a recommended-bet grade.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import math
import pandas as pd


_MONEY = Decimal("0.01")
_COLS = [
    "Week", "Tier", "Stage", "Matchup", "Recommended Bet", "Market",
    "Price", "Sportsbook", "Result", "ROI Status", "Stake", "Returned",
    "Net Profit",
]


def american_price(value):
    """Validate a genuine American odds price, not a spread or model chance."""
    if value is None or isinstance(value, bool):
        return None
    raw = str(value).strip().replace("−", "-").upper()
    if raw in ("EVEN", "EV", "EVS"):
        return 100
    try:
        n = Decimal(raw)
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not n.is_finite() or n != n.to_integral_value() or abs(n) < 100:
        return None
    return int(n)


def _money(number):
    return number.quantize(_MONEY, rounding=ROUND_HALF_UP)


def _stake(value):
    try:
        amount = Decimal(str(value))
    except (TypeError, InvalidOperation, ValueError):
        raise ValueError("Stake must be a positive dollar amount") from None
    if not amount.is_finite() or amount <= 0 or amount > Decimal("100000"):
        raise ValueError("Stake must be between $0.01 and $100,000")
    if _money(amount) != amount:
        raise ValueError("Stake may contain at most two decimal places")
    return amount


def value_roi_detail(frame, stake=100, weeks=None):
    """Build per-selection dollar results; missing prices and pending are excluded.

    Win: net = stake * (+odds / 100) or stake * (100 / |negative odds|).
    Loss: net = -stake. Push: stake refunded, net zero. Profit rounded per bet.
    ROI denominator includes all settled wagered stakes, including refunded pushes.
    """
    amount = _stake(stake)
    if frame is None or frame.empty or "Value Selected" not in frame:
        return pd.DataFrame(columns=_COLS)
    selected = frame.loc[frame["Value Selected"].fillna(False).astype(bool)].copy()
    selected["Week"] = pd.to_numeric(selected.get("Week"), errors="coerce")
    selected = selected[selected["Week"].ge(3)]
    if weeks is not None:
        selected = selected[selected["Week"].isin([int(w) for w in weeks])]
    records = []
    for _, row in selected.iterrows():
        price = american_price(row.get("Value Price"))
        market = str(row.get("Value Market", "")).strip()
        line = str(row.get("Value Line", "Unavailable")).strip()
        pick = str(row.get("Value Pick", "")).strip()
        result = str(row.get("Value Result", "Pending")).strip()
        status = str(row.get("Status", "Awaiting final")).strip()
        sportsbook = str(row.get("Value Source", "Unavailable")).strip()
        bet = (f"{pick} {line} ATS" if market == "Spread" else
               f"{pick} ML {line}" if market == "Moneyline" else
               f"{pick} · market unavailable")
        market_valid = market in ("Spread", "Moneyline")
        # For a spread, verify that Value Line represents the selected point spread.
        if market == "Spread":
            try:
                spread = float(line.replace("−", "-"))
                market_valid = math.isfinite(spread)
            except (ValueError, TypeError):
                market_valid = False
        # For moneylines, the displayed bet line and payout price must match.
        if market == "Moneyline":
            market_valid = american_price(line) == price and price is not None
        if status != "Final":
            label = "Pending final"
        elif result not in ("Correct", "Incorrect", "Push"):
            label = "Not graded"
        elif not market_valid:
            label = "Invalid bet line"
        elif price is None:
            label = "Missing price"
        elif not sportsbook or sportsbook.casefold() in ("unavailable", "published weekly metrics", "none", "nan"):
            label = "Missing sportsbook"
        else:
            label = "Settled"
        wagered = returned = net = None
        if label == "Settled":
            wagered = amount
            if result == "Correct":
                multiplier = (Decimal(price) / 100 if price > 0 else
                              Decimal(100) / abs(Decimal(price)))
                net = _money(amount * multiplier)
                returned = amount + net
            elif result == "Incorrect":
                net = -amount
                returned = Decimal("0")
            else:  # Push refunds stake and has no net P/L.
                net = Decimal("0")
                returned = amount
        stage = pd.to_numeric(row.get("Value Stage"), errors="coerce")
        records.append({
            "Week": int(row["Week"]), "Tier": str(row.get("Value Tier", "")),
            "Stage": int(stage) if pd.notna(stage) else 0,
            "Matchup": f'{row.get("Away Team", "")} at {row.get("Home Team", "")}',
            "Recommended Bet": bet, "Market": market,
            "Price": f"{price:+d}" if price is not None else "Unavailable",
            "Sportsbook": sportsbook, "Result": result,
            "ROI Status": label,
            "Stake": float(wagered) if wagered is not None else 0.0,
            "Returned": float(returned) if returned is not None else 0.0,
            "Net Profit": float(net) if net is not None else 0.0,
        })
    return pd.DataFrame.from_records(records, columns=_COLS)


def roi_summary(detail, group=None):
    """One row per week/tier, including excluded picks and incomplete coverage."""
    columns = ["Selections", "Settled", "Wins", "Losses", "Pushes",
               "Missing / ungraded", "Wagered", "Returned", "Net Profit", "ROI"]
    if group:
        columns = [group] + columns
    if detail is None or detail.empty:
        return pd.DataFrame(columns=columns)
    groups = detail.groupby(group, sort=True, dropna=False) if group else [(None, detail)]
    rows = []
    for key, subset in groups:
        settled = subset[subset["ROI Status"].eq("Settled")]
        wagered = round(float(settled["Stake"].sum()), 2)
        profit = round(float(settled["Net Profit"].sum()), 2)
        row = {
            "Selections": len(subset), "Settled": len(settled),
            "Wins": int(settled["Result"].eq("Correct").sum()),
            "Losses": int(settled["Result"].eq("Incorrect").sum()),
            "Pushes": int(settled["Result"].eq("Push").sum()),
            "Missing / ungraded": len(subset) - len(settled),
            "Wagered": wagered,
            "Returned": round(float(settled["Returned"].sum()), 2),
            "Net Profit": profit,
            "ROI": profit / wagered if wagered else None,
        }
        if group:
            row[group] = key
        rows.append(row)
    return pd.DataFrame.from_records(rows, columns=columns)
