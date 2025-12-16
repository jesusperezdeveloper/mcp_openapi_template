"""
Auth Gateway Service - Obtiene credenciales desde Auth Gateway.

Este módulo maneja la comunicación con el Auth Gateway para obtener
credenciales de APIs de forma dinámica usando JWT de usuarios.

Flujo:
1. Usuario proporciona JWT (obtenido via login en Auth Gateway)
2. MCP llama a GET {AUTH_GATEWAY_URL}{gateway_endpoint} con Bearer token
3. Auth Gateway devuelve {data: {credential_name: value, ...}}
4. Credenciales se cachean en memoria durante la sesión
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx
import structlog

from .config import get_config

logger = structlog.get_logger(__name__)

# Configuración desde variables de entorno
AUTH_GATEWAY_URL = os.getenv("AUTH_GATEWAY_URL", "")
AUTH_GATEWAY_API_KEY = os.getenv("AUTH_GATEWAY_API_KEY", "")
CREDENTIALS_CACHE_TTL_SECONDS = int(os.getenv("AUTH_CREDENTIALS_CACHE_TTL", "3600"))


@dataclass
class APICredentials:
    """Credenciales de API obtenidas del Auth Gateway."""

    credentials: dict[str, str]
    fetched_at: datetime = field(default_factory=datetime.utcnow)
    ttl_seconds: int = CREDENTIALS_CACHE_TTL_SECONDS

    @property
    def expires_at(self) -> datetime:
        """Momento en que expiran las credenciales cacheadas."""
        return self.fetched_at + timedelta(seconds=self.ttl_seconds)

    @property
    def is_expired(self) -> bool:
        """Verifica si las credenciales han expirado."""
        return datetime.utcnow() > self.expires_at

    def to_auth_params(self) -> dict[str, str]:
        """
        Convierte a parámetros de autenticación para la API.

        Usa la configuración de credentials_format para mapear
        las credenciales a query params o headers.
        """
        config = get_config()
        params = {}

        for mapping in config.auth.credentials_format:
            if mapping.name in self.credentials:
                value = self.credentials[mapping.name]
                if mapping.prefix:
                    value = f"{mapping.prefix}{value}"

                if mapping.query_param:
                    params[mapping.query_param] = value
                # Headers se manejan por separado en to_auth_headers()

        return params

    def to_auth_headers(self) -> dict[str, str]:
        """
        Convierte a headers de autenticación para la API.
        """
        config = get_config()
        headers = {}

        for mapping in config.auth.credentials_format:
            if mapping.name in self.credentials and mapping.header:
                value = self.credentials[mapping.name]
                if mapping.prefix:
                    value = f"{mapping.prefix}{value}"
                headers[mapping.header] = value

        return headers


@dataclass
class AuthGatewayError(Exception):
    """Error al comunicarse con el Auth Gateway."""

    message: str
    status_code: Optional[int] = None
    details: Optional[str] = None

    def __str__(self) -> str:
        if self.status_code:
            return f"Auth Gateway Error ({self.status_code}): {self.message}"
        return f"Auth Gateway Error: {self.message}"


class AuthGatewayService:
    """
    Servicio para obtener credenciales desde Auth Gateway.

    Maneja:
    - Comunicación HTTP con el Auth Gateway
    - Cache de credenciales en memoria (por JWT)
    - Renovación automática cuando expiran
    """

    def __init__(
        self,
        gateway_url: str = AUTH_GATEWAY_URL,
        api_key: str = AUTH_GATEWAY_API_KEY,
        cache_ttl_seconds: int = CREDENTIALS_CACHE_TTL_SECONDS,
        timeout: float = 30.0,
    ):
        self.gateway_url = gateway_url.rstrip("/")
        self.api_key = api_key
        self.cache_ttl_seconds = cache_ttl_seconds
        self.timeout = timeout
        self._cache: dict[str, APICredentials] = {}
        self._current_jwt: Optional[str] = None

        logger.info(
            "auth_gateway_service_init",
            gateway_url=self.gateway_url,
            has_api_key=bool(api_key),
            cache_ttl=cache_ttl_seconds,
        )

    @property
    def is_authenticated(self) -> bool:
        """Verifica si hay un JWT configurado con credenciales válidas."""
        if not self._current_jwt:
            return False
        creds = self._cache.get(self._current_jwt)
        return creds is not None and not creds.is_expired

    @property
    def current_credentials(self) -> Optional[APICredentials]:
        """Obtiene las credenciales actuales (si existen y no han expirado)."""
        if not self._current_jwt:
            return None
        creds = self._cache.get(self._current_jwt)
        if creds and not creds.is_expired:
            return creds
        return None

    async def authenticate(self, jwt: str) -> APICredentials:
        """
        Autentica con el Auth Gateway y obtiene credenciales.

        Args:
            jwt: Token JWT del usuario (obtenido via login en Auth Gateway)

        Returns:
            APICredentials con las credenciales de la API

        Raises:
            AuthGatewayError: Si falla la autenticación o el Gateway no responde
        """
        # Verificar cache primero
        cached = self._cache.get(jwt)
        if cached and not cached.is_expired:
            logger.debug("auth_cache_hit", jwt_hash=self._hash_jwt(jwt))
            self._current_jwt = jwt
            return cached

        # Fetch desde el Gateway
        logger.info("auth_fetching_credentials", gateway_url=self.gateway_url)
        credentials = await self._fetch_from_gateway(jwt)

        # Guardar en cache
        self._cache[jwt] = credentials
        self._current_jwt = jwt

        logger.info(
            "auth_credentials_cached",
            jwt_hash=self._hash_jwt(jwt),
            expires_at=credentials.expires_at.isoformat(),
        )

        return credentials

    async def _fetch_from_gateway(self, jwt: str) -> APICredentials:
        """
        Llama al Auth Gateway para obtener credenciales.

        Endpoint: GET {gateway_url}{gateway_endpoint}
        Headers:
            - Authorization: Bearer <jwt>
            - X-API-Key: <api_key>
        Response: {data: {credential_name: value, ...}}
        """
        config = get_config()
        url = f"{self.gateway_url}{config.auth.gateway_endpoint}"
        headers = {
            "Authorization": f"Bearer {jwt}",
            "X-API-Key": self.api_key,
        }

        service_name = config.service.display_name

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=headers)

                if response.status_code == 401:
                    raise AuthGatewayError(
                        message="JWT inválido o expirado. Por favor, vuelve a hacer login.",
                        status_code=401,
                    )

                if response.status_code == 403:
                    raise AuthGatewayError(
                        message=f"No tienes permisos para acceder a las credenciales de {service_name}.",
                        status_code=403,
                    )

                if response.status_code == 404:
                    raise AuthGatewayError(
                        message=f"No tienes credenciales de {service_name} configuradas en Auth Gateway. "
                                "Por favor, añade tus credenciales en el panel de Auth Gateway.",
                        status_code=404,
                    )

                if response.status_code >= 500:
                    raise AuthGatewayError(
                        message="Auth Gateway no disponible. Inténtalo más tarde.",
                        status_code=response.status_code,
                        details=response.text[:200] if response.text else None,
                    )

                response.raise_for_status()

                data = response.json()

                # Extraer credenciales del response
                # Formato esperado: {data: {key: value, ...}}
                creds_data = data.get("data", data)

                if not isinstance(creds_data, dict):
                    raise AuthGatewayError(
                        message="Respuesta inválida del Auth Gateway: formato incorrecto",
                        details=f"Tipo recibido: {type(creds_data).__name__}",
                    )

                # Verificar que tenemos las credenciales esperadas
                expected_creds = [m.name for m in config.auth.credentials_format]
                missing = [c for c in expected_creds if c not in creds_data]
                if missing:
                    raise AuthGatewayError(
                        message="Respuesta inválida del Auth Gateway: faltan credenciales",
                        details=f"Credenciales faltantes: {missing}",
                    )

                return APICredentials(
                    credentials=creds_data,
                    ttl_seconds=self.cache_ttl_seconds,
                )

        except httpx.ConnectError as e:
            raise AuthGatewayError(
                message=f"No se pudo conectar con Auth Gateway ({self.gateway_url})",
                details=str(e),
            )

        except httpx.TimeoutException:
            raise AuthGatewayError(
                message="Timeout al conectar con Auth Gateway",
                details=f"Timeout: {self.timeout}s",
            )

        except httpx.HTTPStatusError as e:
            raise AuthGatewayError(
                message="Error HTTP del Auth Gateway",
                status_code=e.response.status_code,
                details=e.response.text[:200] if e.response.text else None,
            )

    def get_auth_params(self) -> dict[str, str]:
        """
        Obtiene los parámetros de autenticación para la API.

        Returns:
            Dict con parámetros para usar en requests

        Raises:
            AuthGatewayError: Si no hay credenciales configuradas
        """
        creds = self.current_credentials
        if not creds:
            raise AuthGatewayError(
                message="No hay credenciales configuradas. "
                        "Usa la herramienta 'set_auth_token' con tu JWT primero."
            )
        return creds.to_auth_params()

    def get_auth_headers(self) -> dict[str, str]:
        """
        Obtiene los headers de autenticación para la API.

        Returns:
            Dict con headers para usar en requests

        Raises:
            AuthGatewayError: Si no hay credenciales configuradas
        """
        creds = self.current_credentials
        if not creds:
            raise AuthGatewayError(
                message="No hay credenciales configuradas. "
                        "Usa la herramienta 'set_auth_token' con tu JWT primero."
            )
        return creds.to_auth_headers()

    def clear_cache(self, jwt: Optional[str] = None) -> None:
        """
        Limpia el cache de credenciales.

        Args:
            jwt: JWT específico a limpiar. Si es None, limpia todo el cache.
        """
        if jwt:
            self._cache.pop(jwt, None)
            if self._current_jwt == jwt:
                self._current_jwt = None
            logger.info("auth_cache_cleared", jwt_hash=self._hash_jwt(jwt))
        else:
            self._cache.clear()
            self._current_jwt = None
            logger.info("auth_cache_cleared_all")

    def logout(self) -> None:
        """Cierra la sesión actual (limpia el JWT actual del cache)."""
        if self._current_jwt:
            self.clear_cache(self._current_jwt)

    @staticmethod
    def _hash_jwt(jwt: str) -> str:
        """Hash parcial del JWT para logging (no exponer el token completo)."""
        if len(jwt) < 20:
            return "***"
        return f"{jwt[:8]}...{jwt[-4:]}"


# Instancia global del servicio
_auth_service: Optional[AuthGatewayService] = None


def get_auth_service() -> AuthGatewayService:
    """
    Obtiene la instancia global del servicio de Auth Gateway.

    Raises:
        RuntimeError: Si AUTH_GATEWAY_URL o AUTH_GATEWAY_API_KEY no están configurados
    """
    global _auth_service

    if _auth_service is None:
        if not AUTH_GATEWAY_URL:
            raise RuntimeError(
                "AUTH_GATEWAY_URL no está configurado.\n\n"
                "Este MCP requiere autenticación via Auth Gateway.\n"
                "Configura la variable de entorno AUTH_GATEWAY_URL.\n\n"
                "Ejemplo: AUTH_GATEWAY_URL=https://auth.example.com"
            )
        if not AUTH_GATEWAY_API_KEY:
            raise RuntimeError(
                "AUTH_GATEWAY_API_KEY no está configurado.\n\n"
                "Este MCP requiere una API Key para comunicarse con el Auth Gateway.\n"
                "Configura la variable de entorno AUTH_GATEWAY_API_KEY."
            )
        _auth_service = AuthGatewayService(
            gateway_url=AUTH_GATEWAY_URL,
            api_key=AUTH_GATEWAY_API_KEY,
        )

    return _auth_service


def reset_auth_service() -> None:
    """Resetea la instancia global (útil para testing)."""
    global _auth_service
    _auth_service = None
