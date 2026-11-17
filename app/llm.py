from __future__ import annotations

import json

import httpx


class LLMError(RuntimeError):
    """Raised when the model cannot return a usable SQL query."""


SYSTEM_PROMPT = """Eres un generador de consultas de solo lectura para pedidos.
Devuelve exclusivamente un objeto JSON con la propiedad string "sql".
Usa solo estas vistas (nunca tablas base):
- sales_by_month_country(year, month, country, total_sales, order_count)
- top_customers(customer, total_spent, order_count)
El mes debe escribirse con dos dígitos, por ejemplo '03'. Los años son texto.
No inventes columnas ni incluyas explicaciones en el SQL."""


class OpenAICompatibleLLM:
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    async def generate_sql(self, question: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": question},
                        ],
                        "response_format": {"type": "json_object"},
                        "temperature": 0,
                    },
                )
                response.raise_for_status()
        except httpx.HTTPError as error:
            raise LLMError(
                "No se pudo contactar al proveedor LLM; revisa la conexión y la clave."
            ) from error

        try:
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            query = json.loads(content)["sql"]
        except (ValueError, KeyError, TypeError, IndexError) as error:
            raise LLMError(
                "El proveedor LLM devolvió una respuesta JSON inválida o sin SQL."
            ) from error
        if not isinstance(query, str) or not query.strip():
            raise LLMError("El proveedor LLM no devolvió una consulta SQL.")
        return query
