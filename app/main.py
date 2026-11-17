from __future__ import annotations

import os
import sqlite3
from typing import Protocol

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.database import connect_read_only
from app.llm import LLMError, OpenAICompatibleLLM
from app.sql_guard import QueryExecutionError, QueryValidationError, execute_read_only


class SQLGenerator(Protocol):
    async def generate_sql(self, question: str) -> str: ...


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


app = FastAPI(title="API de análisis de pedidos")


def get_llm() -> SQLGenerator:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Falta OPENAI_API_KEY; configura la clave del proveedor LLM.",
        )
    return OpenAICompatibleLLM(
        api_key=api_key,
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    )


@app.post("/ask")
async def ask_question(
    request: QuestionRequest,
    llm: SQLGenerator = Depends(get_llm),
) -> dict[str, object]:
    try:
        sql = await llm.generate_sql(request.question)
    except LLMError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    database_path = os.getenv("ORDERS_DB_PATH", "data/orders.sqlite3")
    try:
        with connect_read_only(database_path) as connection:
            results = execute_read_only(connection, sql)
    except QueryValidationError as error:
        raise HTTPException(
            status_code=422,
            detail=f"Consulta del modelo rechazada: {error}",
        ) from error
    except QueryExecutionError as error:
        raise HTTPException(
            status_code=422,
            detail=f"No se pudo ejecutar la consulta del modelo: {error}",
        ) from error
    except (OSError, sqlite3.Error) as error:
        raise HTTPException(
            status_code=503,
            detail="No se pudo abrir la base de datos de pedidos.",
        ) from error

    return {"question": request.question, "sql": sql, "results": results}
