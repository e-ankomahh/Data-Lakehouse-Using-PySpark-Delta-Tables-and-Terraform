"""Generate test fixtures from real source data files.

Run from the project root:
    python scripts/generate_fixtures.py

Reads the real data files in Data/ (gitignored) and writes small representative
samples to tests/fixtures/. Also injects controlled errors to produce invalid variants.
"""

import json
import pathlib
import random

import pandas as pd

ROOT = pathlib.Path(__file__).parent.parent
DATA_DIR = ROOT / "Data"
FIXTURES_DIR = ROOT / "tests" / "fixtures"
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

SAMPLE_ROWS = 20
random.seed(42)


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------
def _generate_products() -> None:
    src = DATA_DIR / "products.csv"
    if not src.exists():
        print(f"[SKIP] {src} not found")
        return

    df = pd.read_csv(src).head(SAMPLE_ROWS)
    df.to_csv(FIXTURES_DIR / "products_sample.csv", index=False)

    invalid = df.copy()
    # Inject nulls and duplicates
    invalid.loc[0, "product_id"] = None
    invalid = pd.concat([invalid, invalid.iloc[[1]]], ignore_index=True)  # duplicate row 1
    invalid.to_csv(FIXTURES_DIR / "products_invalid.csv", index=False)
    print("[OK] products fixtures written")


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------
def _generate_orders() -> None:
    src = DATA_DIR / "orders_apr_2025.xlsx"
    if not src.exists():
        print(f"[SKIP] {src} not found")
        return

    df = pd.read_excel(src, engine="openpyxl").head(SAMPLE_ROWS)
    _write_jsonl(df, FIXTURES_DIR / "orders_sample.json")

    invalid = df.copy().head(5)
    invalid.loc[0, "order_id"] = None           # null PK
    invalid.loc[1, "total_amount"] = -9.99      # negative amount
    invalid.loc[2, "order_timestamp"] = "2015-01-01 00:00:00"  # out-of-range timestamp
    invalid.loc[3, "total_amount"] = 0.0        # zero amount
    _write_jsonl(invalid, FIXTURES_DIR / "orders_invalid.json")
    print("[OK] orders fixtures written")


# ---------------------------------------------------------------------------
# Order Items
# ---------------------------------------------------------------------------
def _generate_order_items() -> None:
    src = DATA_DIR / "order_items_apr_2025.xlsx"
    if not src.exists():
        print(f"[SKIP] {src} not found")
        return

    df = pd.read_excel(src, engine="openpyxl").head(SAMPLE_ROWS)
    _write_jsonl(df, FIXTURES_DIR / "order_items_sample.json")

    invalid = df.copy().head(5)
    invalid.loc[0, "id"] = None                 # null PK
    invalid.loc[1, "order_id"] = 999999         # FK violation — no such order
    invalid.loc[2, "reordered"] = 2             # invalid boolean flag
    invalid = pd.concat([invalid, invalid.iloc[[3]]], ignore_index=True)  # duplicate id
    _write_jsonl(invalid, FIXTURES_DIR / "order_items_invalid.json")
    print("[OK] order_items fixtures written")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _write_jsonl(df: pd.DataFrame, path: pathlib.Path) -> None:
    """Write DataFrame as newline-delimited JSON (one record per line)."""
    records = df.where(pd.notnull(df), other=None).to_dict(orient="records")
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record) + "\n")


if __name__ == "__main__":
    _generate_products()
    _generate_orders()
    _generate_order_items()
    print(f"\nFixtures written to {FIXTURES_DIR}")
