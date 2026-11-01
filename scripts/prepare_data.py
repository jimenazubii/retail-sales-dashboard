"""
Build the compact datasets used by the dashboard from the raw sales CSVs.

The raw data (~3M rows, ~350 MB) has one row per store, product family and day,
already joined with stores, transactions, oil prices and holidays. This script:

1. Removes duplicated rows: the holiday join repeats a (date, store, family) row
   whenever two holidays/events fall on the same day (53,460 extra rows).
2. Applies each holiday only where it is celebrated: national holidays to every
   store, regional ones to stores in that state and local ones to stores in that
   city. Transferred holidays and "Work Day" entries are not treated as days off.
3. Aggregates into two small tables that allow the dashboard to compute exactly
   the same totals and per-row averages as the raw data:
   - data/sales_monthly.parquet: store x family x year x month
   - data/store_daily.parquet:   store x day (with transactions counted once)

Usage:
    python scripts/prepare_data.py [raw_dir]   # default raw_dir: raw/
"""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "raw"
OUT_DIR = ROOT / "data"

COLUMNS = [
    "date", "store_nbr", "family", "sales", "onpromotion", "holiday_type",
    "locale", "locale_name", "transferred", "city", "state", "store_type",
    "cluster", "transactions",
]

HOLIDAY_TYPES_OFF = {"Holiday", "Transfer", "Additional", "Bridge", "Event"}


def load_raw():
    """Read and concatenate the raw CSV parts (only the columns we need)."""
    parts = sorted(RAW_DIR.glob("*.csv"))
    if not parts:
        sys.exit(f"No CSV files found in {RAW_DIR}")
    df = pd.concat(
        (pd.read_csv(p, usecols=COLUMNS, low_memory=False) for p in parts),
        ignore_index=True,
    )
    df["date"] = pd.to_datetime(df["date"])
    print(f"Raw rows: {len(df):,}")
    return df


def holiday_flag(df):
    """
    True when a holiday/event applies to the store on that day.

    A row is a holiday for the store if the holiday is national, or regional in
    the store's state, or local in the store's city; and it was not transferred
    to another date and it is not a compensatory working day.
    """
    applies = (
        (df["locale"] == "National")
        | ((df["locale"] == "Regional") & (df["locale_name"] == df["state"]))
        | ((df["locale"] == "Local") & (df["locale_name"] == df["city"]))
    )
    transferred = df["transferred"].astype(str).str.lower().eq("true")
    is_off = df["holiday_type"].isin(HOLIDAY_TYPES_OFF)
    return applies & is_off & ~transferred


def main():
    df = load_raw()

    # Holiday flag per row, then aggregated per (date, store): a day is a holiday
    # for a store if any of the joined holiday rows applies to it.
    df["is_holiday"] = holiday_flag(df)
    holiday_store_day = df.groupby(["date", "store_nbr"])["is_holiday"].any()

    # 1. Remove the duplicated (date, store, family) rows created by the holiday join
    before = len(df)
    df = df.drop_duplicates(["date", "store_nbr", "family"]).copy()
    print(f"Removed duplicated rows: {before - len(df):,} -> {len(df):,} rows")

    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    df["promo_sales"] = df["sales"].where(df["onpromotion"] > 0, 0.0)

    stores = (
        df[["store_nbr", "city", "state", "store_type", "cluster"]]
        .drop_duplicates("store_nbr")
        .set_index("store_nbr")
    )

    # 2. Monthly table: store x family x year x month
    monthly = (
        df.groupby(["store_nbr", "family", "year", "month"], observed=True)
        .agg(sales=("sales", "sum"), promo_sales=("promo_sales", "sum"), rows=("sales", "size"))
        .reset_index()
    )
    monthly = monthly.join(stores[["state"]], on="store_nbr")

    # 3. Daily table: store x day. Transactions are one value per store and day,
    # repeated in every family row, so they are taken once (not summed).
    daily = (
        df.groupby(["date", "store_nbr"])
        .agg(
            sales=("sales", "sum"),
            rows=("sales", "size"),
            items_on_promo=("onpromotion", "sum"),
            transactions=("transactions", "first"),
        )
        .reset_index()
    )
    daily = daily.join(holiday_store_day, on=["date", "store_nbr"])
    daily = daily.join(stores, on="store_nbr")

    # Compact dtypes
    for table in (monthly, daily):
        for col in ("family", "state", "city", "store_type"):
            if col in table:
                table[col] = table[col].astype("category")
        table["store_nbr"] = table["store_nbr"].astype("int16")
    monthly[["year", "month"]] = monthly[["year", "month"]].astype("int16")
    monthly["rows"] = monthly["rows"].astype("int16")
    daily["rows"] = daily["rows"].astype("int16")
    daily["cluster"] = daily["cluster"].astype("int8")

    OUT_DIR.mkdir(exist_ok=True)
    monthly.to_parquet(OUT_DIR / "sales_monthly.parquet", index=False)
    daily.to_parquet(OUT_DIR / "store_daily.parquet", index=False)

    # Sanity checks: totals must match the de-duplicated raw data
    assert abs(monthly["sales"].sum() - df["sales"].sum()) < 1e-3 * df["sales"].sum()
    assert abs(daily["sales"].sum() - df["sales"].sum()) < 1e-3 * df["sales"].sum()
    assert monthly["rows"].sum() == daily["rows"].sum() == len(df)

    for name in ("sales_monthly", "store_daily"):
        path = OUT_DIR / f"{name}.parquet"
        print(f"Wrote {path.relative_to(ROOT)} ({path.stat().st_size / 1e6:.1f} MB)")
    print(f"Total sales: {df['sales'].sum():,.0f} | "
          f"transactions: {daily['transactions'].sum():,.0f} | "
          f"store-days on holiday: {daily['is_holiday'].mean():.1%}")


if __name__ == "__main__":
    main()
