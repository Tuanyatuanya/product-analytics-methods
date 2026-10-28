"""
Simulate a product-usage dataset for the DiD, data-quality and metrics demos.

EVERYTHING HERE IS SIMULATED. No real company or user data is used.
The generator plants known "ground truth" so each analysis can be checked:

  * A feature ("smart reminders") launches on 2025-03-03 in regions NA and EMEA only.
    True effect on 7-day retention: +3.0 percentage points.
  * Completing onboarding raises the probability of 7-day retention.
  * A set of data-quality defects is injected into the event log
    (see INJECTED_DEFECTS) for the SQL validation rules to catch.

    python src/simulate_product_data.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 2025
OUT = Path(__file__).resolve().parents[1] / "data" / "simulated"
START, N_DAYS = pd.Timestamp("2025-01-06"), 112          # 16 weeks, Mondays
LAUNCH = pd.Timestamp("2025-03-03")                      # start of week 9
TREATED_REGIONS = {"NA", "EMEA"}
TRUE_EFFECT_PP = 3.0
N_USERS = 40_000

REGION_BASE = {"NA": 0.20, "EMEA": 0.18, "APAC": 0.16, "LATAM": 0.14}   # baseline D7 retention
CHANNELS = {"organic": 0.40, "paid_social": 0.30, "referral": 0.15, "search": 0.15}
ONBOARD_P = {"organic": 0.62, "paid_social": 0.45, "referral": 0.70, "search": 0.55}


def simulate_users(rng):
    n = N_USERS
    signup_day = rng.integers(0, N_DAYS, n)
    signup = START + pd.to_timedelta(signup_day, "D") + pd.to_timedelta(rng.integers(0, 86_400, n), "s")
    region = rng.choice(list(REGION_BASE), n, p=[0.35, 0.30, 0.20, 0.15])
    channel = rng.choice(list(CHANNELS), n, p=list(CHANNELS.values()))
    platform = rng.choice(["ios", "android", "web"], n, p=[0.45, 0.40, 0.15])
    onboarded = rng.random(n) < np.vectorize(ONBOARD_P.get)(channel)

    week = signup_day // 7
    trend = 0.004 * week                                   # common product-wide improvement
    season = 0.01 * np.sin(week / 16 * 2 * np.pi)           # shared seasonality
    treated = np.isin(region, list(TREATED_REGIONS)) & (signup >= LAUNCH)
    p_d7 = (np.vectorize(REGION_BASE.get)(region) + trend + season
            + 0.10 * onboarded - 0.05                       # onboarding lift (centered)
            + TRUE_EFFECT_PP / 100 * treated)
    retained_d7 = rng.random(n) < np.clip(p_d7, 0.01, 0.95)
    retained_d1 = retained_d7 | (rng.random(n) < 0.35)

    return pd.DataFrame({
        "user_id": np.arange(100_000, 100_000 + n),
        "signup_ts": signup, "region": region, "acquisition_channel": channel,
        "platform": platform, "onboarding_completed": onboarded,
        "retained_d1": retained_d1, "retained_d7": retained_d7,
    })


def simulate_events(rng, users):
    rows = []
    feature_user = rng.random(len(users)) < 0.40 + 0.15 * users["onboarding_completed"].to_numpy()
    for u, uses_feature in zip(users.itertuples(index=False), feature_user):
        active_days = [0]
        if u.retained_d1:
            active_days.append(1)
        active_days += list(rng.choice(range(2, 7), rng.integers(0, 3), replace=False))
        if u.retained_d7:
            active_days += [7] + list(rng.choice(range(8, 28), rng.integers(1, 6), replace=False))
        for d in active_days:
            ts = u.signup_ts + pd.Timedelta(days=int(d), seconds=int(rng.integers(0, 40_000)))
            rows.append((u.user_id, ts, "session_start", 0.0))
            if u.onboarding_completed and d == 0:
                rows.append((u.user_id, ts + pd.Timedelta(minutes=3), "onboarding_complete", 0.0))
            for _ in range(rng.poisson(1.5) if uses_feature else 0):
                rows.append((u.user_id, ts + pd.Timedelta(minutes=int(rng.integers(1, 60))), "feature_use", 0.0))
            if rng.random() < 0.03:
                rows.append((u.user_id, ts + pd.Timedelta(minutes=30), "purchase", float(rng.choice([0.99, 4.99, 9.99]))))
    ev = pd.DataFrame(rows, columns=["user_id", "event_ts", "event_type", "revenue_usd"])
    ev = ev[ev["event_ts"] < START + pd.Timedelta(days=N_DAYS + 28)].sort_values("event_ts").reset_index(drop=True)
    ev.insert(0, "event_id", np.arange(1, len(ev) + 1))
    lag = pd.to_timedelta(rng.exponential(600, len(ev)).astype(int), "s")
    ev["ingested_ts"] = ev["event_ts"] + lag
    return ev


# Defects injected on purpose; each SQL rule in sql/data_quality_checks.sql should catch one.
INJECTED_DEFECTS = {
    "duplicate_event_id": 40, "null_user_id": 25, "orphan_user_id": 30, "unknown_event_type": 20,
    "negative_revenue": 8, "event_before_signup": 35, "future_event_ts": 12, "late_ingestion": 60,
    "revenue_on_non_purchase": 15, "duplicate_user": 10, "null_region": 18, "invalid_platform": 12,
}


def inject_defects(rng, users, ev):
    users, ev = users.copy(), ev.copy()
    pick = lambda df, k: rng.choice(df.index, k, replace=False)
    d = INJECTED_DEFECTS
    ev = pd.concat([ev, ev.loc[pick(ev, d["duplicate_event_id"])]], ignore_index=True)
    ev["user_id"] = ev["user_id"].astype("Int64")
    ev.loc[pick(ev, d["null_user_id"]), "user_id"] = pd.NA
    ev.loc[pick(ev, d["orphan_user_id"]), "user_id"] = 999_999
    ev.loc[pick(ev, d["unknown_event_type"]), "event_type"] = "sesion_start"          # typo'd event name
    buy = ev.index[ev["event_type"] == "purchase"]
    ev.loc[rng.choice(buy, d["negative_revenue"], replace=False), "revenue_usd"] = -4.99
    i = pick(ev, d["event_before_signup"]); ev.loc[i, "event_ts"] -= pd.Timedelta(days=30)
    ev.loc[i, "ingested_ts"] = ev.loc[i, "event_ts"] + pd.Timedelta(minutes=5)
    i = pick(ev, d["future_event_ts"]); ev.loc[i, "event_ts"] = pd.Timestamp("2030-01-01")
    ev.loc[i, "ingested_ts"] = pd.Timestamp("2030-01-01 00:05")
    i = pick(ev, d["late_ingestion"]); ev.loc[i, "ingested_ts"] = ev.loc[i, "event_ts"] + pd.Timedelta(days=3)
    non_buy = ev.index[ev["event_type"] == "feature_use"]
    ev.loc[rng.choice(non_buy, d["revenue_on_non_purchase"], replace=False), "revenue_usd"] = 9.99
    # one missing day of events (pipeline outage) for the timeliness rule
    ev = ev[ev["event_ts"].dt.normalize() != pd.Timestamp("2025-02-14")]

    users = pd.concat([users, users.loc[pick(users, d["duplicate_user"])]], ignore_index=True)
    users.loc[pick(users, d["null_region"]), "region"] = None
    users.loc[pick(users, d["invalid_platform"]), "platform"] = "Android "       # casing/whitespace
    return users, ev.reset_index(drop=True)


def main():
    rng = np.random.default_rng(SEED)
    users = simulate_users(rng)
    events = simulate_events(rng, users)
    OUT.mkdir(parents=True, exist_ok=True)
    users.to_parquet(OUT / "users_clean.parquet", index=False)        # ground truth for analysis
    events.to_parquet(OUT / "events_clean.parquet", index=False)
    users_raw, events_raw = inject_defects(rng, users, events)
    users_raw.to_parquet(OUT / "users_raw.parquet", index=False)      # what the DQ checks run on
    events_raw.to_parquet(OUT / "events_raw.parquet", index=False)
    print(f"users: {len(users):,}  events: {len(events):,}  (raw with defects: {len(users_raw):,} / {len(events_raw):,})")


if __name__ == "__main__":
    main()
