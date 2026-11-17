from __future__ import annotations

import sqlite3
from pathlib import Path


ALLOWED_VIEWS = {"sales_by_month_country", "top_customers"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    order_id INTEGER PRIMARY KEY,
    order_date TEXT NOT NULL,
    customer TEXT NOT NULL,
    country TEXT NOT NULL,
    product TEXT NOT NULL,
    amount REAL NOT NULL,
    status TEXT NOT NULL
);

DROP VIEW IF EXISTS sales_by_month_country;
CREATE VIEW sales_by_month_country AS
SELECT
    strftime('%Y', order_date) AS year,
    strftime('%m', order_date) AS month,
    country,
    ROUND(SUM(amount), 2) AS total_sales,
    COUNT(*) AS order_count
FROM orders
WHERE status = 'completado'
GROUP BY year, month, country;

DROP VIEW IF EXISTS top_customers;
CREATE VIEW top_customers AS
SELECT
    customer,
    ROUND(SUM(amount), 2) AS total_spent,
    COUNT(*) AS order_count
FROM orders
WHERE status = 'completado'
GROUP BY customer
ORDER BY total_spent DESC
LIMIT 10;
"""


def connect(database_path: str | Path) -> sqlite3.Connection:
    """Open and initialize the SQLite database and its reporting views."""
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    return connection


def connect_read_only(database_path: str | Path) -> sqlite3.Connection:
    """Open an existing SQLite database without write access."""
    path = Path(database_path).resolve()
    connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection
