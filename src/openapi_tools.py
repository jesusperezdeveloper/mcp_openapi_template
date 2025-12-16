"""
Registro dinámico de herramientas MCP a partir de un OpenAPI.

En este módulo se toma una especificación OpenAPI y se crean
herramientas FastMCP por cada operación, para maximizar la cobertura.

Simplificaciones:
- Parámetros path: se esperan como kwargs con el mismo nombre que en el spec.
- Parámetros query: opcionales salvo que el spec marque required.
- Cuerpo (requestBody): se pasa en el kwarg `body` (dict) y se envía como JSON.
- Respuestas: se devuelve el JSON bruto de la API (raise_for_status en errores).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, Iterable

import httpx
from mcp.server.fastmcp import FastMCP

from .config import get_config


def _collect_parameters(
    path_params: list[dict[str, Any]], op_params: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Recolecta y combina parámetros de path y operación."""
    seen = set()
    merged: list[dict[str, Any]] = []
    for src in (path_params, op_params):
        for param in src:
            name = param.get("name")
            location = param.get("in")
            key = (name, location)
            if key in seen:
                continue
            seen.add(key)
            merged.append(param)
    return merged


def _sanitize_name(name: str, max_length: int = 64) -> str:
    """
    Sanitiza un nombre para uso como tool name MCP.

    - Convierte a minúsculas
    - Reemplaza caracteres no alfanuméricos por underscore
    - Compacta múltiples underscores consecutivos
    - Trunca a max_length caracteres (default 64, límite MCP)
    """
    out = []
    for ch in name:
        if ch.isalnum():
            out.append(ch.lower())
        else:
            out.append("_")
    joined = "".join(out)
    clean = "_".join(filter(None, joined.split("_")))
    if not clean:
        clean = "op"
    if len(clean) > max_length:
        clean = clean[:max_length].rstrip("_")
    return clean


def _make_tool(
    *,
    client_factory: Callable[[], httpx.AsyncClient],
    method: str,
    path_template: str,
    required_path_params: list[str],
    required_query_params: list[str],
    optional_query_params: list[str],
    auth_params: Callable[[], dict[str, str]],
    auth_headers: Callable[[], dict[str, str]],
    has_request_body: bool,
    tool_name: str,
) -> Callable[..., Any]:
    """
    Factory function que crea una tool con las variables capturadas por valor.

    Esto evita el bug de closure donde todas las tools terminan usando
    los valores de la última iteración del loop.
    """
    async def _tool(**kwargs: Any) -> Any:
        return await _execute_request(
            client_factory=client_factory,
            method=method,
            path_template=path_template,
            required_path_params=required_path_params,
            required_query_params=required_query_params,
            optional_query_params=optional_query_params,
            auth_params=auth_params,
            auth_headers=auth_headers,
            has_request_body=has_request_body,
            args=kwargs,
        )

    _tool.__name__ = tool_name
    return _tool


