"""
Módulo de validación centralizado para el MCP.

Provee funciones de validación para:
- IDs de recursos (configurable via service.yaml)
- Strings con sanitización XSS
- URLs seguras
- Límites de longitud

Este módulo usa la configuración de service.yaml para determinar
los patrones de validación específicos del servicio.
"""

from __future__ import annotations

import html
import re
from typing import Any, Optional, Union
from urllib.parse import urlparse

from fastapi import HTTPException

from .config import get_config


# =============================================================================
# Constantes de Validación (defaults)
# =============================================================================

# Protocolos permitidos para URLs
ALLOWED_URL_SCHEMES = frozenset({"http", "https"})

# Patrones peligrosos para detección XSS básica
XSS_PATTERNS = [
    re.compile(r"<script\b", re.IGNORECASE),
    re.compile(r"javascript:", re.IGNORECASE),
    re.compile(r"on\w+\s*=", re.IGNORECASE),
    re.compile(r"<iframe\b", re.IGNORECASE),
    re.compile(r"<object\b", re.IGNORECASE),
    re.compile(r"<embed\b", re.IGNORECASE),
    re.compile(r"<svg\b.*\bonload\b", re.IGNORECASE),
    re.compile(r"data:\s*text/html", re.IGNORECASE),
]


# =============================================================================
# Excepciones Personalizadas
# =============================================================================

class ValidationError(HTTPException):
    """Excepción para errores de validación con contexto adicional."""

    def __init__(
        self,
        param: str,
        message: str,
        expected: Optional[str] = None,
        received: Optional[Any] = None,
    ):
        detail = {
            "error": "validation_error",
            "param": param,
            "message": message,
        }
        if expected:
            detail["expected"] = expected
        if received is not None:
            str_received = str(received)
            detail["received"] = str_received[:100] + "..." if len(str_received) > 100 else str_received

        super().__init__(status_code=400, detail=detail)


# =============================================================================
# Validación de IDs
# =============================================================================

def _get_id_pattern() -> re.Pattern:
    """Obtiene el patrón de validación de IDs desde la configuración."""
    config = get_config()
    return re.compile(config.validation.id_pattern)


def validate_resource_id(value: Optional[str], param_name: str = "id") -> str:
    """
    Valida que un string sea un ID válido según la configuración.

    Args:
        value: El valor a validar
        param_name: Nombre del parámetro para mensajes de error

    Returns:
        El ID validado (stripped)

    Raises:
        ValidationError: Si el ID no es válido
    """
    config = get_config()

    if value is None:
        raise ValidationError(
            param=param_name,
            message=f"{param_name} es requerido",
            expected=config.validation.id_description,
            received=None,
        )

    if not isinstance(value, str):
        raise ValidationError(
            param=param_name,
            message=f"{param_name} debe ser un string",
            expected=config.validation.id_description,
            received=type(value).__name__,
        )

    cleaned = value.strip()

    pattern = _get_id_pattern()
    if not pattern.match(cleaned):
        raise ValidationError(
            param=param_name,
            message=f"{param_name} debe ser un ID válido",
            expected=config.validation.id_description,
            received=value,
        )

    return cleaned


