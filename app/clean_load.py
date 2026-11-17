from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.database import connect


@dataclass(frozen=True)
class LoadReport:
    loaded: int
    duplicates: int
    invalid_dates: int
    invalid_amounts: int


def clean_rows(rows: list[dict[str, str]]) -> tuple[list[tuple[str, ...]], LoadReport]:
    """Normalize valid CSV records and count each class of rejected row."""
    cleaned: list[tuple[str, ...]] = []
    seen: set[tuple[str, ...]] = set()
    duplicates = invalid_dates = invalid_amounts = 0

    for row in rows:
        try:
            order_date = date.fromisoformat(row["date"].strip()).isoformat()
        except (ValueError, KeyError):
            invalid_dates += 1
            continue
        try:
            amount = Decimal(row["amount"].strip())
            if not amount.is_finite() or amount < 0:
                raise InvalidOperation
            amount_text = str(amount.quantize(Decimal("0.01")))
        except (InvalidOperation, ValueError, KeyError):
            invalid_amounts += 1
            continue

        record = (
            order_date,
            row["customer"].strip(),
            row["country"].strip(),
            row["product"].strip(),
            amount_text,
            row["status"].strip(),
        )
        if record in seen:
            duplicates += 1
            continue
        seen.add(record)
        cleaned.append(record)

    return cleaned, LoadReport(
        loaded=len(cleaned),
        duplicates=duplicates,
        invalid_dates=invalid_dates,
        invalid_amounts=invalid_amounts,
    )


def load_csv(csv_path: str | Path, database_path: str | Path) -> LoadReport:
    with Path(csv_path).open(newline="", encoding="utf-8") as csv_file:
        cleaned, report = clean_rows(list(csv.DictReader(csv_file)))

    with connect(database_path) as connection:
        connection.execute("DELETE FROM orders")
        connection.executemany(
            """INSERT INTO orders
               (order_date, customer, country, product, amount, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            cleaned,
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean the sample CSV into SQLite.")
    parser.add_argument("--csv", default="data/orders_raw.csv")
    parser.add_argument("--db", default="data/orders.sqlite3")
    args = parser.parse_args()
    report = load_csv(args.csv, args.db)
    print(
        f"Cargados: {report.loaded}; duplicados: {report.duplicates}; "
        f"fechas inválidas: {report.invalid_dates}; "
        f"importes inválidos/vacíos: {report.invalid_amounts}"
    )


if __name__ == "__main__":
    main()
