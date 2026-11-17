from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path


FIELDS = ("date", "customer", "country", "product", "amount", "status")
COUNTRIES = ("España", "Francia", "Alemania", "Italia", "Portugal")
PRODUCTS = ("Auriculares", "Teclado", "Monitor", "Ratón", "Webcam")
STATUSES = ("completado", "pendiente", "cancelado")
CUSTOMERS = tuple(f"Cliente {number:03d}" for number in range(1, 61))


def generate_csv(path: str | Path, seed: int = 2025) -> int:
    """Write a deterministic sample CSV with intentional data quality errors."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    randomizer = random.Random(seed)
    start = date(2024, 1, 1)
    rows: list[dict[str, str]] = []

    for _ in range(1050):
        order_date = start + timedelta(days=randomizer.randrange(730))
        rows.append(
            {
                "date": order_date.isoformat(),
                "customer": randomizer.choice(CUSTOMERS),
                "country": randomizer.choice(COUNTRIES),
                "product": randomizer.choice(PRODUCTS),
                "amount": f"{randomizer.uniform(10, 1250):.2f}",
                "status": randomizer.choice(STATUSES),
            }
        )

    # Ensure the sample contains the example's country/month and a popular client.
    rows[0].update(
        date="2025-03-12",
        customer="Cliente 001",
        country="España",
        product="Monitor",
        amount="249.99",
        status="completado",
    )
    rows[1].update(
        date="2025-03-20",
        customer="Cliente 001",
        country="España",
        product="Teclado",
        amount="79.50",
        status="completado",
    )

    malformed_dates = ("32/13/2025", "ayer", "2025-02-30", "15-03-25", "2025/03/15")
    for index, value in enumerate(malformed_dates, start=2):
        rows[index]["date"] = value
    for index in range(7, 14):
        rows[index]["amount"] = ""

    # Exact repeated records exercise duplicate detection during ingestion.
    rows.extend(dict(rows[index]) for index in range(20, 26))
    with destination.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


if __name__ == "__main__":
    output = Path(__file__).resolve().parents[1] / "data" / "orders_raw.csv"
    print(f"CSV creado: {output} ({generate_csv(output)} filas de datos)")