def validate_optional_id(
    value: Optional[str],
    param_name: str = "id",
) -> Optional[str]:
    """
    Valida un ID opcional.

    Args:
        value: El valor a validar (puede ser None)
        param_name: Nombre del parámetro para mensajes de error

    Returns:
        El ID validado o None si no se proporcionó

    Raises:
        ValidationError: Si se proporciona un valor inválido
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return validate_resource_id(value, param_name)


# =============================================================================
# Validación y Sanitización de Strings
# =============================================================================

def sanitize_string(
    value: Optional[str],
    param_name: str,
    *,
    required: bool = True,
    max_length: Optional[int] = None,
    allow_empty: bool = False,
    escape_html: bool = True,
    check_xss: bool = True,
) -> Optional[str]:
    """
    Sanitiza y valida un string.

    Args:
        value: El valor a sanitizar
        param_name: Nombre del parámetro para mensajes de error
        required: Si el valor es requerido
        max_length: Longitud máxima permitida (usa config si None)
        allow_empty: Si se permiten strings vacíos
        escape_html: Si se debe escapar HTML
        check_xss: Si se deben verificar patrones XSS

    Returns:
        El string sanitizado, o None si no es requerido y está vacío

    Raises:
        ValidationError: Si la validación falla
    """
    config = get_config()
    if max_length is None:
        max_length = config.validation.max_name_length

    if value is None:
        if required:
            raise ValidationError(
                param=param_name,
                message=f"{param_name} es requerido",
                expected="string no vacío",
                received=None,
            )
        return None

    if not isinstance(value, str):
        raise ValidationError(
            param=param_name,
            message=f"{param_name} debe ser un string",
            expected="string",
            received=type(value).__name__,
        )

    cleaned = value.strip()

    if not cleaned:
        if required and not allow_empty:
            raise ValidationError(
                param=param_name,
                message=f"{param_name} no puede estar vacío",
                expected="string no vacío",
                received="(vacío)",
            )
        return "" if allow_empty else None

    if len(cleaned) > max_length:
        raise ValidationError(
            param=param_name,
            message=f"{param_name} excede la longitud máxima de {max_length} caracteres",
            expected=f"string de máximo {max_length} caracteres",
            received=f"string de {len(cleaned)} caracteres",
        )

    if check_xss:
        for pattern in XSS_PATTERNS:
            if pattern.search(cleaned):
                raise ValidationError(
                    param=param_name,
                    message=f"{param_name} contiene contenido potencialmente peligroso",
                    expected="string sin scripts o código ejecutable",
                    received="(contenido bloqueado por seguridad)",
                )

    if escape_html:
        cleaned = html.escape(cleaned)

    return cleaned


def require_non_empty(value: Optional[str], param_name: str) -> str:
    """
    Valida que un string no esté vacío.

    Args:
        value: El valor a validar
        param_name: Nombre del parámetro

    Returns:
        El string limpio (stripped)

    Raises:
        ValidationError: Si el string está vacío o es None
    """
    result = sanitize_string(
        value,
        param_name,
        required=True,
        escape_html=False,
        check_xss=False,
    )
    assert result is not None
    return result


# =============================================================================
# Validación de URLs
# =============================================================================

def validate_url(
    value: Optional[str],
    param_name: str = "url",
    *,
    required: bool = True,
    allowed_schemes: frozenset[str] = ALLOWED_URL_SCHEMES,
) -> Optional[str]:
    """
    Valida que un string sea una URL segura.

    Args:
        value: La URL a validar
        param_name: Nombre del parámetro para mensajes de error
        required: Si la URL es requerida
        allowed_schemes: Esquemas permitidos (por defecto http/https)

    Returns:
        La URL validada, o None si no es requerida y está vacía

    Raises:
        ValidationError: Si la URL no es válida o segura
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ValidationError(
                param=param_name,
                message=f"{param_name} es requerido",
                expected="URL válida (http/https)",
                received=None,
            )
        return None

    if not isinstance(value, str):
        raise ValidationError(
            param=param_name,
            message=f"{param_name} debe ser un string",
            expected="URL válida",
            received=type(value).__name__,
        )

    cleaned = value.strip()

    try:
        parsed = urlparse(cleaned)
    except Exception:
        raise ValidationError(
            param=param_name,
            message=f"{param_name} no es una URL válida",
            expected="URL válida (http/https)",
            received=cleaned,
        )

    if not parsed.scheme:
        raise ValidationError(
            param=param_name,
            message=f"{param_name} debe incluir el esquema (http/https)",
            expected="URL con esquema http:// o https://",
            received=cleaned,
        )

    if parsed.scheme.lower() not in allowed_schemes:
        raise ValidationError(
            param=param_name,
            message=f"{param_name} usa un esquema no permitido",
            expected=f"URL con esquema: {', '.join(allowed_schemes)}",
            received=f"esquema '{parsed.scheme}'",
        )

    if not parsed.netloc:
        raise ValidationError(
            param=param_name,
            message=f"{param_name} debe incluir un host válido",
            expected="URL con host (ej: https://example.com)",
            received=cleaned,
        )

    dangerous_patterns = ["javascript:", "data:", "vbscript:"]
    cleaned_lower = cleaned.lower()
    for pattern in dangerous_patterns:
        if pattern in cleaned_lower:
            raise ValidationError(
                param=param_name,
                message=f"{param_name} contiene un patrón de URL peligroso",
                expected="URL http/https sin esquemas ejecutables",
                received="(bloqueado por seguridad)",
            )

    return cleaned


# =============================================================================
# Validación de Posiciones (común en muchas APIs)
# =============================================================================

def validate_position(
    pos: Union[str, int, float, None],
    param_name: str = "pos",
    valid_strings: frozenset[str] = frozenset({"top", "bottom"}),
) -> Union[str, int, float]:
    """
    Valida que un valor sea una posición válida.

    Acepta:
    - Strings específicos (por defecto "top" o "bottom")
    - Números positivos (int o float)

    Args:
        pos: La posición a validar
        param_name: Nombre del parámetro para mensajes de error
        valid_strings: Strings válidos como posición

    Returns:
        La posición validada

    Raises:
        ValidationError: Si la posición no es válida
    """
    if pos is None:
        raise ValidationError(
            param=param_name,
            message=f"{param_name} es requerido",
            expected=f"'{', '.join(valid_strings)}', o un número positivo",
            received=None,
        )

    if isinstance(pos, (int, float)):
        if pos < 0:
            raise ValidationError(
                param=param_name,
                message=f"{param_name} debe ser un número positivo",
                expected="número >= 0",
                received=str(pos),
            )
        return pos

    if isinstance(pos, str):
        cleaned = pos.strip().lower()

        if cleaned in valid_strings:
            return cleaned

        try:
            if "." in cleaned:
                num_value = float(cleaned)
            else:
                num_value = int(cleaned)

            if num_value < 0:
                raise ValidationError(
                    param=param_name,
                    message=f"{param_name} debe ser un número positivo",
                    expected="número >= 0",
                    received=cleaned,
                )
            return num_value
        except ValueError:
            pass

        raise ValidationError(
            param=param_name,
            message=f"{param_name} no es una posición válida",
            expected=f"'{', '.join(valid_strings)}', o un número positivo",
            received=pos,
        )

    raise ValidationError(
        param=param_name,
        message=f"{param_name} debe ser string o número",
        expected=f"'{', '.join(valid_strings)}', o un número positivo",
        received=type(pos).__name__,
    )
