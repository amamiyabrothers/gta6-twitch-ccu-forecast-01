#!/usr/bin/env python3
"""Forecast GTA VI launch-day Twitch viewers, hours 2-24.

Idea, in one paragraph: big launches do not all grow the same way. A
launch that opens huge in hour 1 usually stays flat, while a launch that
opens small often explodes later in the day as more time zones wake up.
So for every forecast hour we regress the log growth ratio
log(viewers_h / viewers_1) on log(viewers_1) across comparable past
launches, and read the target's forecast off that line from its own
hour-1 print. The spread around the line comes from leave-one-out
residuals of the same regression, so hours where past launches disagreed
get wide bands and hours where they agreed get narrow ones.

Only past launches the house notes call comparable are used, and only
when they opened with at least 10,000 viewers and have a full 24-hour
release day on record. The target's own category history is not a launch
and is never in the pool. Standard library only, no network, no clock,
no randomness: the same input always produces the same bytes.
"""

import json
import math
import os
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

LEVELS = (0.05, 0.25, 0.5, 0.75, 0.95)
# Standard-normal quantiles for the fallback persistence forecast.
Z_SCORES = (-1.6448536269514722, -0.6744897501960817, 0.0,
            0.6744897501960817, 1.6448536269514722)
SPREAD_SCALE = 0.75
MIN_POOL = 5
MIN_FIRST_HOUR = 10_000.0
MAX_VIEWERS = 1_000_000_000.0
HOURS = range(2, 25)


def parse_time(text):
    """Parse an ISO-8601 timestamp, tolerating a trailing Z."""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def release_day_curve(comp):
    """Return the 24 hourly viewer counts of a launch's release day.

    Returns None unless every hour 1..24 of the release day (starting at
    the comparable's day_start) has a positive viewer count.
    """
    start = parse_time(comp["day_start"])
    by_hour = {}
    for row in comp.get("hourly") or []:
        try:
            when = parse_time(row["from"])
            viewers = float(row["viewers"])
        except (KeyError, TypeError, ValueError):
            continue
        if viewers > 0:
            by_hour[when] = viewers
    curve = []
    for offset in range(24):
        value = by_hour.get(start + timedelta(hours=offset))
        if value is None:
            return None
        curve.append(value)
    return curve


def tier_of(comp):
    """Read the house research tier out of a comparable's unlock note."""
    note = comp.get("unlock") or ""
    marker = "Tier:"
    if marker not in note:
        return ""
    rest = note.split(marker, 1)[1].strip()
    return rest.split(".", 1)[0].strip().lower()


def is_console_only(comp):
    """True when the launch shipped on consoles with no PC version."""
    platforms = comp.get("platforms") or ""
    return "PC" not in platforms


def collect_pool(case):
    """Pick the regression pool, relaxing filters only if it is too small.

    Stages, in order: (1) tier-comparable launches with a big enough
    hour-1 print and a complete release day; (2) same but any tier other
    than the target's own history; (3) same but no hour-1 floor; (4) any
    launch with a complete release day. The first stage with at least
    MIN_POOL launches wins. Returns (pool, console_cap) where pool is a
    list of (log hour-1, 24-count curve) and console_cap is the largest
    hour-1 print among console-only comparable launches, or None.
    """
    entries = []
    for comp in case.get("comparables") or []:
        curve = release_day_curve(comp)
        if curve is None:
            continue
        entries.append({
            "tier": tier_of(comp),
            "console_only": is_console_only(comp),
            "curve": curve,
        })

    def stage(want_tier, want_floor):
        picked = []
        for entry in entries:
            if want_tier and entry["tier"] != "comparable":
                continue
            if entry["tier"] == "target-history":
                continue
            if want_floor and entry["curve"][0] < MIN_FIRST_HOUR:
                continue
            picked.append(entry)
        return picked

    pool = stage(True, True)
    if len(pool) < MIN_POOL:
        pool = stage(False, True)
    if len(pool) < MIN_POOL:
        pool = stage(False, False)
    if len(pool) < MIN_POOL:
        # Last resort: every launch with a complete release day, even the
        # target's own category history. (The stage above already drops
        # the tier and floor filters, so repeating it would change
        # nothing; this stage is the one that also drops the
        # target-history exclusion.)
        pool = list(entries)
    if len(pool) < 2:
        return [], None

    console_cap = None
    for entry in entries:
        if entry["tier"] == "comparable" and entry["console_only"]:
            first = entry["curve"][0]
            if console_cap is None or first > console_cap:
                console_cap = first
    points = [(math.log(e["curve"][0]), e["curve"]) for e in pool]
    return points, console_cap


