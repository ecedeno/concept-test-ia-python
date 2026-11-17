from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.clean_load import clean_rows, load_csv
from app.database import connect
from app.generate_orders import generate_csv
from app.llm import LLMError
from app.main import app, get_llm
from app.sql_guard import (
    QueryExecutionError,
    QueryValidationError,
    execute_read_only,
    validate_sql,
)
import app.sql_guard as sql_guard


def test_cleaning_removes_duplicates_and_bad_rows() -> None:
    rows = [
        {
            "date": "2025-03-01",
            "customer": " Ana ",
            "country": "España",
            "product": "Teclado",
            "amount": "10",
            "status": "completado",
        },
        {
            "date": "2025-03-01",
            "customer": "Ana",
            "country": "España",
            "product": "Teclado",
            "amount": "10.00",
            "status": "completado",
        },
        {
            "date": "mañana",
            "customer": "Luis",
            "country": "España",
            "product": "Monitor",
            "amount": "20",
            "status": "completado",
        },
        {
            "date": "2025-03-03",
            "customer": "Eva",
            "country": "España",
            "product": "Ratón",
            "amount": "",
            "status": "pendiente",
        },
    ]

    cleaned, report = clean_rows(rows)

    assert len(cleaned) == 1
    assert cleaned[0][1] == "Ana"
    assert report.loaded == 1
    assert report.duplicates == 1
    assert report.invalid_dates == 1
    assert report.invalid_amounts == 1


def test_sql_validation_allows_views_and_rejects_writes_or_base_tables() -> None:
    assert "sales_by_month_country" in validate_sql(
        "SELECT country, total_sales FROM sales_by_month_country"
    )
    with pytest.raises(QueryValidationError, match="SELECT"):
        validate_sql("DELETE FROM orders")
    with pytest.raises(QueryValidationError, match="vistas"):
        validate_sql("SELECT * FROM orders")
    with pytest.raises(QueryValidationError, match="exactamente una"):
        validate_sql("SELECT 1; SELECT 2")


def test_execution_authorizer_blocks_unsafe_sql_beyond_parser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "orders.sqlite3"
    with connect(database_path) as connection:
        connection.execute(
            """INSERT INTO orders
               (order_date, customer, country, product, amount, status)
               VALUES ('2025-03-12', 'Ana', 'España', 'Monitor', 25, 'completado')"""
        )

    with connect(database_path) as connection:
        results = execute_read_only(
            connection,
            "SELECT country, total_sales FROM sales_by_month_country",
        )
        assert results == [{"country": "España", "total_sales": 25.0}]

        monkeypatch.setattr(sql_guard, "validate_sql", lambda _: "SELECT * FROM orders")
        with pytest.raises(QueryExecutionError, match="SQLite rechazó"):
            execute_read_only(connection, "SELECT * FROM orders")


def test_endpoint_uses_simulated_llm_and_returns_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "orders.sqlite3"
    csv_path = tmp_path / "orders.csv"
    generate_csv(csv_path)
    report = load_csv(csv_path, database_path)
    assert report.loaded >= 1000
    monkeypatch.setenv("ORDERS_DB_PATH", str(database_path))

    class FakeLLM:
        async def generate_sql(self, question: str) -> str:
            assert "España" in question
            return (
                "SELECT country, month, total_sales "
                "FROM sales_by_month_country "
                "WHERE country = 'España' AND month = '03'"
            )

    app.dependency_overrides[get_llm] = lambda: FakeLLM()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/ask", json={"question": "¿Cuánto vendimos en España en marzo?"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["results"]
    assert all(row["country"] == "España" for row in payload["results"])
    assert all(row["month"] == "03" for row in payload["results"])


def test_endpoint_returns_clear_error_for_invalid_llm_sql() -> None:
    class FakeLLM:
        async def generate_sql(self, question: str) -> str:
            return "DROP TABLE orders"

    app.dependency_overrides[get_llm] = lambda: FakeLLM()
    try:
        with TestClient(app) as client:
            response = client.post("/ask", json={"question": "borra todo"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "Consulta del modelo rechazada" in response.json()["detail"]


def test_endpoint_returns_clear_error_when_llm_fails() -> None:
    class BrokenLLM:
        async def generate_sql(self, question: str) -> str:
            raise LLMError("El proveedor LLM no devolvió una consulta SQL.")

    app.dependency_overrides[get_llm] = lambda: BrokenLLM()
    try:
        with TestClient(app) as client:
            response = client.post("/ask", json={"question": "ventas"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
    assert "no devolvió una consulta SQL" in response.json()["detail"]
