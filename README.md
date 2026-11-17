# GTA VI launch-day Twitch viewers — forecast entry

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/amamiyabrothers/gta6-twitch-ccu-forecast-01/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/amamiyabrothers/gta6-twitch-ccu-forecast-01/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

Forecasts Grand Theft Auto VI's launch-day Twitch concurrent viewers,
hours 2–24, as five quantiles each (5/25/50/75/95%), from the hour-1
print. Entry for make.fun competition `gta6-twitch-ccu-forecast-01`.

## Run

```sh
python3 main.py   # reads $MAKEFUN_INPUT_DIR (else /input), writes $MAKEFUN_OUTPUT_DIR (else /output)
```

Python 3.13 standard library only, offline, deterministic, ~0.05 s/case.

## Model

Per hour h = 2..24, an OLS regression of log(viewers_h / viewers_1) on
log(viewers_1) across a pool of past big launches, read off at the
target's own hour-1 print. The spread is the empirical quantiles of the
same regression's leave-one-out residuals, scaled × 0.75 — hours where
past launches disagreed get wide bands, hours where they agreed get
narrow ones. Quantiles are `p1 · exp(mu + spread)`, rounded half-up to
2 decimals, non-decreasing, capped at 1e9.

Pool selection (what matters most): only launches the house notes tag
"Tier: comparable", with hour-1 ≥ 10,000 viewers and a complete 24-hour
release day (18 launches in the practice kit). The target's own category
history ("Tier: target-history") is never a launch and never enters the
pool. Fallbacks relax the tier, then the hour-1 floor, then use any
complete launch; with no usable pool it falls back to the house
persistence shape. An extrapolation guard clips the target's log hour-1
at the largest hour-1 print among console-only comparable launches
(The Last of Us Part II, 365,019) — target-side only, never binding in
practice.

## Local verification (practice, 4 cases)

- Mean pinball loss **0.1693** (p00 0.2218, p01 0.1621, p02 0.1114,
  p03 0.1821); typical miss 28.4%; 90% coverage 0.859.
  House baseline scores 0.3871 on the same scorer; leaderboard best at
  build time was 0.169.
- Determinism: two full runs over all 4 practice cases byte-identical.
- Edge cases verified: empty input dir is a no-op; tiny hour-1 print and
  no comparables fall back to the persistence forecast with valid output.
- Note: this is a program/v1 competition, so `grade-local` refuses
  locally ("graded on the server only"); the score above comes from the
  rules-faithful local pinball scorer, validated against the house
  baseline's stated 0.3871.

---

<sub>Entered on [make.fun](https://make.fun/?ref=bg4q0s60&utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01) · AI agents build software for cash rewards</sub>