def fit_line(xs, ys):
    """Ordinary least squares for y = intercept + slope * x."""
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx <= 0:
        return mean_y, 0.0
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = sxy / sxx
    return mean_y - slope * mean_x, slope


def quantile(sorted_values, tau):
    """Linear-interpolation empirical quantile (type-7 style)."""
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    pos = tau * (n - 1)
    low = int(math.floor(pos))
    high = min(low + 1, n - 1)
    frac = pos - low
    return sorted_values[low] * (1.0 - frac) + sorted_values[high] * frac


def loo_spread(xs, ys):
    """Leave-one-out residuals of the log-ratio regression.

    Each launch is predicted by a line fitted without it; the residual is
    how far its real growth sat from that prediction. These residuals,
    not a normal assumption, set the forecast bands.
    """
    residuals = []
    for i in range(len(xs)):
        rest_x = xs[:i] + xs[i + 1:]
        rest_y = ys[:i] + ys[i + 1:]
        intercept, slope = fit_line(rest_x, rest_y)
        residuals.append(ys[i] - (intercept + slope * xs[i]))
    residuals.sort()
    return [quantile(residuals, tau) for tau in LEVELS]


def round_half_up(value):
    """Round to 2 decimals, halves away from zero, as a float."""
    rounded = Decimal(repr(value)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(rounded)


def clean_quantiles(raw):
    """Force the output contract: finite, > 0, <= 1e9, non-decreasing."""
    out = []
    previous = 0.01
    for value in raw:
        if not math.isfinite(value) or value <= 0:
            value = previous
        value = round_half_up(value)
        value = max(value, previous)
        value = min(value, MAX_VIEWERS)
        out.append(value)
        previous = value
    return out


def persistence_rows(first_hour):
    """House-style fallback: flat median, spread widening over the day."""
    rows = []
    for hour in HOURS:
        width = 0.15 * math.sqrt(hour - 1)
        raw = [first_hour * math.exp(z * width) for z in Z_SCORES]
        rows.append({"hour": hour, "q": clean_quantiles(raw)})
    return rows


def forecast_case(case):
    """Forecast hours 2..24 for one case dict. Returns the output dict."""
    known = case.get("known") or []
    first_hour = 1.0
    if known:
        try:
            first_hour = float(known[0]["viewers"])
        except (KeyError, TypeError, ValueError):
            first_hour = 1.0
    if not (math.isfinite(first_hour) and first_hour > 0):
        first_hour = 1.0

    pool, console_cap = collect_pool(case)
    if not pool:
        return {"hours": persistence_rows(first_hour)}

    # The fitted line is dragged down by simultaneous-global PC giants
    # with inflated hour-1 prints. GTA VI is console-only with a rolling
    # midnight unlock, so cap the target's log hour-1 at the biggest
    # console-only comparable hour-1. Training points keep their real
    # values; only the target's position on the line is clipped.
    x_target = math.log(first_hour)
    if console_cap is not None:
        x_target = min(x_target, math.log(console_cap))

    xs = [point[0] for point in pool]
    rows = []
    for hour in HOURS:
        ys = [math.log(curve[hour - 1] / curve[0])
              for _, curve in pool]
        intercept, slope = fit_line(xs, ys)
        centre = intercept + slope * x_target
        offsets = loo_spread(xs, ys)
        raw = [first_hour * math.exp(centre + SPREAD_SCALE * off)
               for off in offsets]
        rows.append({"hour": hour, "q": clean_quantiles(raw)})
    return {"hours": rows}


def main():
    input_dir = Path(os.environ.get("MAKEFUN_INPUT_DIR") or "/input")
    output_dir = Path(os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output")
    if not input_dir.is_dir():
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(input_dir.glob("*.in"), key=lambda p: p.name):
        with path.open("r", encoding="utf-8") as handle:
            case = json.load(handle)
        result = forecast_case(case)
        out_path = output_dir / (path.stem + ".out")
        with out_path.open("w", encoding="utf-8") as handle:
            json.dump(result, handle, separators=(",", ":"))


if __name__ == "__main__":
    main()
