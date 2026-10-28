"""
Run the SQL data-quality rules against the (simulated) raw tables with DuckDB.

    python src/run_dq_checks.py              # checks the raw tables with injected defects
    python src/run_dq_checks.py --clean      # checks the clean tables (should pass)

Writes reports/dq_report.csv and prints a summary table.
"""
import argparse
import re
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SQL = ROOT / "sql" / "data_quality_checks.sql"
DATA = ROOT / "data" / "simulated"


def load_rules(path=SQL):
    text = path.read_text()
    parts = re.split(r"^-- rule: (.+)$", text, flags=re.M)[1:]
    rules = []
    for header, body in zip(parts[::2], parts[1::2]):
        rule_id, dimension, description = [h.strip() for h in header.split("|")]
        rules.append({"rule_id": rule_id, "dimension": dimension,
                      "description": description, "sql": body.strip().rstrip(";")})
    return rules


def run(clean=False):
    suffix = "clean" if clean else "raw"
    con = duckdb.connect()
    con.execute(f"CREATE VIEW users AS SELECT * FROM read_parquet('{DATA / f'users_{suffix}.parquet'}')")
    con.execute(f"CREATE VIEW events AS SELECT * FROM read_parquet('{DATA / f'events_{suffix}.parquet'}')")
    n_events = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    results = []
    for r in load_rules():
        failed = con.execute(f"SELECT COUNT(*) FROM ({r['sql']})").fetchone()[0]
        results.append({**{k: r[k] for k in ("rule_id", "dimension", "description")},
                        "failed_rows": failed, "status": "FAIL" if failed else "PASS"})
    report = pd.DataFrame(results)

    # Accuracy = share of event rows that pass every row-level event rule
    row_rules = [r for r in load_rules() if r["rule_id"] in
                 {"C1", "C3", "K3", "K4", "K6", "K7", "K8", "T1", "T3"}]
    bad_ids = " UNION ".join(f"SELECT event_id FROM ({r['sql']})" for r in row_rules)
    n_bad = con.execute(f"SELECT COUNT(DISTINCT event_id) FROM ({bad_ids})").fetchone()[0]
    accuracy = 1 - n_bad / n_events
    return report, accuracy, n_events


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", action="store_true")
    args = ap.parse_args()
    report, accuracy, n_events = run(args.clean)
    out = ROOT / "reports"; out.mkdir(exist_ok=True)
    report.to_csv(out / f"dq_report_{'clean' if args.clean else 'raw'}.csv", index=False)
    print(report.to_string(index=False))
    print(f"\n{(report.status == 'FAIL').sum()} of {len(report)} rules failed · "
          f"event-level accuracy {accuracy:.2%} of {n_events:,} events")


if __name__ == "__main__":
    main()
