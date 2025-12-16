"""
Servidor MCP base con soporte para OpenAPI.

AUTENTICACIÓN:
Este MCP requiere autenticación via Auth Gateway.
1. El usuario debe hacer login en Auth Gateway para obtener un JWT
2. Llamar a set_auth_token(jwt) para configurar la sesión
3. Las credenciales de la API se obtienen automáticamente del Gateway

Soporta dos modos de transporte:
- stdio: Para uso local con Claude Desktop/Cursor (por defecto)
- sse: Para despliegue remoto en VPS/EasyPanel (activar con MCP_TRANSPORT=sse)

Requiere que `vendor/` esté en PYTHONPATH para resolver `mcp` (vendorizado).
"""

from __future__ import annotations

import asyncio
import os
import random
import sys
from pathlib import Path
from typing import Any, Callable, Literal, TypeVar

import httpx
import structlog
from dotenv import load_dotenv
from fastapi import HTTPException
from mcp.server.fastmcp import FastMCP

from .config import get_config
from .openapi_tools import register_openapi_tools
from .validation import sanitize_string
from .tool_policies import log_tool_execution
from .auth_gateway import (
    get_auth_service,
    AuthGatewayService,
    AuthGatewayError,
    AUTH_GATEWAY_URL,
)

# Configurar structlog
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer() if os.getenv("LOG_FORMAT") == "json" else structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

T = TypeVar("T")

load_dotenv()

# Cargar configuración
config = get_config()

# Configuración de la API
BASE_URL = os.getenv("API_BASE_URL", config.api.base_url)
SPEC_PATH = os.getenv("OPENAPI_SPEC_PATH", "openapi/spec.json")

