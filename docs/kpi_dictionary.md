# KPI Dictionary

Shared definitions for the product metrics used in this repository. Each metric has one owner definition so that dashboards, experiment readouts and ad-hoc analyses report the same number.

| KPI | Definition | Grain | Numerator | Denominator | Notes / edge cases |
|---|---|---|---|---|---|
| **DAU** (daily active users) | Distinct users with ≥ 1 `session_start` on a calendar day (UTC) | Day | Distinct `user_id` with `session_start` | — | Excludes events failing DQ rules C1, K3, T1 |
| **Onboarding completion rate** | Share of new users who fire `onboarding_complete` on their signup day | Signup cohort | Users with `onboarding_complete` within 24h of signup | Users who signed up | Day-0 window; later completions are not counted |
| **D1 retention** | Share of users active on day 1 after signup | Signup cohort | Users with a `session_start` on day 1 | Users who signed up ≥ 1 day ago | Cohort is only reportable once fully matured |
| **D7 retention** | Share of users active on day 7 after signup | Signup cohort | Users with a `session_start` on day 7 | Users who signed up ≥ 7 days ago | Primary north-star input; exact-day definition (not "within 7 days") |
| **Feature adoption (7d)** | Share of new users who use the feature at least once in their first 7 days | Signup cohort | Users with ≥ 1 `feature_use` in days 0–6 | Users who signed up ≥ 7 days ago | |
| **Paid conversion (28d)** | Share of new users with ≥ 1 purchase within 28 days | Signup cohort | Users with ≥ 1 `purchase` in days 0–27 | Users who signed up ≥ 28 days ago | Excludes refunds (negative revenue fails DQ rule K6) |
| **ARPU (28d)** | Revenue per new user in the first 28 days | Signup cohort | Sum of `revenue_usd` on `purchase` events, days 0–27 | Users who signed up ≥ 28 days ago | USD; revenue on non-purchase events is a DQ failure (K7) |

## Data-quality dependencies
Every KPI is computed after the [validation rules](../sql/data_quality_checks.sql) run. A **FAIL** on a completeness rule (C1–C4) blocks publication of that day's numbers. Consistency and timeliness failures are logged and the affected rows are excluded.
