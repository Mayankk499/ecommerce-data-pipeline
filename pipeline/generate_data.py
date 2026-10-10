"""Generate a realistic, *deliberately messy* e-commerce source system extract.

Real data is never clean, so this generator injects the problems a data
engineer has to deal with every day:

* duplicate rows (same order / order line delivered twice)
* inconsistent country spellings ("india", "IN ", "U.K.")
* missing / malformed emails
* invalid order timestamps
* orders pointing at customers that do not exist (orphans)
* zero / negative quantities, missing prices
* status values in mixed case
* customer records that change over time (latest one must win)

Output layout (what a source system / S3 landing zone would look like):

    data/raw/customers.csv
    data/raw/products.csv
    data/raw/orders/orders_YYYY-MM-DD.jsonl       (one file per day)
    data/raw/order_items/order_items_YYYY-MM-DD.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from datetime import date, datetime, timedelta
from pathlib import Path

COUNTRY_VARIANTS = {
    "India": ["India", "india", "IN", "in ", "INDIA"],
    "United States": ["United States", "USA", "us", "US", " usa"],
    "United Kingdom": ["United Kingdom", "UK", "uk", "U.K."],
    "Germany": ["Germany", "DE", "germany"],
    "Canada": ["Canada", "CA", "canada"],
}
COUNTRY_WEIGHTS = [0.35, 0.30, 0.15, 0.10, 0.10]
CATEGORIES = ["Electronics", "Home", "Fashion", "Sports", "Books"]
STATUSES = ["completed", "shipped", "cancelled", "returned"]
STATUS_WEIGHTS = [0.70, 0.15, 0.08, 0.07]
PAYMENTS = ["card", "upi", "paypal", "cod"]


def _write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def make_customers(rng: random.Random, n: int, start: date) -> list[list]:
    countries = list(COUNTRY_VARIANTS)
    rows = []
    for i in range(1, n + 1):
        cid = f"C{i:05d}"
        country = rng.choices(countries, COUNTRY_WEIGHTS)[0]
        signup = start - timedelta(days=rng.randint(1, 400))
        r = rng.random()
        if r < 0.03:
            email = ""  # missing
        elif r < 0.05:
            email = f"user{i}.example.com"  # malformed (no @)
        else:
            email = f"User{i}@Example.com" if rng.random() < 0.3 else f"user{i}@example.com"
        rows.append([cid, f"Customer {i}", email, rng.choice(COUNTRY_VARIANTS[country]),
                     signup.isoformat(), f"{signup.isoformat()}T09:00:00"])
        # ~3% of customers appear again later with an updated country (they moved)
        if rng.random() < 0.03:
            new_country = rng.choice(countries)
            upd = start + timedelta(days=rng.randint(0, 5))
            rows.append([cid, f"Customer {i}", email, rng.choice(COUNTRY_VARIANTS[new_country]),
                         signup.isoformat(), f"{upd.isoformat()}T10:00:00"])
    return rows


def make_products(rng: random.Random, n: int = 40) -> list[list]:
    rows = []
    for i in range(1, n + 1):
        cat = CATEGORIES[(i - 1) % len(CATEGORIES)]
        rows.append([f"P{i:04d}", f"{cat} item {i}", cat, f"{rng.uniform(5, 400):.2f}"])
    return rows


def make_day(rng, day: date, products: list[list], n_customers: int, base_orders: int, day_idx: int):
    """Return (orders, items) for one day, with injected defects."""
    weekend = 1.3 if day.weekday() >= 5 else 1.0
    n_orders = int(base_orders * weekend * (1 + 0.01 * day_idx))  # mild growth trend
    orders, items = [], []
    for i in range(1, n_orders + 1):
        oid = f"O{day:%Y%m%d}{i:04d}"
        cust = f"C{rng.randint(1, n_customers):05d}"
        if rng.random() < 0.01:
            cust = "C99999"  # orphan customer
        ts = datetime(day.year, day.month, day.day) + timedelta(seconds=rng.randint(0, 86399))
        ts_str = "not-a-date" if rng.random() < 0.01 else ts.isoformat()
        status = rng.choices(STATUSES, STATUS_WEIGHTS)[0]
        if rng.random() < 0.05:
            status = status.upper()
        order = {"order_id": oid, "customer_id": cust, "order_ts": ts_str,
                 "status": status, "payment_method": rng.choice(PAYMENTS)}
        orders.append(order)
        if rng.random() < 0.02:
            orders.append(dict(order))  # duplicate delivery

        for p in rng.sample(products, rng.randint(1, 4)):
            qty = rng.choices([1, 2, 3, 4, 5], [50, 25, 12, 8, 5])[0]
            price = f"{float(p[3]) * rng.uniform(0.9, 1.0):.2f}"
            r = rng.random()
            if r < 0.01:
                qty = rng.choice([0, -1])
            elif r < 0.02:
                price = ""
            line = [oid, p[0], qty, price]
            items.append(line)
            if rng.random() < 0.02:
                items.append(list(line))  # duplicate line
        if rng.random() < 0.005:  # order line whose order never arrived
            items.append([f"O{day:%Y%m%d}9{i:03d}", products[0][0], 1, "10.00"])
    return orders, items


def generate(out_dir, days=30, orders_per_day=200, customers=500,
             start=date(2026, 1, 1), seed=42) -> None:
    out = Path(out_dir)
    rng = random.Random(seed)
    custs = make_customers(rng, customers, start)
    prods = make_products(rng)
    _write_csv(out / "customers.csv",
               ["customer_id", "full_name", "email", "country", "signup_date", "updated_at"], custs)
    _write_csv(out / "products.csv", ["product_id", "product_name", "category", "list_price"], prods)

    # per-day RNG so that asking for more days later keeps earlier days identical
    for d in range(days):
        day = start + timedelta(days=d)
        drng = random.Random(f"{seed}-{day.isoformat()}")
        orders, items = make_day(drng, day, prods, customers, orders_per_day, d)
        op = out / "orders" / f"orders_{day.isoformat()}.jsonl"
        op.parent.mkdir(parents=True, exist_ok=True)
        with op.open("w") as f:
            for o in orders:
                f.write(json.dumps(o) + "\n")
        _write_csv(out / "order_items" / f"order_items_{day.isoformat()}.csv",
                   ["order_id", "product_id", "quantity", "unit_price"], items)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="data/raw")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--orders-per-day", type=int, default=200)
    ap.add_argument("--customers", type=int, default=500)
    ap.add_argument("--start-date", default="2026-01-01")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args(argv)
    generate(a.out, a.days, a.orders_per_day, a.customers, date.fromisoformat(a.start_date), a.seed)
    print(f"Generated {a.days} days of raw data in {a.out}")


if __name__ == "__main__":
    main()