# Configuración de transporte SSE
MCP_TRANSPORT: Literal["stdio", "sse"] = os.getenv("MCP_TRANSPORT", "stdio")  # type: ignore
MCP_HOST = os.getenv("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("MCP_PORT", "8000"))


def _require_auth() -> AuthGatewayService:
    """
    Verifica que el usuario esté autenticado via Auth Gateway.

    Returns:
        AuthGatewayService con credenciales válidas

    Raises:
        RuntimeError: Si no hay JWT configurado o las credenciales expiraron
    """
    auth_service = get_auth_service()

    if not auth_service.is_authenticated:
        raise RuntimeError(
            "Autenticación requerida.\n\n"
            f"Este MCP requiere autenticación via Auth Gateway.\n"
            "Pasos:\n"
            "  1. Haz login en Auth Gateway para obtener tu JWT\n"
            "  2. Llama a la herramienta 'set_auth_token' con tu JWT\n"
            "  3. Luego podrás usar las demás herramientas\n\n"
            f"Auth Gateway: {AUTH_GATEWAY_URL}"
        )

    return auth_service


def _client() -> httpx.AsyncClient:
    """Crea un cliente HTTP (las credenciales se añaden en cada request)."""
    return httpx.AsyncClient(base_url=BASE_URL, timeout=config.api.timeout)


def _auth_params() -> dict[str, str]:
    """Obtiene los parámetros de autenticación desde Auth Gateway."""
    auth_service = _require_auth()
    return auth_service.get_auth_params()


def _auth_headers() -> dict[str, str]:
    """Obtiene los headers de autenticación desde Auth Gateway."""
    auth_service = _require_auth()
    return auth_service.get_auth_headers()


def _merge_auth(params: dict[str, Any] | None) -> dict[str, Any]:
    """Mezcla parámetros con credenciales de autenticación."""
    merged = dict(params or {})
    auth = _auth_params()
    for key, value in auth.items():
        merged.setdefault(key, value)
    return merged


# Configuración de retry
RETRY_MAX_ATTEMPTS = int(os.getenv("RETRY_MAX_ATTEMPTS", "3"))
RETRY_BASE_DELAY = float(os.getenv("RETRY_BASE_DELAY", "1.0"))
RETRY_MAX_DELAY = float(os.getenv("RETRY_MAX_DELAY", "30.0"))
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


async def with_retry(
    func: Callable[[], T],
    *,
    max_attempts: int = RETRY_MAX_ATTEMPTS,
    base_delay: float = RETRY_BASE_DELAY,
    max_delay: float = RETRY_MAX_DELAY,
    retryable_status: set[int] = RETRYABLE_STATUS_CODES,
) -> T:
    """
    Ejecuta una función async con retry y backoff exponencial.

    Args:
        func: Función async a ejecutar
        max_attempts: Número máximo de intentos (default: 3)
        base_delay: Delay base en segundos (default: 1.0)
        max_delay: Delay máximo en segundos (default: 30.0)
        retryable_status: Códigos HTTP que disparan retry

    Returns:
        El resultado de la función

    Raises:
        httpx.HTTPStatusError: Si se agotan los reintentos o el error no es retriable
        Exception: Cualquier otro error no retriable
    """
    last_exception: Exception | None = None

    for attempt in range(max_attempts):
        try:
            return await func()
        except httpx.HTTPStatusError as exc:
            last_exception = exc
            status_code = exc.response.status_code

            if status_code not in retryable_status:
                logger.warning(
                    f"Error no retriable (HTTP {status_code}): {exc.response.text[:200]}"
                )
                raise

            delay = min(base_delay * (2 ** attempt), max_delay)
            jitter = random.uniform(0, delay * 0.1)
            total_delay = delay + jitter

            logger.warning(
                f"Error retriable (HTTP {status_code}), intento {attempt + 1}/{max_attempts}. "
                f"Reintentando en {total_delay:.2f}s..."
            )

            if attempt < max_attempts - 1:
                await asyncio.sleep(total_delay)

        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            last_exception = exc
            delay = min(base_delay * (2 ** attempt), max_delay)
            jitter = random.uniform(0, delay * 0.1)
            total_delay = delay + jitter

            logger.warning(
                f"Error de conexión ({type(exc).__name__}), intento {attempt + 1}/{max_attempts}. "
                f"Reintentando en {total_delay:.2f}s..."
            )

            if attempt < max_attempts - 1:
                await asyncio.sleep(total_delay)

    if last_exception:
        raise last_exception
    raise RuntimeError("with_retry: no se ejecutó ningún intento")


async def api_request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
) -> Any:
    """
    Ejecuta una request a la API con retry automático.

    Args:
        method: Método HTTP (GET, POST, PUT, DELETE)
        path: Path del endpoint (ej: /resources/123)
        params: Query parameters
        json: Body JSON

    Returns:
        Respuesta JSON de la API

    Raises:
        HTTPException: Con detalles del error
        RuntimeError: Si no hay autenticación configurada
    """
    _require_auth()

    async def _do_request() -> httpx.Response:
        async with _client() as client:
            headers = _auth_headers()
            resp = await client.request(
                method.upper(),
                path,
                params=_merge_auth(params),
                json=json,
                headers=headers if headers else None,
            )
            resp.raise_for_status()
            return resp

    try:
        resp = await with_retry(_do_request)
    except AuthGatewayError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except httpx.HTTPStatusError as exc:
        detail = f"Error de API ({exc.response.status_code}): {exc.response.text}"
        raise HTTPException(status_code=502, detail=detail)
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        raise HTTPException(
            status_code=502, detail=f"Error de conexión con la API: {exc}"
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Error al conectar con la API: {exc}"
        )

    try:
        return resp.json()
    except Exception:
        return resp.text


# Crear instancia del servidor MCP
mcp = FastMCP(
    name=f"{config.service.display_name} MCP",
    instructions=config.service.description,
    host=MCP_HOST,
    port=MCP_PORT,
)


# =============================================================================
# Herramientas de Autenticación (siempre disponibles)
# =============================================================================