def register_openapi_tools(
    mcp: FastMCP,
    *,
    spec_path: Path,
    auth_params: Callable[[], dict[str, str]],
    auth_headers: Callable[[], dict[str, str]],
    client_factory: Callable[[], httpx.AsyncClient],
    tool_prefix: str | None = None,
) -> int:
    """
    Registra herramientas FastMCP para cada operación del OpenAPI.

    Los nombres se basan en operationId si existe; si no, en método + path.

    Args:
        mcp: Instancia de FastMCP donde registrar las herramientas
        spec_path: Ruta al archivo OpenAPI JSON
        auth_params: Función que retorna parámetros de autenticación
        auth_headers: Función que retorna headers de autenticación
        client_factory: Función que crea un cliente HTTP
        tool_prefix: Prefijo para los nombres de las herramientas.
                     Si no se especifica, se usa el de config.

    Returns:
        Número de herramientas registradas.
    """
    config = get_config()
    prefix = tool_prefix or config.api.tool_prefix

    spec = json.loads(spec_path.read_text())
    paths: Dict[str, Any] = spec.get("paths", {})
    seen_tool_names: set[str] = set()

    # Calcular max_length para el nombre sanitizado
    # Dejamos espacio para el prefijo + underscore
    prefix_len = len(prefix) + 1  # +1 por el underscore
    max_name_len = 64 - prefix_len

    for path, path_item in paths.items():
        path_level_params = path_item.get("parameters", [])
        for method, op in path_item.items():
            if method.lower() not in {"get", "post", "put", "delete", "patch"}:
                continue
            if not isinstance(op, dict):
                continue

            op_id = op.get("operationId")
            name_seed = op_id or f"{method}_{path}"
            tool_name = f"{prefix}_{_sanitize_name(name_seed, max_length=max_name_len)}"

            if tool_name in seen_tool_names:
                continue
            seen_tool_names.add(tool_name)

            op_params = op.get("parameters", [])
            all_params = _collect_parameters(path_level_params, op_params)

            required_path = [p["name"] for p in all_params if p.get("in") == "path"]
            required_query = [
                p["name"]
                for p in all_params
                if p.get("in") == "query" and p.get("required") is True
            ]
            optional_query = [
                p["name"]
                for p in all_params
                if p.get("in") == "query" and p.get("required") is not True
            ]

            summary = op.get("summary") or op.get("description") or ""
            doc_lines = [
                f"{method.upper()} {path}",
                summary,
                f"Path params requeridos: {required_path}" if required_path else "Sin path params",
                f"Query requeridos: {required_query}" if required_query else "Sin query requeridos",
                f"Query opcionales: {optional_query}" if optional_query else "Sin query opcionales",
                "Body opcional: `body` (dict) si el endpoint lo admite.",
            ]
            doc = "\n".join(doc_lines)

            tool_func = _make_tool(
                client_factory=client_factory,
                method=method,
                path_template=path,
                required_path_params=required_path,
                required_query_params=required_query,
                optional_query_params=optional_query,
                auth_params=auth_params,
                auth_headers=auth_headers,
                has_request_body=op.get("requestBody") is not None,
                tool_name=tool_name,
            )

            mcp.tool(name=tool_name, description=doc)(tool_func)

    return len(seen_tool_names)


async def _execute_request(
    *,
    client_factory: Callable[[], httpx.AsyncClient],
    method: str,
    path_template: str,
    required_path_params: Iterable[str],
    required_query_params: Iterable[str],
    optional_query_params: Iterable[str],
    auth_params: Callable[[], dict[str, str]],
    auth_headers: Callable[[], dict[str, str]],
    has_request_body: bool,
    args: dict[str, Any],
) -> Any:
    """Ejecuta una request HTTP a la API."""
    # Validar path params requeridos
    missing_path = [p for p in required_path_params if p not in args]
    if missing_path:
        raise ValueError(f"Faltan path params requeridos: {missing_path}")

    # Validar query params requeridos
    missing_query = [p for p in required_query_params if p not in args]
    if missing_query:
        raise ValueError(f"Faltan query params requeridos: {missing_query}")

    # Construir path
    path = path_template
    for p in required_path_params:
        path = path.replace("{" + p + "}", str(args[p]))

    # Construir query params
    query: dict[str, Any] = {k: args[k] for k in required_query_params if k in args}
    for k in optional_query_params:
        if k in args and args[k] is not None:
            query[k] = args[k]
    query.update(auth_params())

    # Headers de autenticación
    headers = auth_headers()

    # Body
    json_body: Any = None
    if has_request_body and "body" in args:
        json_body = args["body"]

    async with client_factory() as client:
        resp = await client.request(
            method.upper(),
            path,
            params=query,
            json=json_body,
            headers=headers if headers else None,
        )
        resp.raise_for_status()
        try:
            return resp.json()
        except Exception:
            return resp.text
