from __future__ import annotations

import sqlite3

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from app.database import ALLOWED_VIEWS


class QueryValidationError(ValueError):
    """Raised when a generated query is outside the permitted SQL subset."""


class QueryExecutionError(RuntimeError):
    """Raised when SQLite refuses or cannot complete an allowed query."""


_ALLOWED_FUNCTIONS = {
    "avg",
    "coalesce",
    "count",
    "ifnull",
    "lower",
    "max",
    "min",
    "round",
    "strftime",
    "substr",
    "sum",
    "upper",
}
_MAX_SQL_LENGTH = 4000
_MAX_RESULT_ROWS = 500


def validate_sql(sql: str) -> str:
    """Require one SELECT that references only the reporting views."""
    if not sql or len(sql) > _MAX_SQL_LENGTH:
        raise QueryValidationError(
            f"La consulta debe tener entre 1 y {_MAX_SQL_LENGTH} caracteres."
        )
    try:
        statements = sqlglot.parse(sql, read="sqlite")
    except ParseError as error:
        raise QueryValidationError("La consulta no tiene sintaxis SQL válida.") from error
    if len(statements) != 1 or statements[0] is None:
        raise QueryValidationError("Se permite exactamente una consulta SQL.")

    statement = statements[0]
    if not isinstance(statement, exp.Select):
        raise QueryValidationError("Solo se permiten consultas SELECT.")

    for table in statement.find_all(exp.Table):
        if (
            table.name.lower() not in ALLOWED_VIEWS
            or table.db
            or table.catalog
        ):
            raise QueryValidationError(
                "La consulta solo puede usar las vistas "
                f"{', '.join(sorted(ALLOWED_VIEWS))}."
            )
    return statement.sql(dialect="sqlite")


def _authorize(action: int, arg1: str | None, arg2: str | None, database: str | None, source: str | None) -> int:
    del database
    if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ):
        if action == sqlite3.SQLITE_READ:
            table = (arg1 or "").lower()
            origin = (source or "").lower()
            if table not in ALLOWED_VIEWS and origin not in ALLOWED_VIEWS:
                return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION:
        if (arg2 or "").lower() in _ALLOWED_FUNCTIONS:
            return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def execute_read_only(connection: sqlite3.Connection, sql: str) -> list[dict[str, object]]:
    """Execute a validated query under SQLite's read-only authorizer."""
    safe_sql = validate_sql(sql)
    connection.set_authorizer(_authorize)
    steps = 0

    def limit_work() -> int:
        nonlocal steps
        steps += 1
        return int(steps > 2000)

    connection.set_progress_handler(limit_work, 1000)
    try:
        cursor = connection.execute(safe_sql)
        names = [column[0] for column in cursor.description or ()]
        rows = cursor.fetchmany(_MAX_RESULT_ROWS + 1)
        if len(rows) > _MAX_RESULT_ROWS:
            raise QueryExecutionError(
                f"La consulta supera el límite de {_MAX_RESULT_ROWS} filas."
            )
        return [dict(zip(names, row)) for row in rows]
    except sqlite3.Error as error:
        raise QueryExecutionError(
            f"SQLite rechazó o no pudo completar la consulta: {error}"
        ) from error
    finally:
        connection.set_progress_handler(None, 0)
        connection.set_authorizer(None)
