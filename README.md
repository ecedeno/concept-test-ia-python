# Análisis de pedidos con Python

Proyecto pequeño y reproducible para generar pedidos de ejemplo, limpiar errores
de calidad, cargarlos en SQLite y consultarlos con una API FastAPI asistida por
un LLM.

## Requisitos

- Python 3.10 o posterior.
- Una clave de API de OpenAI para usar `/ask` en producción. No se guarda en el
  repositorio.

## Instalación y ejecución

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Genera 1.056 filas, con duplicados, fechas inválidas e importes vacíos.
python -m app.generate_orders

# Limpia el CSV y carga data/orders.sqlite3.
python -m app.clean_load

# Configura la clave en el entorno de la terminal, no en un archivo versionado.
export OPENAI_API_KEY="..."
uvicorn app.main:app --reload
```

Consulta `POST http://127.0.0.1:8000/ask`:

```json
{"question": "¿Cuánto vendimos en España en marzo de 2025?"}
```

Respuesta típica:

```json
{
  "question": "¿Cuánto vendimos en España en marzo de 2025?",
  "sql": "SELECT ...",
  "results": [
    {
      "year": "2025",
      "month": "03",
      "country": "España",
      "total_sales": 1279.89,
      "order_count": 4
    }
  ]
}
```

La respuesta incluye todas las filas que coinciden (los datos incluyen más de
un año); para acotar un año, indícalo en la pregunta. La API ofrece también
`OPENAI_MODEL` (por defecto `gpt-4o-mini`), `OPENAI_BASE_URL` (por defecto el
endpoint de OpenAI) y `ORDERS_DB_PATH` (por defecto `data/orders.sqlite3`).
La documentación interactiva de FastAPI está en `/docs`.

## Datos y decisiones

- La semilla fija (`2025`) hace que el CSV se pueda volver a generar de forma
  idéntica. Contiene 1.050 pedidos base, seis copias exactas, cinco fechas mal
  escritas y siete importes vacíos. Los pedidos base mantienen al menos mil
  registros válidos tras la limpieza.
- El importador interpreta fechas ISO, normaliza espacios e importes decimales,
  descarta filas con fecha o importe inválido y elimina duplicados exactos
  después de normalizar. La carga reemplaza el contenido de `orders` para que
  repetirla sea determinista.
- SQLite evita necesitar un servicio externo. `sales_by_month_country` agrupa
  pedidos completados por año, mes y país; `top_customers` contiene los diez
  clientes con mayor gasto en pedidos completados.
- El proveedor de lenguaje se implementa con la API compatible de OpenAI y
  `httpx`. El modelo solo puede proponer SQL: SQLGlot exige una única sentencia
  `SELECT` sobre las dos vistas permitidas; además, la conexión abre la base en
  modo de solo lectura y un authorizer de SQLite bloquea escrituras y lecturas
  directas de tablas. Se limitan el tiempo de trabajo y las filas de salida.
- Un fallo de red/clave del LLM devuelve HTTP 502; una consulta inválida o no
  ejecutable devuelve HTTP 422, con un mensaje explícito.

## Pruebas

```bash
pytest -q
```

Incluyen limpieza, validación y autorización de consultas, y una prueba de
integración del endpoint con el LLM simulado; no necesitan clave ni red.

## Si tuviera más tiempo

- Añadir soporte para varios proveedores LLM con respuestas estructuradas y
  reintentos limitados.
- Incorporar una tabla de auditoría de filas rechazadas y un informe de calidad
  más detallado.
- Añadir autenticación, métricas, paginación y límites de tasa a la API.
- Probar en PostgreSQL administrado y añadir pruebas de integración aisladas.

## Uso de IA

Le pedí a la IA que construyera el flujo completo: generador de datos
reproducibles con errores intencionales, limpieza y carga, vistas analíticas,
API FastAPI con SQL generado por LLM pero limitado a solo lectura, pruebas con
LLM simulado y esta guía de ejecución.

Acepté SQLite para que el proyecto se ejecute localmente sin infraestructura y
una API compatible con OpenAI para evitar acoplar la lógica del endpoint a un
SDK de proveedor. Revisé y ajusté el enfoque para que la validación no dependiera
solo de instrucciones al modelo: agregué análisis sintáctico con allowlist,
apertura SQLite en modo lectura y autorización a nivel de motor; también añadí
una muestra reproducible, límites de consultas y casos de prueba para las
respuestas inválidas. La clave se obtiene únicamente de variables de entorno.