@mcp.tool(
    description="Configura el token JWT para autenticación con Auth Gateway. "
                "OBLIGATORIO: Llamar antes de usar cualquier otra herramienta."
)
async def set_auth_token(jwt: str) -> dict[str, Any]:
    """
    Configura el JWT para autenticación con Auth Gateway.

    El JWT se obtiene haciendo login en Auth Gateway (POST /auth/login).
    Una vez configurado, las credenciales se obtienen automáticamente.

    Args:
        jwt: Token JWT obtenido del login en Auth Gateway

    Returns:
        {
            "success": bool,
            "message": str,
            "error": str si falla
        }
    """
    if not jwt or not jwt.strip():
        return {
            "success": False,
            "error": "JWT vacío. Proporciona un JWT válido obtenido de Auth Gateway.",
        }

    jwt = jwt.strip()
    auth_service = get_auth_service()

    try:
        credentials = await auth_service.authenticate(jwt)

        logger.info(
            "auth_token_set",
            expires_at=credentials.expires_at.isoformat(),
        )

        return {
            "success": True,
            "message": "Autenticado correctamente via Auth Gateway",
            "credentials_expire_at": credentials.expires_at.isoformat(),
        }

    except AuthGatewayError as e:
        logger.warning("auth_token_failed", error=str(e))
        return {
            "success": False,
            "error": str(e),
        }

    except Exception as e:
        logger.error("auth_token_error", error=str(e))
        return {
            "success": False,
            "error": f"Error inesperado: {str(e)}",
        }


@mcp.tool(description="Cierra la sesión actual y limpia las credenciales cacheadas.")
async def logout() -> dict[str, Any]:
    """Cierra la sesión y limpia las credenciales del cache."""
    auth_service = get_auth_service()
    was_authenticated = auth_service.is_authenticated
    auth_service.logout()

    return {
        "success": True,
        "message": "Sesión cerrada" if was_authenticated else "No había sesión activa",
    }


@mcp.tool(description="Muestra el estado actual de autenticación.")
async def get_auth_status() -> dict[str, Any]:
    """
    Retorna el estado de autenticación actual.

    Returns:
        {
            "authenticated": bool,
            "auth_gateway_url": str,
            "credentials_expire_at": str (si autenticado),
            "message": str
        }
    """
    auth_service = get_auth_service()
    creds = auth_service.current_credentials

    if creds and not creds.is_expired:
        return {
            "authenticated": True,
            "auth_gateway_url": AUTH_GATEWAY_URL,
            "credentials_expire_at": creds.expires_at.isoformat(),
            "message": "Autenticado correctamente via Auth Gateway",
        }

    return {
        "authenticated": False,
        "auth_gateway_url": AUTH_GATEWAY_URL,
        "message": "No autenticado. Usa 'set_auth_token' con tu JWT para autenticarte.",
    }


# =============================================================================
# Punto de entrada
# =============================================================================

def _validate_auth_gateway_config() -> None:
    """Valida que AUTH_GATEWAY_URL esté configurado al inicio."""
    if not AUTH_GATEWAY_URL:
        logger.error("auth_gateway_not_configured")
        error_msg = f"""
============================================================
ERROR: AUTH_GATEWAY_URL no configurado
============================================================

Este MCP requiere autenticacion via Auth Gateway.

Configura la variable de entorno:
  AUTH_GATEWAY_URL=https://auth.example.com

Flujo de autenticacion:
  1. Usuario hace login en Auth Gateway -> obtiene JWT
  2. Llama a set_auth_token(jwt) en el MCP
  3. MCP obtiene credenciales de la API del Gateway

============================================================
"""
        print(error_msg, file=sys.stderr)
        sys.exit(1)

    logger.info(
        "auth_gateway_configured",
        gateway_url=AUTH_GATEWAY_URL,
    )


def main() -> None:
    """Punto de entrada principal del servidor MCP."""
    # Validar que AUTH_GATEWAY_URL esté configurado
    _validate_auth_gateway_config()

    # Registrar herramientas OpenAPI si el spec existe
    spec_path = Path(SPEC_PATH)
    if spec_path.exists():
        tool_count = register_openapi_tools(
            mcp,
            spec_path=spec_path,
            auth_params=_auth_params,
            auth_headers=_auth_headers,
            client_factory=_client,
        )
        logger.info("openapi_tools_registered", count=tool_count, spec=str(spec_path))
    else:
        logger.warning("openapi_spec_not_found", spec=str(spec_path))

    # Ejecutar con el transporte configurado (stdio o sse)
    transport = MCP_TRANSPORT if MCP_TRANSPORT in ("stdio", "sse") else "stdio"

    if transport == "sse":
        logger.info(
            "server_starting",
            transport=transport,
            host=MCP_HOST,
            port=MCP_PORT,
            endpoints=["/sse", "/messages/"],
        )

    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
